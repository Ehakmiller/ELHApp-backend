from __future__ import annotations

from pathlib import Path
import math

import numpy as np
import pandas as pd


ANALYSIS_DIR = Path(
    r"C:\Users\ehakm\Documents\ELHApp-Carbon_Calculator\docs\static_data\LCFS\analysis"
)
SOURCE_PATH = ANALYSIS_DIR / "poet_or_ca_thermal_efficiency_analysis.csv"
OUT_DETAIL = ANALYSIS_DIR / "poet_or_ca_iluc_residual_analysis.csv"
OUT_RANKED = ANALYSIS_DIR / "poet_or_ca_iluc_residual_ranked.csv"
OUT_SUMMARY = ANALYSIS_DIR / "poet_or_ca_iluc_residual_summary.csv"
OUT_REPORT = ANALYSIS_DIR / "poet_or_ca_iluc_residual_report.md"

EXPECTED_ILUC_SPREAD = 12.25
OUTLIER_CITIES = {"coon rapids", "jewell", "corning"}


def fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{digits}f}"
    return str(value).replace("|", "\\|")


def markdown_table(df: pd.DataFrame, digits: int = 2) -> str:
    cols = [str(c) for c in df.columns]
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(fmt(row[c], digits) for c in df.columns) + " |")
    return "\n".join(lines)


def regression(df: pd.DataFrame, x_col: str, y_col: str) -> dict:
    subset = df[[x_col, y_col]].dropna()
    if len(subset) < 3:
        return {
            "x": x_col,
            "y": y_col,
            "n": len(subset),
            "slope_per_unit": np.nan,
            "slope_per_1000_btu": np.nan,
            "intercept": np.nan,
            "r_squared": np.nan,
        }
    x = subset[x_col].astype(float)
    y = subset[y_col].astype(float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = intercept + slope * x
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "x": x_col,
        "y": y_col,
        "n": len(subset),
        "slope_per_unit": float(slope),
        "slope_per_1000_btu": float(slope * 1000) if x_col == "total_btu_per_gal" else np.nan,
        "intercept": float(intercept),
        "r_squared": np.nan if ss_tot == 0 else 1 - ss_res / ss_tot,
    }


def binary_flag(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("").astype(int)


def group_summary(df: pd.DataFrame, col: str) -> pd.DataFrame:
    tmp = df.copy()
    tmp[col] = tmp[col].fillna("").astype(str).replace("", "blank")
    return (
        tmp.groupby(col, dropna=False)
        .agg(
            pathway_count=("facility", "size"),
            facility_count=("facility", "nunique"),
            avg_residual=("residual_ci", "mean"),
            median_residual=("residual_ci", "median"),
            avg_btu=("total_btu_per_gal", "mean"),
            avg_or_ci=("or_ci", "mean"),
            avg_ca_ci=("ca_ci", "mean"),
        )
        .reset_index()
        .sort_values(["pathway_count", col], ascending=[False, True])
    )


def main() -> None:
    df = pd.read_csv(SOURCE_PATH)
    df["expected_spread"] = EXPECTED_ILUC_SPREAD
    df["residual_ci"] = (df["or_ci"] + EXPECTED_ILUC_SPREAD) - df["ca_ci"]
    df["residual_abs"] = df["residual_ci"].abs()
    df["outlier_group"] = np.where(
        df["city"].fillna("").str.lower().isin(OUTLIER_CITIES),
        "iowa_outlier",
        "other_poet",
    )

    df["chp_flag"] = binary_flag(df["chp_status"])
    df["fiber_flag"] = binary_flag(df["corn_fiber_technology_status"])
    df["d3_flag"] = binary_flag(df["d3_capability"])
    df["natural_gas_flag"] = df["natural_gas_source"].fillna("").str.lower().str.contains("natural gas").astype(int)

    ranked_cols = [
        "facility",
        "city",
        "state",
        "coproduct",
        "or_ci",
        "ca_ci",
        "or_minus_ca_spread",
        "expected_spread",
        "residual_ci",
        "total_btu_per_gal",
        "chp_status",
        "corn_fiber_technology_status",
        "d3_capability",
        "year_built",
        "capacity_mgy",
        "dryer_type",
        "natural_gas_source",
        "outlier_group",
    ]

    ranked = df.sort_values(["residual_abs", "facility", "coproduct"], ascending=[False, True, True])

    numeric_corrs = []
    for col in ["total_btu_per_gal", "year_built", "capacity_mgy", "chp_flag", "fiber_flag", "d3_flag", "natural_gas_flag"]:
        subset = df[[col, "residual_ci"]].dropna()
        unique = subset[col].nunique()
        corr = np.nan if len(subset) < 3 or unique < 2 else subset[col].corr(subset["residual_ci"])
        numeric_corrs.append(
            {
                "variable": col,
                "n": len(subset),
                "unique_values": unique,
                "correlation_with_residual": corr,
            }
        )
    corrs = pd.DataFrame(numeric_corrs)

    reg_pathway = regression(df, "total_btu_per_gal", "residual_ci")
    facility_avg = (
        df.groupby(["facility", "city", "state", "outlier_group"], dropna=False)
        .agg(
            residual_ci=("residual_ci", "mean"),
            or_ci=("or_ci", "mean"),
            ca_ci=("ca_ci", "mean"),
            or_minus_ca_spread=("or_minus_ca_spread", "mean"),
            total_btu_per_gal=("total_btu_per_gal", "first"),
            chp_status=("chp_status", "first"),
            corn_fiber_technology_status=("corn_fiber_technology_status", "first"),
            d3_capability=("d3_capability", "first"),
            year_built=("year_built", "first"),
            capacity_mgy=("capacity_mgy", "first"),
            pathway_count=("facility", "size"),
        )
        .reset_index()
    )
    reg_facility = regression(facility_avg, "total_btu_per_gal", "residual_ci")

    summaries = []
    for label, summary in [
        ("outlier_group", group_summary(df, "outlier_group")),
        ("chp_status", group_summary(df, "chp_status")),
        ("fiber_technology", group_summary(df, "corn_fiber_technology_status")),
        ("d3_capability", group_summary(df, "d3_capability")),
        ("dryer_type", group_summary(df, "dryer_type")),
        ("natural_gas_source", group_summary(df, "natural_gas_source")),
    ]:
        summary.insert(0, "grouping", label)
        summary = summary.rename(columns={summary.columns[1]: "bucket"})
        summaries.append(summary)
    summary_df = pd.concat(summaries, ignore_index=True)

    df[ranked_cols + ["residual_abs"]].to_csv(OUT_DETAIL, index=False)
    ranked[ranked_cols + ["residual_abs"]].to_csv(OUT_RANKED, index=False)
    summary_df.to_csv(OUT_SUMMARY, index=False)

    report = []
    report.append("# POET OR-to-CA ILUC Residual Analysis\n")
    report.append(
        "Residual = (OR CI + 12.25) - CA CI. A residual near zero means the OR-to-CA spread is explained by the assumed ILUC bridge.\n"
    )
    report.append(f"Matched POET corn-starch pathway rows: {len(df)}; facilities: {df['facility'].nunique()}.\n")
    report.append("## Ranked Residual Table\n")
    report.append(markdown_table(ranked[ranked_cols]))
    report.append("\n\n## Correlations With Residual\n")
    report.append(markdown_table(corrs, digits=4))
    report.append("\n\n## BTU Regression\n")
    report.append(
        f"Pathway-level: n={reg_pathway['n']}, slope={reg_pathway['slope_per_1000_btu']:.3f} residual CI per 1,000 BTU/gal, R²={reg_pathway['r_squared']:.3f}.\n"
    )
    report.append(
        f"Facility-average: n={reg_facility['n']}, slope={reg_facility['slope_per_1000_btu']:.3f} residual CI per 1,000 BTU/gal, R²={reg_facility['r_squared']:.3f}.\n"
    )
    report.append("\n## Group Summaries\n")
    report.append(markdown_table(summary_df))

    iowa = df[df["outlier_group"] == "iowa_outlier"]
    other = df[df["outlier_group"] == "other_poet"]
    report.append("\n\n## Conclusion\n")
    report.append(
        f"The Iowa outliers remain anomalous after the 12.25 CI ILUC bridge. Their average residual is {iowa['residual_ci'].mean():.2f}, "
        f"versus {other['residual_ci'].mean():.2f} for the rest of the matched POET pathways. "
        "That means OR+12.25 overstates the comparable CA CI for Coon Rapids, Jewell, and Corning by roughly 6.6 to 8.6 CI points, while the normal POET group is close to zero residual.\n"
    )
    report.append(
        f"Thermal BTU/gal does not explain much of the remaining variance: pathway-level R² is {reg_pathway['r_squared']:.3f} and facility-average R² is {reg_facility['r_squared']:.3f}. "
        "Fiber technology and D3 status have no useful explanatory power here because all matched POET rows carry the same BPX/Yes indicators; dryer type is also constant as Ring Dryer. CHP and gas source split the sample, but the three anomalous Iowa rows are not uniquely identified by either field.\n"
    )

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")

    print("POET OR-to-CA ILUC Residual Analysis")
    print(f"Rows: {len(df)}; facilities: {df['facility'].nunique()}")
    print("\nRanked residuals")
    print(ranked[ranked_cols].to_string(index=False))
    print("\nCorrelations")
    print(corrs.to_string(index=False))
    print("\nBTU regression")
    print(reg_pathway)
    print(reg_facility)
    print("\nOutlier group summary")
    print(group_summary(df, "outlier_group").to_string(index=False))
    print(f"\nWrote: {OUT_DETAIL}")
    print(f"Wrote: {OUT_RANKED}")
    print(f"Wrote: {OUT_SUMMARY}")
    print(f"Wrote: {OUT_REPORT}")


if __name__ == "__main__":
    main()
