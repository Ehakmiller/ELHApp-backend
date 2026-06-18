import sqlite3
from pathlib import Path

import pandas as pd


DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)

with sqlite3.connect(DB_PATH) as con:
    status = pd.read_sql_query(
        'SELECT "Status", COUNT(*) AS rows FROM corn_processors GROUP BY "Status" ORDER BY rows DESC',
        con,
    )
    values = pd.read_sql_query(
        """
        SELECT
          "C02 Pipeline -Direct" AS direct_ccs,
          "C02 Pipeline -3rd Party" AS third_party_ccs,
          COUNT(*) AS rows
        FROM corn_processors
        GROUP BY "C02 Pipeline -Direct", "C02 Pipeline -3rd Party"
        ORDER BY rows DESC
        LIMIT 30
        """,
        con,
    )
    sample = pd.read_sql_query(
        """
        SELECT "EPM", "Name", "State", "Status",
               "C02 Pipeline -Direct" AS direct_ccs,
               "C02 Pipeline -3rd Party" AS third_party_ccs,
               "Sponsor"
        FROM corn_processors
        WHERE COALESCE(TRIM("C02 Pipeline -Direct"), '') <> ''
           OR COALESCE(TRIM("C02 Pipeline -3rd Party"), '') <> ''
        LIMIT 40
        """,
        con,
    )

print("STATUS")
print(status.to_string(index=False))
print("\nCO2 VALUE COMBINATIONS")
print(values.to_string(index=False))
print("\nNONBLANK SAMPLE")
print(sample.to_string(index=False))
