from __future__ import annotations

from pathlib import Path
import re
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
WORKBOOK = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\Ethanol Production DataBase\MASTER Plant File - Current.xlsx"
)
SHEET_CANDIDATES = (
    "British Columbia",
    "British Columbia LCFS",
    "BC LCFS",
    "BC",
)
TABLE = "BC_LCFS_CI"
EPM_COLUMN_CANDIDATES = ("EPM", "EPM#", "EPM Number", "EPM_NUMBER", "epm")
EPM_SOURCE_COLUMN_CANDIDATES = EPM_COLUMN_CANDIDATES + ("EPA",)
BC_CI_COLUMN_PATTERNS = (
    r"\bbc\b.*\bci\b",
    r"\bci\b.*\bbc\b",
    r"british\s+columbia.*\bci\b",
    r"carbon[_\s-]*intensity",
    r"\bci\s+score\b",
    r"\bci\b",
)


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_column_name(column: object, used: set[str]) -> str:
    name = str(column).strip()
    if not name or name.lower().startswith("unnamed:"):
        name = "Column"

    base = name
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    used: set[str] = set()
    df = df.copy()
    df.columns = [normalize_column_name(c, used) for c in df.columns]
    epm_source_col = find_column(df.columns, EPM_SOURCE_COLUMN_CANDIDATES, required=False)
    if epm_source_col and epm_source_col != "EPM" and "EPM" not in df.columns:
        df = df.rename(columns={epm_source_col: "EPM"})
    df = df.dropna(how="all").copy()

    for col in df.columns:
        df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    epm_col = find_column(df.columns, EPM_COLUMN_CANDIDATES, required=False)
    if epm_col:
        df[epm_col] = df[epm_col].map(normalize_epm)

    return df


def normalize_epm(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def choose_sheet() -> str:
    workbook = pd.ExcelFile(WORKBOOK)
    sheet_lookup = {sheet.strip().lower(): sheet for sheet in workbook.sheet_names}
    for candidate in SHEET_CANDIDATES:
        sheet = sheet_lookup.get(candidate.lower())
        if sheet:
            return sheet

    contains_bc = [
        sheet
        for sheet in workbook.sheet_names
        if "british" in sheet.lower() or re.search(r"\bbc\b", sheet, flags=re.IGNORECASE)
    ]
    if len(contains_bc) == 1:
        return contains_bc[0]

    raise RuntimeError(
        "Could not identify the British Columbia sheet. "
        f"Candidates checked: {SHEET_CANDIDATES}. Workbook sheets: {workbook.sheet_names}"
    )


def sqlite_type_for(series: pd.Series, column_name: str) -> str:
    if column_name.lower() in {c.lower() for c in EPM_COLUMN_CANDIDATES}:
        return "TEXT"
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TEXT"
    return "TEXT"


def create_table_if_missing(con: sqlite3.Connection, df: pd.DataFrame) -> None:
    columns_sql = [
        f"{quote_ident(col)} {sqlite_type_for(df[col], col)}"
        for col in df.columns
    ]
    con.execute(f"CREATE TABLE IF NOT EXISTS {quote_ident(TABLE)} ({', '.join(columns_sql)})")


def existing_columns(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(f"PRAGMA table_info({quote_ident(TABLE)})").fetchall()
    return [row[1] for row in rows]


def add_missing_columns(con: sqlite3.Connection, df: pd.DataFrame) -> list[str]:
    existing = set(existing_columns(con))
    added: list[str] = []
    for col in df.columns:
        if col in existing:
            continue
        col_type = sqlite_type_for(df[col], col)
        con.execute(
            f"ALTER TABLE {quote_ident(TABLE)} ADD COLUMN {quote_ident(col)} {col_type}"
        )
        existing.add(col)
        added.append(col)
    return added


def insert_rows(con: sqlite3.Connection, df: pd.DataFrame) -> None:
    insert_cols = list(df.columns)
    placeholders = ", ".join(["?"] * len(insert_cols))
    columns_sql = ", ".join(quote_ident(col) for col in insert_cols)
    sql = f"INSERT INTO {quote_ident(TABLE)} ({columns_sql}) VALUES ({placeholders})"

    rows = []
    for row in df.itertuples(index=False, name=None):
        rows.append(tuple(value_for_sql(value) for value in row))
    con.executemany(sql, rows)


def value_for_sql(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def find_column(
    columns: pd.Index | list[str] | tuple[str, ...],
    candidates: tuple[str, ...],
    required: bool = True,
) -> str | None:
    by_lower = {str(col).strip().lower(): str(col) for col in columns}
    for candidate in candidates:
        col = by_lower.get(candidate.lower())
        if col:
            return col
    if required:
        raise RuntimeError(f"Could not find required column. Candidates: {candidates}")
    return None


def find_bc_ci_column(columns: pd.Index | list[str]) -> str:
    for pattern in BC_CI_COLUMN_PATTERNS:
        matches = [
            str(col)
            for col in columns
            if re.search(pattern, str(col), flags=re.IGNORECASE)
        ]
        if len(matches) == 1:
            return matches[0]
    raise RuntimeError(f"Could not identify BC CI score column. Columns: {list(columns)}")


def main() -> None:
    sheet = choose_sheet()
    df = pd.read_excel(WORKBOOK, sheet_name=sheet, dtype={"EPM": str})
    df = clean_frame(df)

    epm_col = find_column(df.columns, EPM_COLUMN_CANDIDATES)
    bc_ci_col = find_bc_ci_column(df.columns)

    with sqlite3.connect(DB_PATH) as con:
        create_table_if_missing(con, df)
        added_columns = add_missing_columns(con, df)

        con.execute(f"DELETE FROM {quote_ident(TABLE)}")
        insert_rows(con, df)
        con.commit()

        row_count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(TABLE)}").fetchone()[0]
        table_columns = existing_columns(con)

    print(f"Loaded {TABLE} into {DB_PATH}")
    print(f"Source workbook: {WORKBOOK}")
    print(f"Source sheet: {sheet}")
    print(f"Rows loaded: {row_count}")
    print(f"Columns in source sheet: {len(df.columns)}")
    print(f"Columns in SQLite table: {len(table_columns)}")
    if added_columns:
        print("Added columns:")
        for col in added_columns:
            print(f"  {col}")
    print(f"Preview columns: {epm_col}, {bc_ci_col}")
    print(df[[epm_col, bc_ci_col]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
