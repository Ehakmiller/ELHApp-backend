from __future__ import annotations

from pathlib import Path
import re

import matplotlib.pyplot as plt
import pandas as pd


WORKBOOK = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Ethanol Industry Data\Ethanol Margin Calculation\LCFS3.xlsx"
)
OUTPUT = WORKBOOK.with_name("LCFS_Current_Certified_CI_by_Fuel_Feedstock.png")
SHEET = "Original"

FUEL_ORDER = [
    "Biodiesel (BIO)",
    "Ethanol (ETH)",
    "Renewable Diesel (RND)",
]

FEEDSTOCK_ORDER = {
    "Biodiesel (BIO)": [
        "Distillers' Corn Oil (003)",
        "Used Cooking Oil/Waste Oil (UCO) (001)",
        "Tallow (animal and poultry fat) (002)",
        "Soybean Oil (005)",
        "Canola Oil (006)",
    ],
    "Ethanol (ETH)": [
        "Corn (009)",
        "Corn Fiber (012)",
        "Grain Sorghum (010)",
        "Wheat Starch Slurry (014)",
        "Any Sugar Feedstock (040)",
        "Any Cellulosic Biomass (041)",
    ],
    "Renewable Diesel (RND)": [
        "Distillers' Corn Oil (003)",
        "Used Cooking Oil/Waste Oil (UCO) (001)",
        "Tallow (animal and poultry fat) (002)",
        "Soybean Oil (005)",
        "Canola Oil (006)",
    ],
}


def clean_feedstock(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "Distillers' Corn Oil (003)": "Distillers' Corn Oil (003)",
        "Sugarcane (018)": "Sugarcane (018)",
        "Used Cooking Oil (UCO)": "Used Cooking Oil/Waste Oil (UCO) (001)",
    }
    return replacements.get(text, text)


def clean_fuel_type(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    replacements = {
        "Biodiesel": "Biodiesel (BIO)",
        "Ethanol": "Ethanol (ETH)",
        "Renewable Diesel": "Renewable Diesel (RND)",
    }
    return replacements.get(text, text)


def is_retired(df: pd.DataFrame) -> pd.Series:
    if "Retired Pathway" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Retired Pathway"].fillna("").astype(str).str.strip().ne("")


def is_provisional(df: pd.DataFrame) -> pd.Series:
    return df.apply(
        lambda row: any("provisional" in str(value).lower() for value in row.values),
        axis=1,
    )


def fmt_ci(value: float) -> str:
    return f"{value:,.2f}" if pd.notna(value) else ""


def build_rows(df: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for fuel in FUEL_ORDER:
        fuel_df = df[df["Fuel Type"].eq(fuel)].copy()
        if fuel_df.empty:
            continue

        rows.append(
            [
                fuel,
                "Total",
                f"{len(fuel_df):,}",
                fmt_ci(fuel_df["Current Certified CI"].mean()),
                fmt_ci(fuel_df["Current Certified CI"].min()),
                fmt_ci(fuel_df["Current Certified CI"].max()),
            ]
        )

        grouped = (
            fuel_df.groupby("Feedstock", dropna=False)["Current Certified CI"]
            .agg(Pathways="count", Average="mean", Minimum="min", Maximum="max")
            .reset_index()
        )
        grouped["_order"] = grouped["Feedstock"].map(
            {feedstock: i for i, feedstock in enumerate(FEEDSTOCK_ORDER.get(fuel, []))}
        )
        grouped = grouped.sort_values(["_order", "Feedstock"], na_position="last")

        for _, row in grouped.iterrows():
            rows.append(
                [
                    "",
                    row["Feedstock"],
                    f"{int(row['Pathways']):,}",
                    fmt_ci(row["Average"]),
                    fmt_ci(row["Minimum"]),
                    fmt_ci(row["Maximum"]),
                ]
            )
    return rows


def render_table(rows: list[list[str]]) -> None:
    headers = [
        "Fuel Type",
        "Feedstock",
        "Pathways",
        "Avg Current Certified CI",
        "Min",
        "Max",
    ]

    fig_height = max(7.0, 0.34 * (len(rows) + 3))
    fig, ax = plt.subplots(figsize=(15.5, fig_height), dpi=220)
    ax.axis("off")

    title = "LCFS Current Certified CI by Fuel Type and Feedstock"
    subtitle = (
        f"Source: {WORKBOOK.name} | Sheet: {SHEET} | Global active pathways, excludes provisional"
    )
    fig.text(0.04, 0.965, title, ha="left", va="top", fontsize=18, weight="bold")
    fig.text(0.04, 0.925, subtitle, ha="left", va="top", fontsize=9, color="#555555")

    table = ax.table(
        cellText=rows,
        colLabels=headers,
        loc="upper left",
        cellLoc="left",
        colLoc="left",
        bbox=[0.035, 0.035, 0.93, 0.84],
        colWidths=[0.22, 0.36, 0.09, 0.19, 0.07, 0.07],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.25)

    for (row_idx, col_idx), cell in table.get_celld().items():
        cell.set_edgecolor("#d7dde5")
        cell.set_linewidth(0.6)
        if row_idx == 0:
            cell.set_facecolor("#263238")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("bold")
            cell.get_text().set_fontsize(9.5)
            continue

        row = rows[row_idx - 1]
        is_total = row[1] == "Total"
        if is_total:
            cell.set_facecolor("#e8eef3")
            cell.get_text().set_weight("bold")
        else:
            cell.set_facecolor("#ffffff" if row_idx % 2 else "#f8fafc")

        if col_idx in {2, 3, 4, 5}:
            cell.get_text().set_ha("right")

    fig.savefig(OUTPUT, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    df = pd.read_excel(WORKBOOK, sheet_name=SHEET, dtype=object)
    df["Fuel Type"] = df["Fuel Type"].map(clean_fuel_type)
    df = df[df["Fuel Type"].isin(FUEL_ORDER)].copy()
    df = df[~is_retired(df) & ~is_provisional(df)].copy()
    df["Feedstock"] = df["Feedstock"].map(clean_feedstock)
    df["Current Certified CI"] = pd.to_numeric(df["Current Certified CI"], errors="coerce")
    df = df.dropna(subset=["Current Certified CI"])

    rows = build_rows(df)
    render_table(rows)

    print(f"Wrote PNG: {OUTPUT}")
    print(f"Rows included in table: {len(rows)}")
    print(f"Pathways summarized: {len(df):,}")


if __name__ == "__main__":
    main()
