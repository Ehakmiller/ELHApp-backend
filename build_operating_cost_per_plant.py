from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd


QUARTERLY_JSON = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Ethanol Quarterly Data\Data Files\quarterly_master_current.json"
)
ETHANOL_DB = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)
OUT_XLSX = Path(__file__).with_name("Operating_Cost_Per_Plant.xlsx")


COMPANY_OWNER_MAP = {
    "Green Plains": ["Green Plains"],
    "VLO": ["Valero Renewables"],
    "Valero": ["Valero Renewables"],
    "ANDE": ["The Andersons"],
    "REX": ["Rex American", "REX American"],
    "Gevo": ["Gevo"],
    "Alto": ["Alto"],
    "Amentis": ["Aemetis"],
    "Aemetis": ["Aemetis"],
    "ADM": ["ADM"],
}


def period_quarter_count(period: str) -> int:
    text = str(period).upper()
    if "FY" in text:
        return 4
    return 1


def operating_cost_basis(costs: dict, financials: dict) -> tuple[float | None, str]:
    if not isinstance(costs, dict):
        costs = {}
    if not isinstance(financials, dict):
        financials = {}

    # Prefer direct total costs when present.
    for key in ["total_costs_mil", "operating_costs_mil", "cogs_incl_depreciation_mil"]:
        value = costs.get(key)
        if isinstance(value, (int, float)):
            return float(value), key

    # Otherwise reconstruct from revenue - operating income when available.
    revenue = financials.get("revenue_mil")
    operating_income = financials.get("operating_income_mil")
    if isinstance(revenue, (int, float)) and isinstance(operating_income, (int, float)):
        return float(revenue) - float(operating_income), "revenue_mil_minus_operating_income_mil"

    return None, "missing"


def load_plants() -> pd.DataFrame:
    con = sqlite3.connect(ETHANOL_DB)
    try:
        df = pd.read_sql_query(
            """
            SELECT
                EPM,
                Name,
                Ownership,
                State,
                City,
                [Ethanol Capacity] AS ethanol_capacity_mgy
            FROM corn_processors
            """,
            con,
        )
    finally:
        con.close()

    df["EPM"] = df["EPM"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["ethanol_capacity_mgy"] = pd.to_numeric(df["ethanol_capacity_mgy"], errors="coerce")
    df = df.dropna(subset=["Name", "Ownership"])
    df = (
        df.sort_values(["EPM", "Name", "Ownership"])
        .drop_duplicates(subset=["EPM", "Name", "Ownership", "State", "City"], keep="last")
        .copy()
    )
    return df


def company_plants(plants: pd.DataFrame, company: str) -> pd.DataFrame:
    owners = COMPANY_OWNER_MAP.get(company, [company])
    mask = False
    for owner in owners:
        mask = mask | plants["Ownership"].astype(str).str.contains(owner, case=False, na=False)
    out = plants[mask].copy()
    return out


def main() -> None:
    quarterly = json.load(open(QUARTERLY_JSON, encoding="utf-8"))
    plants = load_plants()

    company_period_rows = []
    plant_rows = []

    for company, cdata in quarterly.items():
        periods = cdata.get("periods", {}) if isinstance(cdata, dict) else {}
        pdf = company_plants(plants, company)
        company_capacity = pdf["ethanol_capacity_mgy"].sum(min_count=1)

        for period, rec in periods.items():
            costs = rec.get("costs", {}) if isinstance(rec, dict) else {}
            financials = rec.get("financials", {}) if isinstance(rec, dict) else {}
            operations = rec.get("operations", {}) if isinstance(rec, dict) else {}
            derived = rec.get("derived_metrics", {}) if isinstance(rec, dict) else {}
            cap = (derived.get("capacity", {}) or {}) if isinstance(derived, dict) else {}

            cost_mil, cost_basis = operating_cost_basis(costs, financials)
            gallons_mil = operations.get("ethanol_gallons_mil")
            if not isinstance(gallons_mil, (int, float)):
                gallons_mil = (derived.get("unit_economics", {}) or {}).get("gallons_used_for_ci_mil")

            cost_per_gal = (
                float(cost_mil) / float(gallons_mil)
                if isinstance(cost_mil, (int, float))
                and isinstance(gallons_mil, (int, float))
                and gallons_mil
                else None
            )

            company_period_rows.append(
                {
                    "company": company,
                    "period": period,
                    "reported_operating_cost_mil": cost_mil,
                    "cost_basis": cost_basis,
                    "reported_ethanol_gallons_mil": gallons_mil,
                    "company_cost_per_gallon": cost_per_gal,
                    "json_stated_capacity_mgy": cap.get("stated_capacity_mgy"),
                    "matched_db_plant_count": len(pdf),
                    "matched_db_capacity_mgy": company_capacity,
                }
            )

            if pdf.empty or not isinstance(cost_mil, (int, float)) or not company_capacity:
                continue

            q_count = period_quarter_count(period)
            annualized_company_cost_mil = float(cost_mil) * q_count

            for _, plant in pdf.iterrows():
                cap_mgy = plant["ethanol_capacity_mgy"]
                if not isinstance(cap_mgy, (int, float)) or pd.isna(cap_mgy):
                    continue
                share = float(cap_mgy) / float(company_capacity)
                allocated_period_cost_mil = float(cost_mil) * share
                allocated_annual_cost_mil = annualized_company_cost_mil * share
                plant_rows.append(
                    {
                        "company": company,
                        "period": period,
                        "epm": plant["EPM"],
                        "plant_name": plant["Name"],
                        "ownership": plant["Ownership"],
                        "city": plant["City"],
                        "state": plant["State"],
                        "plant_capacity_mgy": cap_mgy,
                        "company_matched_capacity_mgy": company_capacity,
                        "plant_capacity_share": share,
                        "allocated_period_operating_cost_mil": allocated_period_cost_mil,
                        "allocated_annualized_operating_cost_mil": allocated_annual_cost_mil,
                        "allocated_operating_cost_per_capacity_gal": allocated_annual_cost_mil / float(cap_mgy),
                        "company_cost_per_actual_gallon": cost_per_gal,
                        "allocation_method": "company_period_cost_allocated_by_db_ethanol_capacity",
                        "cost_basis": cost_basis,
                    }
                )

    company_df = pd.DataFrame(company_period_rows)
    plant_df = pd.DataFrame(plant_rows)

    latest_period_order = {
        p: i
        for i, p in enumerate(
            sorted(
                company_df["period"].dropna().unique(),
                key=lambda x: (str(x).split()[0], str(x).split()[-1]),
                reverse=True,
            )
        )
    }
    plant_df["period_sort"] = plant_df["period"].map(latest_period_order)
    plant_df = plant_df.sort_values(["period_sort", "company", "plant_name"]).drop(columns=["period_sort"])

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        plant_df.to_excel(writer, sheet_name="plant_allocated_costs", index=False)
        company_df.sort_values(["company", "period"]).to_excel(writer, sheet_name="company_cost_basis", index=False)
        pd.DataFrame(
            [
                {
                    "note": "Plant costs are allocated estimates unless the source company directly discloses plant-level operating costs.",
                },
                {
                    "note": "Allocation uses each matched plant's ethanol capacity share within the company owner group from corn_processors.",
                },
                {
                    "note": "allocated_operating_cost_per_capacity_gal = annualized allocated operating cost in $ million divided by plant capacity in million gallons.",
                },
            ]
        ).to_excel(writer, sheet_name="notes", index=False)

    print(f"Wrote {OUT_XLSX}")
    print("company rows", len(company_df), "plant rows", len(plant_df))
    if not plant_df.empty:
        latest = plant_df[plant_df["period"].eq("2026 Q1")]
        print(latest[["company", "plant_name", "allocated_operating_cost_per_capacity_gal", "company_cost_per_actual_gallon"]].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
