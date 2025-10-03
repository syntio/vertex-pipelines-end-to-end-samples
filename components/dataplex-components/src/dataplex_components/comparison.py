from kfp import dsl
from typing import NamedTuple, Dict, List, Any


@dsl.component(
    base_image="europe-west2-docker.pkg.dev/PROJECT_ID/ml-pipeline-containers/ml-pipeline-base:latest",
    packages_to_install=["google-cloud-bigquery>=3.25.0", "pandas>=2.0.0"],
)
def compare_profiles(
    current_profile: Dict[str, Any],
    project_id: str,
    dataset_id: str = "data_profiles",
    profiles_table: str = "profile_scans",
    deviation_threshold: float = 0.1,  # 10%
) -> NamedTuple(
    "Outputs",
    [
        ("comparison_results", dict),
        ("significant_changes", list),
        ("comparison_summary", dict),
    ],
):
    """
    Compare current profile with historical baseline profiles

    Args:
        current_profile: Current profile scan results
        project_id: GCP project ID
        dataset_id: BigQuery dataset with historical profiles
        profiles_table: Table containing profile history
        deviation_threshold: Threshold for flagging significant changes (0.1 = 10%)

    Returns:
        comparison_results: Detailed comparison metrics
        significant_changes: List of significant deviations found
        comparison_summary: High-level comparison summary
    """
    from google.cloud import bigquery
    from datetime import datetime

    print("📊 Comparing current profile with historical baselines...")
    print(f"🎯 Deviation threshold: {deviation_threshold * 100}%")

    client = bigquery.Client(project=project_id)

    # Get current profile metadata
    current_metadata = current_profile["scan_metadata"]
    current_table = current_metadata["table_name"]
    current_stage = current_metadata["pipeline_stage"]
    current_columns = current_profile["column_metrics"]

    # Query historical profiles for same table/stage (last 30 days)
    baseline_query = f"""
    SELECT
        column_name,
        AVG(mean_value) as baseline_mean,
        AVG(stddev_value) as baseline_stddev,
        AVG(null_percentage) as baseline_null_pct,
        AVG(cardinality) as baseline_cardinality,
        COUNT(*) as baseline_sample_count
    FROM `{project_id}.{dataset_id}.{profiles_table}`
    WHERE table_name = '{current_table}'
      AND pipeline_stage = '{current_stage}'
      AND scan_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
      AND scan_timestamp < TIMESTAMP('{current_metadata["scan_timestamp"]}')
    GROUP BY column_name
    HAVING COUNT(*) >= 3  -- Require at least 3 historical samples
    """

    baseline_df = client.query(baseline_query).to_dataframe()

    if baseline_df.empty:
        print("⚠️ No historical baseline found - this is the first profile scan")
        return {}, [], {"status": "no_baseline", "first_scan": True}

    print(f"📈 Found baseline data for {len(baseline_df)} columns")

    # Perform comparisons
    comparison_results = {}
    significant_changes = []

    for column_name, current_metrics in current_columns.items():
        if column_name not in baseline_df["column_name"].values:
            print(f"⚠️ No baseline for column: {column_name}")
            continue

        baseline = baseline_df[baseline_df["column_name"] == column_name].iloc[0]

        column_comparisons = {"column_name": column_name, "comparisons": {}}

        # Compare numeric metrics
        numeric_metrics = [
            ("mean_value", "baseline_mean"),
            ("stddev_value", "baseline_stddev"),
            ("null_percentage", "baseline_null_pct"),
            ("cardinality", "baseline_cardinality"),
        ]

        for current_key, baseline_key in numeric_metrics:
            current_val = current_metrics.get(current_key)
            baseline_val = baseline[baseline_key]

            if (
                current_val is not None
                and baseline_val is not None
                and baseline_val != 0
            ):
                percent_change = (current_val - baseline_val) / baseline_val
                absolute_change = abs(percent_change)

                comparison = {
                    "current_value": current_val,
                    "baseline_value": baseline_val,
                    "absolute_change": current_val - baseline_val,
                    "percent_change": percent_change,
                    "is_significant": absolute_change > deviation_threshold,
                }

                column_comparisons["comparisons"][current_key] = comparison

                # Flag significant changes
                if comparison["is_significant"]:
                    significance = "CRITICAL" if absolute_change > 0.2 else "WARNING"

                    significant_changes.append(
                        {
                            "column_name": column_name,
                            "metric": current_key,
                            "current_value": current_val,
                            "baseline_value": baseline_val,
                            "percent_change": percent_change * 100,
                            "significance_level": significance,
                            "deviation_threshold": deviation_threshold * 100,
                            "table_name": current_table,
                            "pipeline_stage": current_stage,
                        }
                    )

        comparison_results[column_name] = column_comparisons

    # Generate summary
    total_comparisons = sum(
        len(col["comparisons"]) for col in comparison_results.values()
    )
    significant_count = len(significant_changes)

    comparison_summary = {
        "total_columns_compared": len(comparison_results),
        "total_metric_comparisons": total_comparisons,
        "significant_changes_count": significant_count,
        "significant_changes_percentage": (
            (significant_count / total_comparisons * 100)
            if total_comparisons > 0
            else 0
        ),
        "deviation_threshold_used": deviation_threshold * 100,
        "baseline_samples": (
            int(baseline_df["baseline_sample_count"].iloc[0])
            if len(baseline_df) > 0
            else 0
        ),
        "comparison_timestamp": datetime.utcnow().isoformat(),
        "status": "completed",
    }

    print("✅ Profile comparison completed!")
    print(f"📊 Compared {comparison_summary['total_columns_compared']} columns")
    print(f"🚨 Found {significant_count} significant changes")

    if significant_count > 0:
        print("⚠️ SIGNIFICANT CHANGES DETECTED:")
        for change in significant_changes[:5]:  # Show first 5
            print(
                f"  - {change['column_name']}.{change['metric']}: {change['percent_change']:.1f}% change ({change['significance_level']})"
            )

    return comparison_results, significant_changes, comparison_summary


@dsl.component(
    base_image="europe-west2-docker.pkg.dev/PROJECT_ID/ml-pipeline-containers/ml-pipeline-base:latest",
    packages_to_install=["google-cloud-bigquery>=3.25.0"],
)
def detect_significant_changes(
    significant_changes: List[Dict[str, Any]],
    project_id: str,
    dataset_id: str = "data_profiles",
    comparisons_table: str = "profile_comparisons",
    pipeline_run_id: str = "",
) -> str:
    """
    Store significant profile changes and determine if pipeline should halt

    Args:
        significant_changes: List of significant deviations
        project_id: GCP project ID
        dataset_id: BigQuery dataset for storage
        comparisons_table: Table to store comparison results
        pipeline_run_id: Current pipeline run ID

    Returns:
        action: "CONTINUE" | "HALT" based on significance levels
    """
    from google.cloud import bigquery

    if not significant_changes:
        print("✅ No significant changes detected - pipeline can continue")
        return "CONTINUE"

    print(f"🚨 Processing {len(significant_changes)} significant changes...")

    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{comparisons_table}"

    # Store comparison results
    rows_to_insert = []
    critical_changes = 0

    for change in significant_changes:
        row = {
            "comparison_timestamp": bigquery.Client()
            .query("SELECT CURRENT_TIMESTAMP()")
            .to_dataframe()
            .iloc[0, 0],
            "pipeline_run_id": pipeline_run_id,
            "baseline_run_id": "historical_avg",  # Using historical average as baseline
            "table_name": change.get("table_name", "unknown"),
            "column_name": change["column_name"],
            "pipeline_stage": change.get("pipeline_stage", "unknown"),
            "metric_name": change["metric"],
            "current_value": change["current_value"],
            "baseline_value": change["baseline_value"],
            "absolute_change": change["current_value"] - change["baseline_value"],
            "percent_change": change["percent_change"],
            "is_significant": True,
            "deviation_threshold": change["deviation_threshold"],
            "significance_level": change["significance_level"],
        }
        rows_to_insert.append(row)

        if change["significance_level"] == "CRITICAL":
            critical_changes += 1

    # Insert into BigQuery
    errors = client.insert_rows_json(table_ref, rows_to_insert)

    if errors:
        print(f"⚠️ BigQuery insert errors: {errors}")
    else:
        print(f"💾 Stored {len(rows_to_insert)} comparison records")

    # Determine action based on critical changes
    if critical_changes > 0:
        print(f"🛑 CRITICAL CHANGES DETECTED: {critical_changes}")
        print("🚨 RECOMMENDATION: HALT PIPELINE FOR MANUAL REVIEW")
        return "HALT"
    else:
        print(f"⚠️ Warning-level changes detected: {len(significant_changes)}")
        print("✅ RECOMMENDATION: CONTINUE WITH MONITORING")
        return "CONTINUE"
