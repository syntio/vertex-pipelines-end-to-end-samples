from kfp import dsl
from typing import NamedTuple, Optional


@dsl.component(
    base_image="europe-west2-docker.pkg.dev/PROJECT_ID/ml-pipeline-containers/ml-pipeline-base:latest",
    packages_to_install=[
        "google-cloud-dataplex>=1.0.0",
        "google-cloud-bigquery>=3.25.0",
    ],
)
def run_profile_scan(
    project_id: str,
    location: str = "europe-west2",
    bq_table: str = "",  # Format: "project.dataset.table"
    profile_scan_id: str = "",
    pipeline_stage: str = "post-ingestion",  # "post-ingestion" | "post-preprocessing"
    pipeline_run_id: str = "",
    # TIME FILTERING PARAMETERS (REQUIRED)
    start_date: str = "",  # YYYY-MM-DD format (MANDATORY)
    end_date: str = "",    # YYYY-MM-DD format (MANDATORY)
    date_column: str = "trip_start_timestamp",  # Column to filter on
) -> NamedTuple(
    "Outputs",
    [("profile_results", dict), ("profile_scan_id", str), ("metrics_summary", dict)],
):
    """
    Run Dataplex profile scan with MANDATORY time filtering for cost protection.
    
    Creates temporary filtered view and profiles only the specified time range.
    Prevents expensive full-table scans on 211M row datasets.

    Args:
        project_id: GCP project ID
        location: GCP region for Dataplex scan
        bq_table: BigQuery table to profile (format: project.dataset.table)
        profile_scan_id: Unique ID for this profile scan
        pipeline_stage: Stage when profiling occurs
        pipeline_run_id: Pipeline execution ID for tracking
        start_date: Start date for filtering (YYYY-MM-DD) - REQUIRED
        end_date: End date for filtering (YYYY-MM-DD) - REQUIRED  
        date_column: Column to filter on (default: trip_start_timestamp)

    Returns:
        profile_results: Detailed profiling metrics for time-filtered data
        profile_scan_id: ID of created scan
        metrics_summary: High-level summary metrics
        
    Raises:
        ValueError: If start_date or end_date not provided (cost protection)
    """
    from google.cloud import dataplex_v1, bigquery
    import time
    from .protected_access import protected_table_access

    print(f"🔍 Starting PROTECTED profile scan: {profile_scan_id}")
    print(f"📊 Original table: {bq_table}")
    print(f"🏗️ Stage: {pipeline_stage}")
    print(f"📅 Time range: {start_date} to {end_date}")

    # COST PROTECTION: Enforce time filtering
    if not start_date or not end_date:
        raise ValueError("Time filtering required - provide start_date and end_date")

    # Initialize clients
    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery.Client(project=project_id)

    # Use protected table access with time filtering
    with protected_table_access(
        bq_table=bq_table,
        start_date=start_date,
        end_date=end_date,
        date_column=date_column,
        project_id=project_id
    ) as filtered_view_name:
        
        print(f"🔒 Using filtered view: {filtered_view_name}")
        
        # Parse filtered view reference for Dataplex
        project, dataset, table = filtered_view_name.replace('`', '').split(".")
        resource_uri = f"//bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}"

        # Create Dataplex profile scan
        parent = f"projects/{project_id}/locations/{location}"
        data_source = dataplex_v1.DataSource(resource=resource_uri)

        profile_scan = dataplex_v1.DataScan(
            data=data_source, data_profile_spec=dataplex_v1.DataProfileSpec()
        )

        scan_full_name = f"{parent}/dataScans/{profile_scan_id}"

        try:
            # Check if scan already exists
            existing_scan = dataplex_client.get_data_scan(name=scan_full_name)
            print(f"✅ Profile scan '{profile_scan_id}' already exists")
        except Exception:
            print(f"📝 Creating new profile scan: {profile_scan_id}")
            operation = dataplex_client.create_data_scan(
                parent=parent, data_scan_id=profile_scan_id, data_scan=profile_scan
            )
            operation.result()  # Wait for creation
            print(f"✅ Created profile scan: {profile_scan_id}")

        # Run the profile scan
        print("🚀 Running profile scan...")
        run_request = dataplex_v1.RunDataScanRequest(name=scan_full_name)
        run_response = dataplex_client.run_data_scan(request=run_request)

        print("⏳ Waiting for scan completion...")
        time.sleep(60)  # Wait for scan to complete

        # Get scan results
        jobs = dataplex_client.list_data_scan_jobs(parent=scan_full_name)
        latest_job = None
        for job in jobs:
            if latest_job is None or job.start_time > latest_job.start_time:
                latest_job = job

        if not latest_job:
            raise Exception("No scan job found!")

        print("📈 Processing scan results...")

        # Extract comprehensive metrics
        profile_results = {
            "scan_metadata": {
                "scan_id": profile_scan_id,
                "table_name": bq_table,
                "pipeline_stage": pipeline_stage,
                "pipeline_run_id": pipeline_run_id,
                "scan_timestamp": latest_job.start_time.isoformat(),
                "job_state": latest_job.state.name,
            },
            "table_metrics": {},
            "column_metrics": {},
        }

        if latest_job.data_profile_result:
            profile = latest_job.data_profile_result.profile

            # Table-level metrics
            profile_results["table_metrics"] = {
                "row_count": profile.row_count,
                "column_count": len(profile.fields) if profile.fields else 0,
            }

            # Column-level metrics
            if profile.fields:
                for field in profile.fields:
                    column_name = field.name
                    column_metrics = {
                        "name": column_name,
                        "type": field.type_,
                        "mode": field.mode,
                    }

                    if field.profile:
                        prof = field.profile

                        # Null statistics
                        column_metrics.update(
                            {
                                "null_ratio": prof.null_ratio,
                                "distinct_ratio": prof.distinct_ratio,
                            }
                        )

                        # Numeric statistics
                        if hasattr(prof, "double_profile") and prof.double_profile:
                            dp = prof.double_profile
                            column_metrics.update(
                                {
                                    "min_value": dp.min,
                                    "max_value": dp.max,
                                    "mean_value": dp.mean,
                                    "stddev_value": dp.standard_deviation,
                                    "percentiles": {
                                        "p5": dp.quartiles[0] if dp.quartiles else None,
                                        "p25": (
                                            dp.quartiles[1]
                                            if len(dp.quartiles) > 1
                                            else None
                                        ),
                                        "p50": (
                                            dp.quartiles[2]
                                            if len(dp.quartiles) > 2
                                            else None
                                        ),
                                        "p75": (
                                            dp.quartiles[3]
                                            if len(dp.quartiles) > 3
                                            else None
                                        ),
                                        "p95": (
                                            dp.quartiles[4]
                                            if len(dp.quartiles) > 4
                                            else None
                                        ),
                                    },
                                }
                            )

                        # String/Categorical statistics
                        if hasattr(prof, "string_profile") and prof.string_profile:
                            sp = prof.string_profile
                            top_values = []
                            if sp.top_n_values:
                                for tv in sp.top_n_values:
                                    top_values.append(
                                        {"value": tv.value, "count": tv.count}
                                    )

                            column_metrics.update(
                                {"unique_count": sp.unique_count, "top_values": top_values}
                            )

                    profile_results["column_metrics"][column_name] = column_metrics

        # Generate metrics summary with time filtering info
        metrics_summary = {
            "total_columns_profiled": len(profile_results["column_metrics"]),
            "table_row_count": profile_results["table_metrics"].get("row_count", 0),
            "pipeline_stage": pipeline_stage,
            "scan_status": (
                "completed" if latest_job.state.name == "SUCCEEDED" else "failed"
            ),
            "time_filtered": True,
            "filter_start_date": start_date,
            "filter_end_date": end_date,
            "filter_column": date_column
        }

        print("✅ PROTECTED profile scan completed successfully!")
        print(f"📊 Profiled {metrics_summary['total_columns_profiled']} columns")
        print(f"🔢 Filtered table has {metrics_summary['table_row_count']} rows")
        print(f"📅 Time range: {start_date} to {end_date}")

        return profile_results, profile_scan_id, metrics_summary
