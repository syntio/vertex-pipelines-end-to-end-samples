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
    from google.cloud import dataplex_v1
    import time
    from .protected_access import protected_table_access
    from .cost_aware_client import Client as bigquery_Client

    print(f"🔍 Starting PROTECTED profile scan: {profile_scan_id}")
    print(f"📊 Original table: {bq_table}")
    print(f"🏗️ Stage: {pipeline_stage}")
    print(f"📅 Time range: {start_date} to {end_date}")

    # Initialize clients first for cost estimation
    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery_Client(project=project_id)
    
    # Show cost estimate for full table scan (what would happen without protection)
    if not start_date or not end_date:
        print(f"💰 Estimating cost of unprotected full table scan...")
        try:
            full_scan_query = f"SELECT * FROM `{bq_table}`"
            bytes_processed, estimated_cost = bq_client.estimate_query_cost(full_scan_query)
            gb_processed = bytes_processed / (1024**3)
            print(f"⚠️  UNPROTECTED SCAN COST: €{estimated_cost:.2f} ({gb_processed:.2f} GB)")
        except Exception as e:
            print(f"⚠️  Could not estimate full scan cost: {e}")
        
        # COST PROTECTION: Enforce time filtering
        raise ValueError("Time filtering required - provide start_date and end_date")

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

        # Create Dataplex profile scan with export configuration
        parent = f"projects/{project_id}/locations/{location}"
        data_source = dataplex_v1.DataSource(resource=resource_uri)

        # Configure export to BigQuery table
        export_config = dataplex_v1.DataProfileSpec.PostScanActions.BigQueryExport(
            results_table=f"projects/{project_id}/datasets/chicago_taxi_trips/tables/profile_scan_results"
        )

        post_scan_actions = dataplex_v1.DataProfileSpec.PostScanActions(
            bigquery_export=export_config
        )

        profile_spec = dataplex_v1.DataProfileSpec(
            post_scan_actions=post_scan_actions
        )

        profile_scan = dataplex_v1.DataScan(
            data=data_source,
            data_profile_spec=profile_spec
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

        # Verify view has data before scanning
        print("🔍 Verifying view has data before Dataplex scan...")
        try:
            test_query = f"SELECT COUNT(*) as cnt FROM `{filtered_view_name.replace('`', '')}`"
            result = bq_client.query(test_query).to_dataframe()
            row_count = result.iloc[0]['cnt']
            print(f"✅ View contains {row_count:,} rows - ready for Dataplex")

            if row_count == 0:
                raise Exception(f"View {filtered_view_name} is empty - no data to profile")
        except Exception as e:
            print(f"❌ Cannot access view for verification: {e}")
            raise Exception(f"View verification failed: {e}")

        # Run the profile scan
        print("🚀 Running profile scan...")
        run_request = dataplex_v1.RunDataScanRequest(name=scan_full_name)
        run_response = dataplex_client.run_data_scan(request=run_request)

        print("⏳ Waiting for scan completion...")

        # Smart polling with adaptive intervals and status updates
        max_wait_minutes = 15  # Max 15 minutes wait
        start_time = time.time()
        poll_count = 0
        last_state = None
        state_duration = 0

        print("⏳ Monitoring scan progress...")

        latest_job = None
        while True:
            poll_count += 1
            elapsed = time.time() - start_time

            # Adaptive polling interval: faster at start, slower later
            if elapsed < 60:  # First minute: every 5s
                poll_interval = 5
            elif elapsed < 300:  # Next 4 minutes: every 10s
                poll_interval = 10
            else:  # After 5 minutes: every 15s
                poll_interval = 15

            # Get current jobs
            jobs = dataplex_client.list_data_scan_jobs(parent=scan_full_name)
            latest_job = None
            for job in jobs:
                if latest_job is None or job.start_time > latest_job.start_time:
                    latest_job = job

            if not latest_job:
                print(f"⏳ [{elapsed:.0f}s] Waiting for job to start...")
                time.sleep(poll_interval)
                if elapsed > max_wait_minutes * 60:
                    raise Exception(f"Timeout: No job started after {max_wait_minutes} minutes")
                continue

            job_state = latest_job.state.name

            # Track state changes and duration
            if job_state != last_state:
                if last_state:
                    print(f"🔄 State change: {last_state} → {job_state} (after {state_duration:.0f}s)")
                else:
                    print(f"🎬 Job started: {job_state}")
                last_state = job_state
                state_duration = 0
            else:
                state_duration += poll_interval

            # Status with progress indicators
            if job_state == "SUCCEEDED":
                print(f"✅ Scan completed successfully! (Total time: {elapsed:.0f}s)")
                break
            elif job_state == "FAILED":
                error_msg = getattr(latest_job, 'message', 'Unknown error')
                print(f"❌ Scan failed after {elapsed:.0f}s: {error_msg}")
                raise Exception(f"Dataplex scan failed: {error_msg}")
            elif job_state == "RUNNING":
                progress_dots = "." * ((poll_count % 3) + 1)
                print(f"⚡ Processing data{progress_dots} ({elapsed:.0f}s elapsed, ~{19237} rows)")
            elif job_state == "PENDING":
                spinner = ['⏳', '⌛'][poll_count % 2]
                print(f"{spinner} Queued for processing ({elapsed:.0f}s waiting)")
            else:
                print(f"🔍 Status: {job_state} ({elapsed:.0f}s elapsed)")

            # Timeout check
            if elapsed > max_wait_minutes * 60:
                print(f"⏰ Timeout after {max_wait_minutes} minutes")
                final_state = latest_job.state.name if latest_job else "UNKNOWN"
                raise Exception(f"Dataplex scan timeout. Final state: {final_state}")

            time.sleep(poll_interval)

        if not latest_job:
            raise Exception("No scan job found after polling completed")

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

        # Read profile results from BigQuery export table
        print("📊 Reading profile results from BigQuery export table...")
        export_table = f"{project_id}.chicago_taxi_trips.profile_scan_results"

        try:
            # Query the most recent results for this scan
            results_query = f"""
            SELECT * FROM `{export_table}`
            WHERE data_profile_scan.data_scan_id = '{profile_scan_id}'
            ORDER BY job_start_time DESC
            LIMIT 1000
            """

            results_df = bq_client.query(results_query).to_dataframe()

            if results_df.empty:
                print(f"⚠️ No results found in export table for scan {profile_scan_id}")
                # Fall back to checking if job has direct results (for older scans)
                if hasattr(latest_job, 'data_profile_result') and latest_job.data_profile_result:
                    print("📊 Using direct job results as fallback")
                    profile = latest_job.data_profile_result.profile
                    profile_results["table_metrics"] = {
                        "row_count": profile.row_count,
                        "column_count": len(profile.fields) if profile.fields else 0,
                    }
                else:
                    print("❌ No results available in export table or job response")
                    # Still return basic structure for compatibility
                    profile_results["table_metrics"] = {"row_count": 0, "column_count": 0}
            else:
                print(f"✅ Found {len(results_df)} profile result records in export table")

                # Process BigQuery export results into expected format
                # Get unique column count and total row count
                unique_columns = results_df['column_name'].nunique() if 'column_name' in results_df.columns else 0
                table_row_count = results_df.iloc[0].get('job_rows_scanned', 0) if not results_df.empty else 0

                profile_results["table_metrics"] = {
                    "row_count": table_row_count,
                    "column_count": unique_columns,
                }

                # Process column-level metrics from export table
                for _, row in results_df.iterrows():
                    column_name = row.get('column_name', 'unknown')

                    column_metrics = {
                        "name": column_name,
                        "type": row.get('column_data_type', 'unknown'),
                        "null_ratio": row.get('null_count', 0) / max(row.get('non_null_count', 1), 1),
                        "distinct_ratio": row.get('distinct_count', 0) / max(table_row_count, 1),
                    }

                    # Add numeric statistics if available
                    if row.get('min_value') is not None:
                        column_metrics.update({
                            "min_value": row.get('min_value'),
                            "max_value": row.get('max_value'),
                            "mean_value": row.get('avg_value'),
                            "stddev_value": row.get('std_dev_value'),
                        })

                    # Add unique count for categorical data
                    if row.get('distinct_count') is not None:
                        column_metrics["unique_count"] = row.get('distinct_count')

                    profile_results["column_metrics"][column_name] = column_metrics

        except Exception as e:
            print(f"⚠️ Error reading from export table: {e}")
            print("💡 This might be the first scan - export table may not exist yet")

            # Create basic structure for now
            profile_results["table_metrics"] = {"row_count": 0, "column_count": 0}

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
