from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
JSON_PATH = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\lcfs_dropdown_v2.json"
)
TARGET_EPMS = {"3573", "3578", "3699"}


def plant_epm(row: dict) -> str:
    fac = row.get("fac_info") or {}
    for value in (
        fac.get("epm"),
        row.get("EPM"),
        row.get("epm"),
        row.get("EPM_NUMBER"),
        row.get("facility_id"),
    ):
        text = "" if value is None else str(value).strip()
        if text and text.lower() not in {"nan", "none", "null"}:
            return text.replace(".0", "")
    return ""


def print_dropdown_records() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    for rec in data:
        epm = plant_epm(rec)
        if epm not in TARGET_EPMS:
            continue

        fac = rec.get("fac_info") or {}
        print(f"\n================ EPM {epm}: {fac.get('plant_name')} ================")
        print(
            {
                "ownership": fac.get("ownership"),
                "state": fac.get("state"),
                "city": fac.get("city"),
                "capacity": fac.get("ethanol_capacity_mgy"),
            }
        )
        print("canadian_fed_ci:", rec.get("canadian_fed_ci"))
        print("ci_summary:", json.dumps(rec.get("ci_summary"), indent=2))
        print(
            "tech_flags:",
            {
                key: (rec.get("tech_flags") or {}).get(key)
                for key in (
                    "technology",
                    "chp",
                    "white_fox",
                    "icm_p10",
                    "waste_heat",
                    "dryer_types",
                    "primary_process_fuel",
                    "fiber_technology",
                )
            },
        )
        print("ca_detail:", json.dumps((rec.get("lcfs_detail") or {}).get("ca_detail") or [], indent=2))
        print("or_detail:", json.dumps((rec.get("lcfs_detail") or {}).get("or_detail") or [], indent=2))


def candidate_tables(con: sqlite3.Connection) -> list[str]:
    tables = [
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    ]
    terms = ("lcfs", "ci", "ethanol", "canadian", "or_", "wa_", "bc_")
    return [table for table in tables if any(term in table.lower() for term in terms)]


def table_columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def search_sqlite_tables() -> None:
    with sqlite3.connect(DB_PATH) as con:
        for table in candidate_tables(con):
            cols = table_columns(con, table)
            interesting_cols = [
                col
                for col in cols
                if any(
                    token in col.lower()
                    for token in (
                        "epm",
                        "facility",
                        "company",
                        "feedstock",
                        "fuel",
                        "ci",
                        "pathway",
                        "description",
                    )
                )
            ]
            if not interesting_cols:
                continue

            try:
                df = pd.read_sql_query(f'SELECT * FROM "{table}"', con)
            except Exception:
                continue
            if df.empty:
                continue

            mask = pd.Series(False, index=df.index)
            for col in interesting_cols:
                mask = mask | df[col].astype(str).str.contains(
                    "3573|3578|3699|Blue Flint|Bonanza|Red Trail",
                    case=False,
                    na=False,
                )
            if not mask.any():
                continue

            print(f"\n--- SQLite table {table} {df.shape} ---")
            show_cols = interesting_cols[:16]
            print(df.loc[mask, show_cols].head(40).to_string(index=False))


def main() -> None:
    print_dropdown_records()
    search_sqlite_tables()


if __name__ == "__main__":
    main()
