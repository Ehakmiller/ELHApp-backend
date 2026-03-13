# -*- coding: utf-8 -*-
"""
Created on Thu Jan  8 10:34:38 2026

@author: ehakm
"""

# -*- coding: utf-8 -*-
"""
Created on Thu Jan  8 10:06:12 2026
@author: ehakm
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\ehakm\Documents\ELHApp-backend")
DOCS_ROOT = REPO_ROOT / "docs"

# where you want the public site assets to live
BASIS_CHANGE_DIR_DOCS = DOCS_ROOT / "static_data" / "Basis_Changes" / "Current_Basis_Change"
BASIS_CHANGE_DIR_DOCS.mkdir(parents=True, exist_ok=True)

# (optional) also keep a copy in repo-root static_data if you still want it
BASIS_CHANGE_DIR_ROOT = REPO_ROOT / "static_data" / "Basis_Changes" / "Current_Basis_Change"
BASIS_CHANGE_DIR_ROOT.mkdir(parents=True, exist_ok=True)


DB_PATH = r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"

with sqlite3.connect(DB_PATH) as conn:

    # 1) Find latest basis DAY in the table (anchor)
    latest_day = pd.read_sql_query(
        "SELECT DATE(MAX(Date)) AS latest_day FROM CornBasis;", conn
    ).iat[0, 0]
    if latest_day is None:
        raise RuntimeError("CornBasis is empty—no dates found.")

    latest_day = pd.to_datetime(latest_day)

    # 2) Pull DISTINCT days in the last 30 days (anchored to latest_day)
    days_30 = pd.read_sql_query(
        """
        SELECT DISTINCT DATE(Date) AS day
        FROM CornBasis
        WHERE DATE(Date) >= DATE(?, '-30 day')
          AND DATE(Date) <= DATE(?)
        ORDER BY day DESC;
        """,
        conn,
        params=(latest_day.strftime("%Y-%m-%d"), latest_day.strftime("%Y-%m-%d"))
    )

    if days_30.empty:
        raise RuntimeError("No CornBasis rows found in the last 30 days window (unexpected).")

    # latest + 2nd latest
    latest_day_str = days_30["day"].iloc[0]
    second_latest_day_str = days_30["day"].iloc[1] if len(days_30) > 1 else None

    # nearest to 30 days ago (relative to latest_day in DB)
    target = latest_day - pd.Timedelta(days=30)
    dts = pd.to_datetime(days_30["day"], errors="coerce")
    nearest_30_str = days_30.loc[(dts - target).abs().idxmin(), "day"]

    date_table = pd.DataFrame({
        "Label": ["Latest", "Second Latest", "Nearest to (Latest - 30d)"],
        "Date":  [latest_day_str, second_latest_day_str, nearest_30_str],
    })
    print("\n=== Basis Date Table ===")
    print(date_table)

    # 3) CornBasis — ALL rows in last 30 days, ONE row per (Epm_number, day)
    corn_basis_30_query = """
    WITH day_rows AS (
      SELECT
        Epm_number,
        Name,
        Basis_price,
        Flat,
        Del_Month,
        Contract_Month,
        Adj_Basis,
        Date,
        DATE(Date) AS Basis_Day
      FROM CornBasis
      WHERE DATE(Date) >= DATE(?, '-30 day')
        AND DATE(Date) <= DATE(?)
    ),
    ranked AS (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY Epm_number, Basis_Day
          ORDER BY
            datetime(Date) DESC,
            CASE WHEN Basis_price IS NOT NULL AND (Flat IS NULL OR Flat = '') THEN 0 ELSE 1 END,
            Contract_Month DESC
        ) AS rn
      FROM day_rows
    )
    SELECT
      Epm_number,
      Name,
      Basis_price,
      Flat,
      Del_Month,
      Contract_Month,
      Adj_Basis,
      Date,
      Basis_Day
    FROM ranked
    WHERE rn = 1;
    """

    df_basis_30 = pd.read_sql_query(
        corn_basis_30_query,
        conn,
        params=(latest_day.strftime("%Y-%m-%d"), latest_day.strftime("%Y-%m-%d"))
    )

    # Normalize Adj_Basis
    df_basis_30["Adj_Basis"] = (
        df_basis_30["Adj_Basis"]
          .astype("object")
          .replace({None: pd.NA, "": pd.NA})
          .mask(df_basis_30["Adj_Basis"].astype(str).str.strip() == "", pd.NA)
          .fillna("No Basis")
    )

    # 3-day subset
    keep_days = [d for d in [latest_day_str, second_latest_day_str, nearest_30_str] if d]
    df_basis_3days = df_basis_30[df_basis_30["Basis_Day"].isin(keep_days)].copy()

    # 4) Pull plant master fields from Corn_Processors and merge on EPM
    df_proc = pd.read_sql_query("""
    SELECT
      EPM,
      Name,
      State,
      City,
      Latitude,
      Longitude,
      Ownership
    FROM Corn_Processors
    """, conn)

    df_proc["EPM"] = df_proc["EPM"].astype(str).str.strip()
    df_basis_3days["Epm_number"] = df_basis_3days["Epm_number"].astype(str).str.strip()

    df_basis_3days = (df_basis_3days
        .merge(df_proc[["EPM","State","City","Latitude","Longitude","Ownership"]],
               left_on="Epm_number", right_on="EPM", how="left")
        .drop(columns=["EPM"])
    )

    # Optional: enforce numeric lat/lon
    df_basis_3days["Latitude"]  = pd.to_numeric(df_basis_3days["Latitude"], errors="coerce")
    df_basis_3days["Longitude"] = pd.to_numeric(df_basis_3days["Longitude"], errors="coerce")

    print("\n=== df_basis_3days with State/Lat/Lon ===")
    print(df_basis_3days[["Epm_number","State","City","Latitude","Longitude","Adj_Basis","Basis_Day"]].head(25))

    print("\nRows in last-30-days basis snapshot table:", len(df_basis_30))
    print("Rows in 3-day subset:", len(df_basis_3days))
    
    # Make numeric for math (No Basis -> NaN)
    df_basis_3days["Adj_Basis_num"] = pd.to_numeric(df_basis_3days["Adj_Basis"], errors="coerce")
    
    # Pivot wide: columns become the dates
    wide = (df_basis_3days
            .pivot_table(index=["Epm_number","Name", "State", "City", "Latitude", "Longitude", "Ownership"],
                         columns="Basis_Day",
                         values="Adj_Basis_num",
                         aggfunc="last")   # should be unique already, but safe
            .reset_index())
    
    print(wide.head(20))
    print("Columns:", wide.columns.tolist())

    wide["Delta 1 week"]  = wide[latest_day_str] - wide[second_latest_day_str]
    wide["Delta 1 month"] = wide[latest_day_str] - wide[nearest_30_str]
    
        # Make numeric for math (No Basis -> NaN)
    df_basis_3days["Adj_Basis_num"] = pd.to_numeric(df_basis_3days["Adj_Basis"], errors="coerce")
    
    # Pivot wide: columns become the dates
    wide = (df_basis_3days
            .pivot_table(
                index=["Epm_number","Name","State","City","Latitude","Longitude","Ownership"],
                columns="Basis_Day",
                values="Adj_Basis_num",
                aggfunc="last"
            )
            .reset_index())
    
    print(wide.head(20))
    print("Columns:", wide.columns.tolist())
    
    # --- Compute deltas ---
    # (guard in case second_latest_day_str is None)
    if second_latest_day_str is None:
        wide["Delta 1 week"] = np.nan
    else:
        wide["Delta 1 week"] = wide[latest_day_str] - wide[second_latest_day_str]
    
    wide["Delta 1 month"] = wide[latest_day_str] - wide[nearest_30_str]
    
    # sort for convenience
    wide = wide.sort_values("Delta 1 week", ascending=True, na_position="last").reset_index(drop=True)
    
    # -------------------------------------------------------------------
    # SAVE wide snapshot (overwrite) + APPEND a change-history sheet
    # --------------------------

    
    wide = wide.sort_values("Delta 1 week", ascending=True, na_position="last").reset_index(drop=True)
    
    wide.to_excel(r"C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\weekly_basis_deltas.xlsx", index=False)
    print(r"Saved file to C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\weekly_basis_deltas.xlsx")
    
    # ---- Largest Movers (PNG) ----
    GLOBALS = globals()
    GLOBALS["REPO_ROOT"] = str(REPO_ROOT)
    GLOBALS["DOCS_ROOT"] = str(DOCS_ROOT)
    GLOBALS["PUBLISH_DIR_DOCS"] = str(BASIS_CHANGE_DIR_DOCS)
    GLOBALS["PUBLISH_DIR_ROOT"] = str(BASIS_CHANGE_DIR_ROOT)
    
    exec(open(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Largest Movers basis.py",
              "r", encoding="utf-8").read(), GLOBALS)
    
    # ---- Map / HTML writer ----
    exec(open(r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Map that shows the basis change.py",
              "r", encoding="utf-8").read(), GLOBALS)
    
   