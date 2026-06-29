from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import json
import os
import re
import shutil
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
DEFAULT_JSON_PATH = Path("docs/static_data/LCFS/lcfs_dropdown_v2.json")
CARBON_CALC_JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
TABLE_ISCC = "iscc_certifications"
TABLE_WA = "WA_LCFS_CI"
TABLE_BC = "BC_LCFS_CI"
TABLE_CFR_CANDIDATES = ("Canadian_Fed_CI", "Candian_Fed_CI")
DEBUG_TARGETS = (
    ("PureField Ingredients / Russell KS", "3695"),
    ("Alto ICP / Pekin IL", "3553"),
)


def resolve_json_path() -> Path:
    env_path = os.environ.get("LCFS_JSON_PATH")
    if env_path:
        return Path(env_path)
    if DEFAULT_JSON_PATH.exists():
        return DEFAULT_JSON_PATH
    return CARBON_CALC_JSON_PATH


JSON_PATH = resolve_json_path()


def normalize_epm(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return re.sub(r"\.0$", "", text)


def plant_epm(row: dict) -> str:
    fac = row.get("fac_info") if isinstance(row.get("fac_info"), dict) else {}
    for value in (
        row.get("EPM_NUMBER"),
        row.get("epm_number"),
        row.get("epm"),
        row.get("EPM"),
        row.get("facility_id"),
        fac.get("epm"),
        fac.get("facility_id"),
    ):
        epm = normalize_epm(value)
        if epm:
            return epm
    return ""


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def is_nonempty(value: object) -> bool:
    text = clean_text(value)
    return bool(text and text.lower() not in {"nan", "none", "null", "<na>", "-"})


def active_row(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    status = clean_text(row.get("status") or row.get("Status")).lower()
    if status:
        return status == "active"
    active = clean_text(row.get("Active")).lower()
    if active:
        return active in {"1", "true", "active", "yes", "y"}
    return True


def rows_have_signal(rows: object, value_keys: tuple[str, ...]) -> bool:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not active_row(row):
            continue
        if not isinstance(row, dict):
            continue
        if any(is_nonempty(row.get(key)) for key in value_keys):
            return True
    return False


def plant_has_ca(row: dict) -> bool:
    detail = row.get("lcfs_detail") if isinstance(row.get("lcfs_detail"), dict) else {}
    records = row.get("ca_detail") or detail.get("ca_detail") or []
    return rows_have_signal(records, ("ci_score", "program", "feedstock", "pathway_type"))


def plant_has_or(row: dict) -> bool:
    detail = row.get("lcfs_detail") if isinstance(row.get("lcfs_detail"), dict) else {}
    records = row.get("or_detail") or detail.get("or_detail") or []
    return rows_have_signal(records, ("ci_score", "program", "feedstock", "pathway_type"))


def plant_has_wa(row: dict) -> bool:
    return rows_have_signal(
        row.get("wa_lcfs_ci_detail"),
        ("CI", "Fuel Pathway Code", "Pathway Description", "WA ID"),
    )


def plant_has_cfr(row: dict) -> bool:
    if is_nonempty(row.get("canadian_fed_ci")):
        return True
    return rows_have_signal(
        row.get("canadian_fed_ci_detail"),
        ("approved_ci_gco2e_mj", "fuel_type", "ci_status", "status", "facility_name"),
    )


def plant_has_bc(row: dict) -> bool:
    return rows_have_signal(
        row.get("bc_lcfs_ci_detail"),
        ("carbon_intensity_gCO2e_per_MJ", "fuel_code", "company"),
    )


def split_values(value: object) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    values = []
    for part in re.split(r"[;,]", text):
        cleaned = clean_text(part)
        if is_nonempty(cleaned):
            values.append(cleaned)
    return values


def dataframe_records(df: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for _, row in df.iterrows():
        record: dict[str, object] = {}
        for col in df.columns:
            if col == "_epm":
                continue
            value = row.get(col)
            if value is None or pd.isna(value):
                record[col] = None
            else:
                record[col] = value.item() if hasattr(value, "item") else value
        records.append(record)
    return records


def sqlite_tables(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def load_program_epms() -> dict[str, set[str]]:
    with sqlite3.connect(DB_PATH) as con:
        tables = sqlite_tables(con)
        program_epms: dict[str, set[str]] = {
            "wa_lcfs": set(),
            "bc_carbon": set(),
            "canadian_cfr": set(),
        }

        if TABLE_WA in tables:
            wa = pd.read_sql_query(f'SELECT * FROM "{TABLE_WA}"', con)
            if "EPM" in wa.columns:
                for _, row in wa.iterrows():
                    epm = normalize_epm(row.get("EPM"))
                    if not epm:
                        continue
                    if is_nonempty(row.get("CI")) or is_nonempty(row.get("Fuel Pathway Code")):
                        program_epms["wa_lcfs"].add(epm)

        if TABLE_BC in tables:
            bc = pd.read_sql_query(f'SELECT * FROM "{TABLE_BC}"', con)
            if "EPM" in bc.columns:
                for _, row in bc.iterrows():
                    epm = normalize_epm(row.get("EPM"))
                    if not epm:
                        continue
                    if is_nonempty(row.get("carbon_intensity_gCO2e_per_MJ")) or is_nonempty(row.get("fuel_code")):
                        program_epms["bc_carbon"].add(epm)

        cfr_table = next((table for table in TABLE_CFR_CANDIDATES if table in tables), "")
        if cfr_table:
            cfr = pd.read_sql_query(f'SELECT * FROM "{cfr_table}"', con)
            epm_col = next((col for col in ("EPM", "EPM#", "epm", "epm_number") if col in cfr.columns), "")
            if epm_col:
                for _, row in cfr.iterrows():
                    epm = normalize_epm(row.get(epm_col))
                    if not epm:
                        continue
                    if any(is_nonempty(row.get(col)) for col in ("Approved CI (gCO2e/MJ)", "CI Status", "Fuel Type", "Facility Name")):
                        program_epms["canadian_cfr"].add(epm)

    return program_epms


def load_iscc_by_epm() -> dict[str, dict[str, object]]:
    with sqlite3.connect(DB_PATH) as con:
        tables = sqlite_tables(con)
        if TABLE_ISCC not in tables:
            print(f"WARNING: table {TABLE_ISCC!r} not found; ISCC flags will be false.")
            return {}
        df = pd.read_sql_query(f'SELECT * FROM "{TABLE_ISCC}"', con)

    if df.empty or "epm_number" not in df.columns:
        return {}

    out: dict[str, dict[str, object]] = {}
    grouped = df.assign(_epm=df["epm_number"].map(normalize_epm))
    grouped = grouped[grouped["_epm"] != ""]

    type_columns = [
        col
        for col in ("schemes", "raw_materials_short", "products")
        if col in grouped.columns
    ]

    for epm, rows in grouped.groupby("_epm"):
        types: list[str] = []
        seen = set()
        for _, row in rows.iterrows():
            for col in type_columns:
                for value in split_values(row.get(col)):
                    key = value.lower()
                    if key and key not in seen:
                        seen.add(key)
                        types.append(value)
        out[epm] = {
            "iscc": True,
            "iscc_types": sorted(types, key=str.lower),
            "row_count": int(len(rows)),
            "raw_rows": dataframe_records(rows),
        }
    return out


def regulatory_object(
    row: dict,
    iscc_by_epm: dict[str, dict[str, object]],
    program_epms: dict[str, set[str]],
) -> dict[str, object]:
    epm = plant_epm(row)
    iscc_info = iscc_by_epm.get(epm, {})
    programs = {
        "ca_lcfs": plant_has_ca(row),
        "or_lcfs": plant_has_or(row),
        "wa_lcfs": epm in program_epms.get("wa_lcfs", set()) or plant_has_wa(row),
        "canadian_cfr": epm in program_epms.get("canadian_cfr", set()) or plant_has_cfr(row),
        "bc_carbon": epm in program_epms.get("bc_carbon", set()) or plant_has_bc(row),
        "iscc": bool(iscc_info.get("iscc")),
    }
    return {
        "registered_programs": programs,
        "iscc_types": list(iscc_info.get("iscc_types") or []),
    }


def print_debug_epm(
    data: list[object],
    iscc_by_epm: dict[str, dict[str, object]],
    label: str,
    epm: str,
) -> None:
    iscc_info = iscc_by_epm.get(epm, {})
    final_regulatory = {}
    for row in data:
        if isinstance(row, dict) and plant_epm(row) == epm:
            final_regulatory = row.get("regulatory_pathways") or {}
            break

    raw_rows = iscc_info.get("raw_rows") or []
    print(f"{label} ISCC debug:")
    print(f"  epm_number: {epm}")
    print(f"  number of ISCC rows found: {len(raw_rows)}")
    print("  raw ISCC row values:")
    print(json.dumps(raw_rows, ensure_ascii=False, indent=2))
    print("  final regulatory_pathways:")
    print(json.dumps(final_regulatory, ensure_ascii=False, indent=2))


def main() -> None:
    if not JSON_PATH.exists():
        raise FileNotFoundError(f"LCFS dropdown JSON not found: {JSON_PATH}")

    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected top-level JSON list, got {type(data).__name__}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSON_PATH.with_name(f"{JSON_PATH.stem}.backup_{timestamp}{JSON_PATH.suffix}")
    shutil.copy2(JSON_PATH, backup_path)

    program_epms = load_program_epms()
    iscc_by_epm = load_iscc_by_epm()
    program_counts = defaultdict(int)
    iscc_match_count = 0

    for row in data:
        if not isinstance(row, dict):
            continue
        row["regulatory_pathways"] = regulatory_object(row, iscc_by_epm, program_epms)
        programs = row["regulatory_pathways"]["registered_programs"]
        for key, value in programs.items():
            if value:
                program_counts[key] += 1
        if programs.get("iscc"):
            iscc_match_count += 1

    for label, epm in DEBUG_TARGETS:
        print_debug_epm(data, iscc_by_epm, label, epm)

    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Updated LCFS dropdown JSON with regulatory_pathways")
    print(f"JSON path: {JSON_PATH}")
    print(f"Backup path: {backup_path}")
    print(f"Plants in JSON: {len(data)}")
    print(f"ISCC EPMs in database: {len(iscc_by_epm)}")
    print("Program EPMs in database:")
    for key in ("wa_lcfs", "canadian_cfr", "bc_carbon"):
        print(f"  {key}: {len(program_epms.get(key, set()))}")
    print(f"JSON plants matched to ISCC: {iscc_match_count}")
    print("Registered program counts:")
    for key in ("ca_lcfs", "or_lcfs", "wa_lcfs", "canadian_cfr", "bc_carbon", "iscc"):
        print(f"  {key}: {program_counts[key]}")


if __name__ == "__main__":
    main()
