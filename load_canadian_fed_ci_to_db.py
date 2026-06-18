from pathlib import Path
import sqlite3

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
WORKBOOK = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\Ethanol Production DataBase\MASTER Plant File - Current.xlsx"
)
SHEET = "Active Ethanol CI"
TABLE = "Candian_Fed_CI"


def main() -> None:
    df = pd.read_excel(WORKBOOK, sheet_name=SHEET, dtype=object)
    df = df.dropna(how="all").copy()
    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)

    with sqlite3.connect(DB_PATH) as con:
        existing = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            con,
            params=(TABLE,),
        )
        if not existing.empty:
            print(f"Replacing existing table: {TABLE}")

        df.to_sql(TABLE, con, if_exists="replace", index=False)

        row_count = con.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
        columns = [r[1] for r in con.execute(f'PRAGMA table_info("{TABLE}")').fetchall()]

    print(f"Wrote table {TABLE} to {DB_PATH}")
    print(f"Source workbook: {WORKBOOK}")
    print(f"Source sheet: {SHEET}")
    print(f"Rows loaded: {row_count}")
    print("Columns:")
    for col in columns:
        print(f"  {col}")


if __name__ == "__main__":
    main()
