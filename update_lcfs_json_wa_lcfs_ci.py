from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import shutil
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
TABLE = "WA_LCFS_CI"
TODAY = pd.Timestamp.today().normalize()


def normalize_epm(value: object) -> str:
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
    ):
        epm = normalize_epm(value)
        if epm:
            return epm
    return ""


def clean_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def quarter_start(value: object) -> pd.Timestamp:
    match = re.match(r"Q([1-4])\s+(\d{4})", str(value or "").strip(), flags=re.I)
    if not match:
        return pd.NaT
    quarter = int(match.group(1))
    year = int(match.group(2))
    return pd.Timestamp(year, (quarter - 1) * 3 + 1, 1)


def quarter_end(value: object) -> pd.Timestamp:
    match = re.match(r"Q([1-4])\s+(\d{4})", str(value or "").strip(), flags=re.I)
    if not match:
        return pd.NaT
    quarter = int(match.group(1))
    year = int(match.group(2))
    return pd.Timestamp(year, quarter * 3, 1) + pd.offsets.MonthEnd(0)


def active_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def status_from_row(row: pd.Series) -> str:
    if not active_bool(row.get("Active")):
        return "Expired"
    start = quarter_start(row.get("Eff. Start Qtr/Yr"))
    end = quarter_end(row.get("Eff. End Qtr/Yr"))
    if pd.notna(start) and start > TODAY:
        return "Pending"
    if pd.notna(end) and end < TODAY:
        return "Expired"
    return "Active"


def classify_feedstock(row: pd.Series) -> str | None:
    code = str(row.get("Fuel Pathway Code") or "").upper()
    desc = str(row.get("Pathway Description") or "").upper()
    text = f"{code} {desc}"
    if "WA012" in text or "FIBER" in text or "CELLULOSIC" in text:
        return "fiber/cellulosic"
    if "WA010" in text or "SORGHUM" in text:
        return "sorghum"
    if "WA009" in text or "CORN STARCH" in text or "ETHANOL FROM CORN" in text:
        return "corn starch"
    return None


def load_wa_records() -> tuple[dict[str, list[dict[str, object]]], int]:
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query(f'SELECT * FROM "{TABLE}"', con)

    df["_epm_norm"] = df["EPM"].map(normalize_epm)
    df = df[df["_epm_norm"] != ""].copy()

    records_by_epm: dict[str, list[dict[str, object]]] = {}
    for _, row in df.iterrows():
        record = {col: clean_value(row[col]) for col in df.columns if col != "_epm_norm"}
        record["status"] = status_from_row(row)
        record["feedstock_class"] = classify_feedstock(row)
        records_by_epm.setdefault(row["_epm_norm"], []).append(record)

    for records in records_by_epm.values():
        records.sort(
            key=lambda item: (
                str(item.get("status") != "Active"),
                str(item.get("feedstock_class") or ""),
                str(item.get("Fuel Pathway Code") or ""),
            )
        )

    return records_by_epm, len(df)


def main() -> None:
    records_by_epm, source_rows = load_wa_records()

    with JSON_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"Expected top-level JSON list, got {type(data).__name__}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = JSON_PATH.with_name(f"{JSON_PATH.stem}.backup_{timestamp}{JSON_PATH.suffix}")
    shutil.copy2(JSON_PATH, backup_path)

    matched_rows = 0
    matched_epms = set()
    unmatched_epms = set(records_by_epm)

    for row in data:
        if not isinstance(row, dict):
            continue
        epm = plant_epm(row)
        records = records_by_epm.get(epm, [])
        row["wa_lcfs_ci_detail"] = records
        if records:
            matched_rows += 1
            matched_epms.add(epm)
            unmatched_epms.discard(epm)

    with JSON_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Updated LCFS dropdown JSON with WA LCFS CI detail")
    print(f"JSON path: {JSON_PATH}")
    print(f"Backup path: {backup_path}")
    print(f"SQLite source table: {TABLE}")
    print(f"WA source rows with EPM: {source_rows}")
    print(f"Matched JSON plants: {matched_rows}")
    print(f"Matched unique EPMs: {len(matched_epms)}")
    print(f"Unmatched WA source EPMs: {len(unmatched_epms)}")
    if unmatched_epms:
        print("Unmatched WA source EPMs:")
        for epm in sorted(unmatched_epms):
            print(f"  {epm}")


if __name__ == "__main__":
    main()
