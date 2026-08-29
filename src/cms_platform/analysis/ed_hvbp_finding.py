"""
The one finding with a number (README "Key finding").

Groups hospitals into quartiles by ED boarding time (proxy: OP_18d, median
minutes before transfer to another facility) and reports mean HVBP Total
Performance Score per quartile, plus a Spearman correlation between the two.

Cross-sectional, single fiscal year (FY2026), no lag applied — see README
"Data limitations". Run after `dbt build` has populated
dbt/cms_platform.duckdb.

Usage:
    python -m cms_platform.analysis.ed_hvbp_finding
"""

from __future__ import annotations

import duckdb
import pandas as pd
from scipy import stats

from cms_platform.common.settings import DUCKDB_PATH


def load_mart() -> pd.DataFrame:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        return con.execute(
            """
            select ccn, ed_boarding_time_minutes, total_performance_score, ed_volume_category
            from main.mart_ed_performance_vs_hvbp
            """
        ).fetchdf()
    finally:
        con.close()


def compute_finding(df: pd.DataFrame) -> dict:
    both = df.dropna(subset=["ed_boarding_time_minutes", "total_performance_score"]).copy()

    rho, pvalue = stats.spearmanr(both["ed_boarding_time_minutes"], both["total_performance_score"])

    both["boarding_quartile"] = pd.qcut(
        both["ed_boarding_time_minutes"], 4, labels=["Q1 (fastest)", "Q2", "Q3", "Q4 (slowest)"]
    )
    quartile_summary = (
        both.groupby("boarding_quartile", observed=True)
        .agg(
            mean_total_performance_score=("total_performance_score", "mean"),
            mean_boarding_minutes=("ed_boarding_time_minutes", "mean"),
            n_hospitals=("ccn", "count"),
        )
        .reset_index()
    )

    return {
        "n_hospitals_total_in_mart": len(df),
        "n_hospitals_with_both_metrics": len(both),
        "spearman_rho": round(float(rho), 4),
        "p_value": round(float(pvalue), 4),
        "quartile_summary": quartile_summary,
    }


def main() -> None:
    df = load_mart()
    result = compute_finding(df)

    print(f"Hospitals in mart: {result['n_hospitals_total_in_mart']}")
    print(f"Hospitals with both ED boarding time and Total Performance Score: {result['n_hospitals_with_both_metrics']}")
    print(f"Spearman rho = {result['spearman_rho']}, p = {result['p_value']}")
    print()
    print(result["quartile_summary"].to_string(index=False))


if __name__ == "__main__":
    main()
