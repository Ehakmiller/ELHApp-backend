from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
import shutil
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)

TABLE_CANDIDATES = ("Canadian_Fed_CI", "Candian_Fed_CI")
CI_COLUMN_CANDIDATES = (
    "canadian_fed_ci",
    "Canadian_Fed_CI",
    "Approved CI (gCO2e/MJ)",
    "Approved CI",
)
EPM_COLUMN_CANDIDATES = ("EPM#", "EPM", "epm", "EPM_NUMBER")

DETAIL_COLUMN_MAP = {
    "CI Applicant": "ci_applicant",
    "Facility Name": "facility_name",
    "City": "city",
    "Country": "country",
    "Fuel Type": "fuel_type",
    "Feedstock Type": "grain_source",
    "Feedstock Origin (Province/State/ Region/ Country)": "feedstock_origin",
    "CI Type": "ci_type",
    "CI Scope (Cradle-to-Gate, Cradle-to-Grave)": "ci_scope",
    "Approved CI (gCO2e/MJ)": "approved_ci_gco2e_mj",
    "CI Approval Date": "approval_date",
    "Version of the Fuel LCA Model": "fuel_lca_model_version",
    "CI Status": "status",
}


def normalize_epm(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    try:
        as_float = float(text)
        if as_float.is_integer():
            return str(int(as_float))
    except ValueError:
        pass
    return text


def plant_epm(row: dict) -> str:
    candidates = (
        row.get("EPM_NUMBER"),
        row.get("epm_number"),
        row.get("epm"),
        row.get("EPM"),
        row.get("facility_id"),
        row.get("fac_info", {}).get("epm") if isinstance(row.get("fac_info"), dict) else None,
    )
    for value in candidates:
        epm = normalize_epm(value)
        if epm:
            return epm
    return ""


def find_table(con: sqlite3.Connection) -> str:
    tables = {
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in TABLE_CANDIDATES:
        if table in tables:
            return table
    raise RuntimeError(f"None of these tables exist: {', '.join(TABLE_CANDIDATES)}")


def find_column(columns: list[str], candidates: tuple[str, ...], label: str) -> str:
    by_lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    raise RuntimeError(f"Could not find {label} column. Columns: {columns}")


def clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def clean_status(value):
    value = clean_value(value)
    if not isinstance(value, str):
        return value
    lowered = value.strip().lower()
    if lowered == "active":
        return "Active"
    if lowered == "expired":
        return "Expired"
    return value


def detail_record(row: pd.Series) -> dict[str, object]:
    detail = {}
    for source_col, out_key in DETAIL_COLUMN_MAP.items():
        if source_col in row.index:
            cleaner = clean_status if out_key == "status" else clean_value
            detail[out_key] = cleaner(row[source_col])
    return detail


def load_ci_map() -> tuple[
    dict[str, object],
    dict[str, dict[str, object]],
    dict[str, list[object]],
    str,
    str,
]:
    with sqlite3.connect(DB_PATH) as con:
        table = find_table(con)
        df = pd.read_sql_query(f'SELECT * FROM "{table}"', con)

    epm_col = find_column(list(df.columns), EPM_COLUMN_CANDIDATES, "EPM")
    ci_col = find_column(list(df.columns), CI_COLUMN_CANDIDATES, "Canadian Federal CI")

    df["_epm_norm"] = df[epm_col].map(normalize_epm)
    df = df[df["_epm_norm"] != ""].copy()

    values_by_epm: dict[str, list[object]] = defaultdict(list)
    details_by_epm: dict[str, list[dict[str, object]]] = defaultdict(list)
    for _, row in df.iterrows():
        value = row[ci_col]
        if pd.isna(value):
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        values_by_epm[row["_epm_norm"]].append(value)
        details_by_epm[row["_epm_norm"]].append(detail_record(row))

    ci_map: dict[str, object] = {}
    detail_map: dict[str, dict[str, object]] = {}
    duplicates: dict[str, list[object]] = {}
    for epm, values in values_by_epm.items():
        unique_values = []
        for value in values:
            if value not in unique_values:
                unique_values.append(value)
        ci_map[epm] = unique_values[0]
        detail_map[epm] = details_by_epm[epm][0]
        if len(values) > 1 or len(unique_values) > 1:
            duplicates[epm] = unique_values

    return ci_map, detail_map, duplicates, table, ci_col


def main() -> None:
    ci_map, detail_map, db_duplicates, source_table, source_ci_col = load_ci_map()

    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected top-level JSON list, got {type(data).__name__}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSON_PATH.with_name(f"{JSON_PATH.stem}.backup_{timestamp}{JSON_PATH.suffix}")
    shutil.copy2(JSON_PATH, backup_path)

    json_epms = [plant_epm(row) if isinstance(row, dict) else "" for row in data]
    json_epm_counts = Counter(epm for epm in json_epms if epm)
    duplicate_json_epms = sorted(epm for epm, count in json_epm_counts.items() if count > 1)

    matched_epms = set()
    unmatched_epms = set()
    matched_rows = 0
    unmatched_rows = 0

    for row, epm in zip(data, json_epms):
        if not isinstance(row, dict):
            continue
        if epm and epm in ci_map:
            row["canadian_fed_ci"] = ci_map[epm]
            row["canadian_fed_ci_detail"] = detail_map.get(epm)
            matched_rows += 1
            matched_epms.add(epm)
        else:
            row["canadian_fed_ci"] = None
            row["canadian_fed_ci_detail"] = None
            unmatched_rows += 1
            if epm:
                unmatched_epms.add(epm)

    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Updated LCFS dropdown JSON with Canadian Federal CI")
    print(f"JSON path: {JSON_PATH}")
    print(f"Backup path: {backup_path}")
    print(f"SQLite source table: {source_table}")
    print(f"SQLite source CI column: {source_ci_col}")
    print(f"Total plants in JSON: {len(data)}")
    print(f"Matched plants: {matched_rows}")
    print(f"Unmatched plants: {unmatched_rows}")
    print(f"Matched unique EPMs: {len(matched_epms)}")
    print(f"Unmatched unique EPMs: {len(unmatched_epms)}")
    print(f"Duplicate EPM numbers in JSON: {len(duplicate_json_epms)}")
    if duplicate_json_epms:
        print("JSON duplicate EPMs:")
        for epm in duplicate_json_epms:
            print(f"  {epm}: {json_epm_counts[epm]} rows")
    print(f"Duplicate EPM numbers in Canadian CI source: {len(db_duplicates)}")
    if db_duplicates:
        print("Canadian CI duplicate EPMs:")
        for epm, values in sorted(db_duplicates.items()):
            print(f"  {epm}: {values}")


if __name__ == "__main__":
    main()
