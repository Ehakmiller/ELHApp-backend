from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
import sqlite3

import numpy as np
import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
WORKBOOK = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\Ethanol Production DataBase\MASTER Plant File - Current.xlsx"
)

SHEETS = (
    {
        "sheet": "British Columbia",
        "table": "BC_LCFS_CI",
        "header_markers": ("fuel_code", "carbon_intensity_gCO2e_per_MJ"),
        "epm_aliases": ("EPM", "EPA"),
        "ci_patterns": (r"carbon[_\s-]*intensity", r"\bbc\b.*\bci\b", r"\bci\b"),
        "plant_candidates": ("plant", "company", "Facility", "Facility Name", "Name"),
        "epm_overrides": {
            "Bonanza Bioenergy": "3574",
        },
    },
    {
        "sheet": "Washington",
        "table": "WA_LCFS_CI",
        "header_markers": ("Fuel Pathway Code", "Pathway Description"),
        "epm_aliases": ("EPM",),
        "ci_patterns": (r"^CI$", r"\bcurrent.*\bci\b", r"carbon[_\s-]*intensity"),
        "plant_candidates": ("Plant", "Name", "company", "Facility", "Facility Name"),
        "epm_overrides": {},
    },
)

EPM_COLUMN = "EPM"
EPM_COLUMN_CANDIDATES = ("EPM", "EPM#", "EPM Number", "EPM_NUMBER", "epm")
NULL_STRINGS = {"", "nan", "none", "null", "nat", "#n/a", "n/a"}


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_header(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def normalize_column_name(column: object, used: set[str]) -> str:
    name = normalize_header(column)
    if not name or name.lower().startswith("unnamed:"):
        name = "Column"

    base = name
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def clean_cell(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        text = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
        return None if text.lower() in NULL_STRINGS else text
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def normalize_epm(value: object) -> str | None:
    value = clean_cell(value)
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in NULL_STRINGS:
        return None
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def find_header_row(sheet_name: str, markers: tuple[str, ...]) -> int:
    preview = pd.read_excel(WORKBOOK, sheet_name=sheet_name, header=None, nrows=25, dtype=object)
    marker_set = {marker.strip().lower() for marker in markers}
    for row_idx, row in preview.iterrows():
        values = {normalize_header(value).lower() for value in row.tolist()}
        if marker_set.issubset(values):
            return int(row_idx)
    raise RuntimeError(
        f"Could not find header row on sheet {sheet_name!r}. "
        f"Expected markers: {', '.join(markers)}"
    )


def find_column(
    columns: pd.Index | list[str],
    candidates: tuple[str, ...],
    required: bool = False,
) -> str | None:
    by_lower = {str(col).strip().lower(): str(col) for col in columns}
    for candidate in candidates:
        match = by_lower.get(candidate.strip().lower())
        if match:
            return match
    if required:
        raise RuntimeError(f"Could not find required column. Candidates: {candidates}")
    return None


def find_pattern_column(columns: pd.Index | list[str], patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        matches = [
            str(col)
            for col in columns
            if re.search(pattern, str(col), flags=re.IGNORECASE)
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def clean_frame(df: pd.DataFrame, epm_aliases: tuple[str, ...]) -> pd.DataFrame:
    used: set[str] = set()
    df = df.copy()
    df.columns = [normalize_column_name(col, used) for col in df.columns]
    df = df.dropna(how="all").copy()

    for col in df.columns:
        df[col] = df[col].map(clean_cell)

    df = df.dropna(how="all").copy()

    epm_col = find_column(df.columns, epm_aliases)
    if epm_col and epm_col != EPM_COLUMN and EPM_COLUMN not in df.columns:
        df = df.rename(columns={epm_col: EPM_COLUMN})
        epm_col = EPM_COLUMN

    if epm_col:
        df[epm_col] = df[epm_col].map(normalize_epm)

    return df


def apply_epm_overrides(
    df: pd.DataFrame,
    overrides: dict[str, str],
    plant_candidates: tuple[str, ...],
) -> pd.DataFrame:
    if not overrides or EPM_COLUMN not in df.columns:
        return df

    plant_col = find_column(df.columns, plant_candidates)
    if not plant_col:
        return df

    out = df.copy()
    names = out[plant_col].fillna("").astype(str).str.strip().str.lower()
    for plant_name, epm in overrides.items():
        out.loc[names.eq(plant_name.strip().lower()), EPM_COLUMN] = normalize_epm(epm)
    return out


def sqlite_type_for(series: pd.Series, column_name: str) -> str:
    if column_name.strip().lower() == EPM_COLUMN.lower():
        return "TEXT"
    non_null = series.dropna()
    if non_null.empty:
        return "TEXT"
    if pd.api.types.is_bool_dtype(non_null):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(non_null):
        return "INTEGER"
    if pd.api.types.is_float_dtype(non_null):
        return "REAL"
    return "TEXT"


def create_table_if_missing(con: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    columns_sql = [
        f"{quote_ident(col)} {sqlite_type_for(df[col], col)}"
        for col in df.columns
    ]
    con.execute(f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} ({', '.join(columns_sql)})")


def existing_columns(con: sqlite3.Connection, table: str) -> list[str]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [row[1] for row in rows]


def add_missing_columns(con: sqlite3.Connection, table: str, df: pd.DataFrame) -> list[str]:
    existing = set(existing_columns(con, table))
    added: list[str] = []
    for col in df.columns:
        if col in existing:
            continue
        con.execute(
            f"ALTER TABLE {quote_ident(table)} "
            f"ADD COLUMN {quote_ident(col)} {sqlite_type_for(df[col], col)}"
        )
        existing.add(col)
        added.append(col)
    return added


def insert_rows(con: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    columns = list(df.columns)
    placeholders = ", ".join(["?"] * len(columns))
    columns_sql = ", ".join(quote_ident(col) for col in columns)
    sql = f"INSERT INTO {quote_ident(table)} ({columns_sql}) VALUES ({placeholders})"
    rows = [tuple(clean_cell(value) for value in row) for row in df.itertuples(index=False, name=None)]
    con.executemany(sql, rows)


def load_sheet(config: dict[str, object]) -> dict[str, object]:
    sheet = str(config["sheet"])
    table = str(config["table"])
    header_row = find_header_row(sheet, tuple(config["header_markers"]))
    df = pd.read_excel(WORKBOOK, sheet_name=sheet, header=header_row, dtype=object)
    df = clean_frame(df, tuple(config["epm_aliases"]))
    df = apply_epm_overrides(
        df,
        dict(config.get("epm_overrides", {})),
        tuple(config["plant_candidates"]),
    )

    if df.empty:
        raise RuntimeError(f"Sheet {sheet!r} produced no data rows after cleanup")

    with sqlite3.connect(DB_PATH) as con:
        create_table_if_missing(con, table, df)
        added_columns = add_missing_columns(con, table, df)
        con.execute(f"DELETE FROM {quote_ident(table)}")
        insert_rows(con, table, df)
        con.commit()

        row_count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]
        table_columns = existing_columns(con, table)

    epm_col = find_column(df.columns, EPM_COLUMN_CANDIDATES)
    plant_col = find_column(df.columns, tuple(config["plant_candidates"]))
    ci_col = find_pattern_column(df.columns, tuple(config["ci_patterns"]))
    preview_cols = [col for col in (epm_col, plant_col, ci_col) if col and col in df.columns]

    return {
        "sheet": sheet,
        "table": table,
        "header_row": header_row + 1,
        "source_rows": len(df),
        "source_columns": len(df.columns),
        "row_count": row_count,
        "table_columns": table_columns,
        "added_columns": added_columns,
        "preview": df[preview_cols].head(10) if preview_cols else pd.DataFrame(),
        "preview_cols": preview_cols,
    }


def main() -> None:
    print(f"Source workbook: {WORKBOOK}")
    print(f"SQLite database: {DB_PATH}")

    results = [load_sheet(config) for config in SHEETS]

    for result in results:
        print()
        print(f"Loaded {result['table']} from sheet {result['sheet']}")
        print(f"Excel header row: {result['header_row']}")
        print(f"Rows loaded: {result['row_count']}")
        print(f"Columns in source sheet: {result['source_columns']}")
        print(f"Columns in SQLite table: {len(result['table_columns'])}")
        if result["added_columns"]:
            print("Added columns:")
            for col in result["added_columns"]:
                print(f"  {col}")
        if result["preview_cols"]:
            print(f"Preview columns: {', '.join(result['preview_cols'])}")
            print(result["preview"].to_string(index=False))
        else:
            print("Preview columns: none found")


if __name__ == "__main__":
    main()
