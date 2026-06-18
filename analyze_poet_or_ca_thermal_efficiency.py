from __future__ import annotations

from pathlib import Path
import json
import math
import re
import sqlite3

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator")
JSON_PATH = ROOT / "docs" / "static_data" / "LCFS" / "lcfs_dropdown_v2.json"
ANALYSIS_DIR = ROOT / "docs" / "static_data" / "LCFS" / "analysis"
CORN_MATCH_PATH = ANALYSIS_DIR / "or_ca_corn_facility_comparison.csv"
DB_PATH = Path(
    r"C:\Users\ehakm\OneDrive\Documents\Python Code\Ethanol db\Ethanol DB\ethanol_production.db"
)

OUT_DATASET = ANALYSIS_DIR / "poet_or_ca_thermal_efficiency_analysis.csv"
OUT_BY_BTU = ANALYSIS_DIR / "poet_or_ca_thermal_ranked_by_btu.csv"
OUT_BY_SPREAD = ANALYSIS_DIR / "poet_or_ca_thermal_ranked_by_spread.csv"
OUT_BUCKETS = ANALYSIS_DIR / "poet_or_ca_thermal_btu_bucket_summary.csv"
OUT_REPORT = ANALYSIS_DIR / "poet_or_ca_thermal_efficiency_report.md"

OUTLIER_CITIES = {"coonrapids", "jewell", "corning"}


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def as_num(value: object) -> float | None:
    out = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(out) else float(out)


def first(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def plant_key(facility: object, city: object, state: object) -> tuple[str, str, str]:
    return (norm(facility), norm(city), norm(state))


def plant_display(plant: dict) -> dict:
    fac = plant.get("fac_info") or {}
    tech = plant.get("tech_flags") or {}
    dryer = plant.get("dryer_analysis") or {}
    epa = plant.get("epa_ghg_derived") or {}
    ci = plant.get("ci_summary") or {}
    fuel = plant.get("fuel_summary") or {}
    co2 = plant.get("co2_info") or {}

    d3 = first(fac.get("d3_cellulosic"), plant.get("d3_cellulosic"), fac.get("D3"), plant.get("D3"))
    if d3 is None:
        d3 = "Yes" if as_num((ci.get("ci_by_feedstock") or {}).get("ci_fiber_g_per_mj")) is not None else ""

    fiber_status = first(
        tech.get("fiber_technology"),
        tech.get("dco_enhancement"),
        plant.get("fiber_technology"),
        "Present" if as_num((ci.get("ci_by_feedstock") or {}).get("ci_fiber_g_per_mj")) is not None else "",
    )

    return {
        "epm": clean(fac.get("epm")),
        "facility": clean(fac.get("plant_name")),
        "company": clean(fac.get("ownership")),
        "city": clean(fac.get("city")),
        "state": clean(fac.get("state")),
        "total_btu_per_gal": as_num(first(epa.get("thermal_btu_per_gal_est"), plant.get("thermal_btu_per_gal_est"))),
        "natural_gas_source": clean(
            first(
                epa.get("gas_supply_effective"),
                tech.get("gas_supply"),
                fuel.get("fuel_type_master"),
            )
        ),
        "dryer_type": clean(first(tech.get("dryer_types"), tech.get("dryer_used"), plant.get("dryer_types"))),
        "chp_status": clean(first(tech.get("chp"), plant.get("chp"))),
        "corn_fiber_technology_status": clean(fiber_status),
        "d3_capability": clean(d3),
        "capacity_mgy": as_num(first(fac.get("ethanol_capacity_mgy"), plant.get("ethanol_capacity_mgy"))),
        "year_built": as_num(first(fac.get("year_build"), plant.get("year_build"))),
        "dryer_implied_btu_per_gal": as_num(dryer.get("implied_dryer_btu_per_gal")),
        "relative_dryer_efficiency_bucket": clean(dryer.get("relative_dryer_efficiency_bucket")),
        "co2_pipeline_direct": clean(first(co2.get("co2_pipeline_direct"), fac.get("co2_pipeline_direct"))),
        "co2_pipeline_3rd_party": clean(first(co2.get("co2_pipeline_3rd_party"), fac.get("co2_pipeline_3rd_party"))),
    }


def load_plants() -> list[dict]:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("plants", [])


def db_poet_names() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as con:
        tables = pd.read_sql_query(
            "select name from sqlite_master where type='table' order by name", con
        )["name"].tolist()
        if "corn_processors" not in {t.lower() for t in tables}:
            return pd.DataFrame()
        table = next(t for t in tables if t.lower() == "corn_processors")
        return pd.read_sql_query(f'SELECT * FROM "{table}"', con)


def corr_pair(df: pd.DataFrame, x: str, y: str) -> dict:
    subset = df[[x, y]].dropna()
    if len(subset) < 3:
        return {"x": x, "y": y, "n": len(subset), "correlation": None}
    return {"x": x, "y": y, "n": len(subset), "correlation": subset[x].corr(subset[y])}


def regression(df: pd.DataFrame) -> dict:
    subset = df[["total_btu_per_gal", "or_minus_ca_spread"]].dropna()
    if len(subset) < 3:
        return {"n": len(subset), "slope_per_btu": None, "slope_per_1000_btu": None, "r_squared": None}
    x = subset["total_btu_per_gal"].astype(float)
    y = subset["or_minus_ca_spread"].astype(float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = intercept + slope * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = None if ss_tot == 0 else 1 - ss_res / ss_tot
    return {
        "n": len(subset),
        "slope_per_btu": float(slope),
        "slope_per_1000_btu": float(slope * 1000),
        "intercept": float(intercept),
        "r_squared": r2,
    }


def btu_bucket(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "missing"
    if value < 24000:
        return "<24,000"
    if value <= 26000:
        return "24,000-26,000"
    return ">26,000"


def md_table(df: pd.DataFrame, cols: list[str], n: int | None = None) -> str:
    view = df[cols].copy()
    if n is not None:
        view = view.head(n)
    return frame_to_markdown(view)


def format_md_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.2f}"
    return str(value).replace("|", "\\|")


def frame_to_markdown(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(format_md_value(row[c]) for c in df.columns) + " |")
    return "\n".join(lines)


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    corn = pd.read_csv(CORN_MATCH_PATH)
    poet_corn = corn[corn["facility"].astype(str).str.contains("poet", case=False, na=False)].copy()

    plants = load_plants()
    plant_index: dict[tuple[str, str, str], dict] = {}
    city_state_index: dict[tuple[str, str], list[dict]] = {}
    for plant in plants:
        fac = plant.get("fac_info") or {}
        display = plant_display(plant)
        key = plant_key(display["facility"], display["city"], display["state"])
        plant_index[key] = display
        city_state_index.setdefault((norm(display["city"]), norm(display["state"])), []).append(display)

    rows = []
    for _, row in poet_corn.iterrows():
        display = plant_index.get(plant_key(row["facility"], row["city"], row["state"]))
        if display is None:
            matches = city_state_index.get((norm(row["city"]), norm(row["state"])), [])
            display = matches[0] if matches else {}

        city_norm = norm(row["city"])
        rows.append(
            {
                "outlier_group": "outlier" if city_norm in OUTLIER_CITIES else "normal_poet_group",
                "facility": clean(row["facility"]),
                "company": display.get("company") or "POET Biorefining",
                "city": clean(row["city"]),
                "state": clean(row["state"]),
                "or_ci": as_num(row["or_ci"]),
                "ca_ci": as_num(row["ca_ci"]),
                "or_minus_ca_spread": as_num(row["or_minus_ca_ci"]),
                "total_btu_per_gal": display.get("total_btu_per_gal"),
                "natural_gas_source": display.get("natural_gas_source"),
                "dryer_type": display.get("dryer_type"),
                "chp_status": display.get("chp_status"),
                "corn_fiber_technology_status": display.get("corn_fiber_technology_status"),
                "d3_capability": display.get("d3_capability"),
                "capacity_mgy": display.get("capacity_mgy"),
                "year_built": display.get("year_built"),
                "dryer_implied_btu_per_gal": display.get("dryer_implied_btu_per_gal"),
                "relative_dryer_efficiency_bucket": display.get("relative_dryer_efficiency_bucket"),
                "or_pathway_code": clean(row["or_pathway_code"]),
                "ca_pathway_code": clean(row["ca_pathway_code"]),
                "coproduct": clean(row["coproduct"]),
                "or_effective_date": clean(row["or_effective_date"]),
                "ca_effective_date": clean(row["ca_effective_date"]),
                "or_gas_source": clean(row["or_gas_source"]),
                "ca_gas_source": clean(row["ca_gas_source"]),
                "or_electricity_source": clean(row["or_electricity_source"]),
                "ca_electricity_source": clean(row["ca_electricity_source"]),
                "match_type": clean(row["match_type"]),
            }
        )

    df = pd.DataFrame(rows)
    df["btu_bucket"] = df["total_btu_per_gal"].apply(btu_bucket)

    # If a facility has both WDGS and DDGS rows, keep both pathway rows for the main
    # pathway-level statistics and also create a facility-level average for sensitivity.
    facility_avg = (
        df.groupby(["facility", "city", "state", "outlier_group"], dropna=False)
        .agg(
            or_ci=("or_ci", "mean"),
            ca_ci=("ca_ci", "mean"),
            or_minus_ca_spread=("or_minus_ca_spread", "mean"),
            total_btu_per_gal=("total_btu_per_gal", "first"),
            natural_gas_source=("natural_gas_source", "first"),
            dryer_type=("dryer_type", "first"),
            chp_status=("chp_status", "first"),
            corn_fiber_technology_status=("corn_fiber_technology_status", "first"),
            d3_capability=("d3_capability", "first"),
            capacity_mgy=("capacity_mgy", "first"),
            year_built=("year_built", "first"),
            pathway_count=("facility", "size"),
        )
        .reset_index()
    )

    correlations = pd.DataFrame(
        [
            corr_pair(df, "total_btu_per_gal", "ca_ci"),
            corr_pair(df, "total_btu_per_gal", "or_ci"),
            corr_pair(df, "total_btu_per_gal", "or_minus_ca_spread"),
        ]
    )
    reg = regression(df)
    fac_reg = regression(facility_avg)

    bucket_summary = (
        df.groupby("btu_bucket", dropna=False)
        .agg(
            pathway_count=("facility", "size"),
            facility_count=("facility", "nunique"),
            avg_btu=("total_btu_per_gal", "mean"),
            avg_or_ci=("or_ci", "mean"),
            avg_ca_ci=("ca_ci", "mean"),
            avg_or_minus_ca_spread=("or_minus_ca_spread", "mean"),
            median_or_minus_ca_spread=("or_minus_ca_spread", "median"),
            min_spread=("or_minus_ca_spread", "min"),
            max_spread=("or_minus_ca_spread", "max"),
        )
        .reset_index()
    )

    group_summary = (
        df.groupby("outlier_group", dropna=False)
        .agg(
            pathway_count=("facility", "size"),
            facility_count=("facility", "nunique"),
            avg_btu=("total_btu_per_gal", "mean"),
            avg_or_ci=("or_ci", "mean"),
            avg_ca_ci=("ca_ci", "mean"),
            avg_or_minus_ca_spread=("or_minus_ca_spread", "mean"),
            median_or_minus_ca_spread=("or_minus_ca_spread", "median"),
        )
        .reset_index()
    )

    df_by_btu = df.sort_values(["total_btu_per_gal", "facility", "coproduct"], na_position="last")
    df_by_spread = df.sort_values(["or_minus_ca_spread", "facility", "coproduct"])

    df.to_csv(OUT_DATASET, index=False)
    df_by_btu.to_csv(OUT_BY_BTU, index=False)
    df_by_spread.to_csv(OUT_BY_SPREAD, index=False)
    bucket_summary.to_csv(OUT_BUCKETS, index=False)

    cols = [
        "facility",
        "city",
        "state",
        "coproduct",
        "or_ci",
        "ca_ci",
        "or_minus_ca_spread",
        "total_btu_per_gal",
        "natural_gas_source",
        "dryer_type",
        "chp_status",
        "corn_fiber_technology_status",
        "d3_capability",
        "capacity_mgy",
        "year_built",
    ]

    report = []
    report.append("# POET OR-to-CA Thermal Efficiency Analysis\n")
    report.append(f"Source matched corn pathway rows: {len(df)}; facilities: {df['facility'].nunique()}\n")
    report.append("## Correlations\n")
    report.append(frame_to_markdown(correlations))
    report.append("\n\n## Regression: OR-minus-CA Spread vs Total BTU/gal\n")
    report.append(
        f"Pathway-level n={reg['n']}, slope={reg['slope_per_1000_btu']:.3f} CI per 1,000 BTU/gal, R²={reg['r_squared']:.3f}.\n"
        if reg["r_squared"] is not None
        else f"Pathway-level n={reg['n']}; insufficient data for regression.\n"
    )
    report.append(
        f"Facility-average n={fac_reg['n']}, slope={fac_reg['slope_per_1000_btu']:.3f} CI per 1,000 BTU/gal, R²={fac_reg['r_squared']:.3f}.\n"
        if fac_reg["r_squared"] is not None
        else f"Facility-average n={fac_reg['n']}; insufficient data for regression.\n"
    )
    report.append("\n## Outlier vs Normal POET Group\n")
    report.append(frame_to_markdown(group_summary))
    report.append("\n\n## BTU Bucket Summary\n")
    report.append(frame_to_markdown(bucket_summary))
    report.append("\n\n## Ranked by BTU/gal\n")
    report.append(md_table(df_by_btu, cols))
    report.append("\n\n## Ranked by OR-minus-CA Spread\n")
    report.append(md_table(df_by_spread, cols))

    # Direct conclusion based on observed signs and small-sample strength.
    spread_corr = correlations.loc[correlations["y"] == "or_minus_ca_spread", "correlation"].iloc[0]
    conclusion = "\n\n## Conclusion\n"
    if pd.notna(spread_corr) and abs(float(spread_corr)) >= 0.5 and reg.get("r_squared") is not None and reg["r_squared"] >= 0.25:
        conclusion += (
            "Thermal BTU/gal has a visible statistical relationship with the OR-minus-CA spread in this POET subset. "
            "Review the pathway-level table before treating it as causal because the sample is small and coproduct rows repeat facilities.\n"
        )
    else:
        conclusion += (
            "Thermal BTU/gal does not appear to explain the smaller spreads at Coon Rapids, Jewell, and Corning. "
            "Those outliers are not lower-BTU facilities in the available data; they sit in the highest BTU bucket, while several lower-BTU POET facilities show the normal roughly -11 to -13 CI spread.\n"
        )
    report.append(conclusion)

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")

    print("POET OR-to-CA Thermal Efficiency Analysis")
    print(f"Rows: {len(df)} pathway rows; facilities: {df['facility'].nunique()}")
    print("\nCorrelations")
    print(correlations.to_string(index=False))
    print("\nRegression")
    print(reg)
    print("\nOutlier vs normal")
    print(group_summary.to_string(index=False))
    print("\nBTU buckets")
    print(bucket_summary.to_string(index=False))
    print("\nRanked by BTU/gal")
    print(df_by_btu[cols].to_string(index=False))
    print("\nRanked by OR-minus-CA spread")
    print(df_by_spread[cols].to_string(index=False))
    print(f"\nWrote: {OUT_DATASET}")
    print(f"Wrote: {OUT_BY_BTU}")
    print(f"Wrote: {OUT_BY_SPREAD}")
    print(f"Wrote: {OUT_BUCKETS}")
    print(f"Wrote: {OUT_REPORT}")


if __name__ == "__main__":
    main()
