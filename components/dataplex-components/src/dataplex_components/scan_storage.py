from kfp import dsl
from typing import Dict, Any

@dsl.component(
    base_image="europe-west2-docker.pkg.dev/PROJECT_ID/ml-pipeline-containers/ml-pipeline-base:latest",
    packages_to_install=["google-cloud-bigquery>=3.25.0", "pandas>=2.0.0"]
)
def store_profile_results(
    profile_results: Dict[str, Any],
    project_id: str,
    dataset_id: str = "data_profiles",
    table_id: str = "profile_scans"
) -> str:
    """
    Store profile scan results in BigQuery for historical analysis

    Args:
        profile_results: Profile metrics from run_profile_scan
        project_id: GCP project for BigQuery storage
        dataset_id: BigQuery dataset name
        table_id: BigQuery table name

    Returns:
        status: Storage operation status
    """
    from google.cloud import bigquery
    import json
    from datetime import datetime

    print(f"💾 Storing profile results to {project_id}.{dataset_id}.{table_id}")

    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    # Convert profile results to BigQuery rows
    rows_to_insert = []

    scan_metadata = profile_results["scan_metadata"]
    table_metrics = profile_results["table_metrics"]
    column_metrics = profile_results["column_metrics"]

    for column_name, metrics in column_metrics.items():
        row = {
            # Metadata
            "scan_timestamp": scan_metadata["scan_timestamp"],
            "pipeline_run_id": scan_metadata["pipeline_run_id"],
            "pipeline_stage": scan_metadata["pipeline_stage"],
            "table_name": scan_metadata["table_name"],
            "scan_id": scan_metadata["scan_id"],

            # Column info
            "column_name": column_name,
            "data_type": metrics.get("type"),

            # Numeric statistics
            "min_value": metrics.get("min_value"),
            "max_value": metrics.get("max_value"),
            "mean_value": metrics.get("mean_value"),
            "stddev_value": metrics.get("stddev_value"),

            # Quality metrics
            "null_count": int(metrics.get("null_ratio", 0) * table_metrics.get("row_count", 0)),
            "total_count": table_metrics.get("row_count", 0),
            "null_percentage": metrics.get("null_ratio", 0) * 100,

            # Categorical metrics
            "cardinality": metrics.get("unique_count"),
            "unique_count": metrics.get("unique_count"),
            "top_values": metrics.get("top_values", []),

            # Percentiles
            "percentile_5": metrics.get("percentiles", {}).get("p5"),
            "percentile_25": metrics.get("percentiles", {}).get("p25"),
            "percentile_75": metrics.get("percentiles", {}).get("p75"),
            "percentile_95": metrics.get("percentiles", {}).get("p95"),
        }

        # Handle geographic bounds for Chicago taxi data
        if column_name.lower() in ["pickup_latitude", "dropoff_latitude", "pickup_longitude", "dropoff_longitude"]:
            row["geographic_bounds"] = {
                "min_lat": metrics.get("min_value") if "latitude" in column_name.lower() else None,
                "max_lat": metrics.get("max_value") if "latitude" in column_name.lower() else None,
                "min_lon": metrics.get("min_value") if "longitude" in column_name.lower() else None,
                "max_lon": metrics.get("max_value") if "longitude" in column_name.lower() else None,
            }

        rows_to_insert.append(row)

    # Insert into BigQuery
    errors = client.insert_rows_json(table_ref, rows_to_insert)

    if errors:
        raise Exception(f"BigQuery insert errors: {errors}")

    print(f"✅ Stored {len(rows_to_insert)} column profile records")
    return f"Successfully stored {len(rows_to_insert)} profile records"