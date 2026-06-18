from __future__ import annotations

from pathlib import Path
import re
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
OUT_CSV = Path(__file__).with_name("current_bc_wa_lcfs_duplicate_scores.csv")
AS_OF = pd.Timestamp.today().normalize()


def normalize_epm(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "null"}:
        return ""
    return re.sub(r"\.0$", "", text)


def parse_date(value: object) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce")


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


def parse_bc_fuel_code(value: object) -> tuple[str, int]:
    match = re.search(r"([0-9]{3})(?:[.]([0-9]+))?", str(value or "").strip())
    if not match:
        return "", -1
    return match.group(1), int(match.group(2) or 0)


def current_bc(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EPM_norm"] = out["EPM"].map(normalize_epm)
    out["ci_score"] = pd.to_numeric(out["carbon_intensity_gCO2e_per_MJ"], errors="coerce")
    out["start_date"] = out["effective_date"].map(parse_date)
    out["end_date"] = out["expiry_date"].map(parse_date)
    out[["pathway_base", "pathway_version"]] = out["fuel_code"].apply(
        lambda value: pd.Series(parse_bc_fuel_code(value))
    )
    current_flag = pd.to_numeric(out["current_as_of_pdf_revision"], errors="coerce").fillna(0).astype(int).eq(1)
    current = out[
        out["EPM_norm"].ne("")
        & out["ci_score"].notna()
        & current_flag
        & (out["start_date"].isna() | out["start_date"].le(AS_OF))
        & (out["end_date"].isna() | out["end_date"].ge(AS_OF))
    ].copy()
    return (
        current.sort_values(["EPM_norm", "pathway_base", "pathway_version"])
        .groupby(["EPM_norm", "pathway_base"], as_index=False)
        .tail(1)
        .copy()
    )


def current_wa(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EPM_norm"] = out["EPM"].map(normalize_epm)
    out["ci_score"] = pd.to_numeric(out["CI"], errors="coerce")
    out["start_date"] = out["Eff. Start Qtr/Yr"].map(quarter_start)
    out["end_date"] = out["Eff. End Qtr/Yr"].map(quarter_end)
    return out[
        out["EPM_norm"].ne("")
        & out["ci_score"].notna()
        & out["Active"].map(active_bool)
        & (out["start_date"].isna() | out["start_date"].le(AS_OF))
        & (out["end_date"].isna() | out["end_date"].ge(AS_OF))
    ].copy()


def duplicate_rows(df: pd.DataFrame, program: str, name_col: str, code_col: str) -> pd.DataFrame:
    dupes = df.groupby("EPM_norm").filter(lambda group: len(group) > 1).copy()
    if dupes.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "program": program,
            "EPM": dupes["EPM_norm"],
            "plant": dupes[name_col],
            "ci_score": dupes["ci_score"],
            "pathway_code": dupes[code_col],
            "pathway_base": dupes["pathway_base"] if "pathway_base" in dupes.columns else "",
            "pathway_version": dupes["pathway_version"] if "pathway_version" in dupes.columns else "",
            "start": dupes["start_date"].dt.date.astype("string").fillna(""),
            "end": dupes["end_date"].dt.date.astype("string").fillna(""),
        }
    ).sort_values(["program", "EPM", "ci_score", "pathway_code"])


def main() -> None:
    with sqlite3.connect(DB_PATH) as con:
        bc = pd.read_sql_query("SELECT * FROM BC_LCFS_CI", con)
        wa = pd.read_sql_query("SELECT * FROM WA_LCFS_CI", con)

    bc_cur = current_bc(bc)
    wa_cur = current_wa(wa)

    bc_dupes = duplicate_rows(bc_cur, "BC", "company", "fuel_code")
    wa_dupes = duplicate_rows(wa_cur, "WA", "Plant", "Fuel Pathway Code")
    all_dupes = pd.concat([bc_dupes, wa_dupes], ignore_index=True)
    all_dupes.to_csv(OUT_CSV, index=False)

    print(f"As-of date: {AS_OF.date()}")
    print(f"BC current rows: {len(bc_cur)}; unique EPMs: {bc_cur['EPM_norm'].nunique()}")
    print(f"WA current rows: {len(wa_cur)}; unique EPMs: {wa_cur['EPM_norm'].nunique()}")
    print(f"Duplicate report: {OUT_CSV}")
    print()

    if all_dupes.empty:
        print("No duplicate current scores by EPM.")
        return

    summary = (
        all_dupes.groupby(["program", "EPM", "plant"], dropna=False)
        .agg(score_count=("ci_score", "count"), scores=("ci_score", lambda s: ", ".join(f"{v:.2f}" for v in s)))
        .reset_index()
        .sort_values(["program", "EPM"])
    )
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
