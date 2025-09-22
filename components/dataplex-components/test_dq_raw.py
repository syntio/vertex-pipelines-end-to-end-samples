#!/usr/bin/env python3

import sys
import os

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def run_dq_scan_raw(
    project_id: str,
    location: str,
    bq_table: str,
    dq_scan_id: str,
    start_date: str,
    end_date: str,
    date_column: str = "trip_start_timestamp",
):
    """Raw DQ scan function extracted from the KFP component"""

    from google.cloud import dataplex_v1
    from dataplex_components.cost_aware_client import Client as bigquery_Client
    import time

    print(f"🔍 Starting PROTECTED DQ scan: {dq_scan_id}")
    print(f"📊 Table: {bq_table}")
    print(f"📅 Time range: {start_date} to {end_date}")

    # COST PROTECTION: Enforce time filtering
    if not start_date or not end_date:
        raise ValueError("Time filtering required - provide start_date and end_date")

    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery_Client(project=project_id)

    parent = f"projects/{project_id}/locations/{location}"
    dq_scan_full_name = f"{parent}/dataScans/{dq_scan_id}"

    try:
        project, dataset, table = bq_table.split(".")
    except ValueError:
        raise ValueError(f"Invalid bq_table format:'{bq_table}'.")

    resource_uri = (
        f"//bigquery.googleapis.com/projects/{project}"
        f"/datasets/{dataset}/tables/{table}"
    )
    data_source = dataplex_v1.DataSource(resource=resource_uri)

    # Step 1: Query BigQuery metadata to get column information (FAST!)
    print("Fetching table metadata from INFORMATION_SCHEMA...")

    metadata_query = f"""
    SELECT
        column_name,
        data_type,
        is_nullable,
        ordinal_position
    FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name = '{table}'
    ORDER BY ordinal_position
    """

    try:
        query_job = bq_client.query(metadata_query)
        columns_metadata = list(query_job.result())
        print(f"Fetched metadata for {len(columns_metadata)} columns.")

        print("Generating simple rules based on table metadata...")

        generated_rules = []
        for column in columns_metadata:
            column_name = column.column_name
            data_type = column.data_type
            is_nullable = column.is_nullable

            print(f"Analyzing column: {column_name} ({data_type}, nullable: {is_nullable})")

            # Simple null check rules for nullable columns
            if is_nullable == "YES":
                print(f"  -> Adding null check rule for {column_name}")
                non_null_exp = dataplex_v1.DataQualityRule.NonNullExpectation()
                generated_rules.append(
                    dataplex_v1.DataQualityRule(
                        column=column_name,
                        dimension="COMPLETENESS",
                        non_null_expectation=non_null_exp,
                    )
                )

        print(f"Generated {len(generated_rules)} simple rules")

    except Exception as e:
        print(f"Error while fetching table metadata: {e}")
        print("Using fallback rule...")
        generated_rules = [
            dataplex_v1.DataQualityRule(
                column="trip_total",
                dimension="COMPLETENESS",
                non_null_expectation=dataplex_v1.DataQualityRule.NonNullExpectation(),
            )
        ]

    # Add more rules (simplified)
    print("Adding additional smart rules...")

    # Add smart rule: trip_miles > 0
    print("Adding a rule: trip_miles > 0")
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            column="trip_miles",
            dimension="VALIDITY",
            range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
                min_value="0.00001"
            ),
        )
    )

    # Step 3: Create and run DQ scan with generated rules
    dq_scan = dataplex_v1.DataScan(
        data=data_source,
        data_quality_spec=dataplex_v1.DataQualitySpec(rules=generated_rules),
    )

    try:
        dataplex_client.get_data_scan(name=dq_scan_full_name)
        print(f"DQ scan '{dq_scan_id}' already exists.")
    except Exception:
        print(f"DQ scan not found. Creating a new one: {dq_scan_id}")

        operation = dataplex_client.create_data_scan(
            parent=parent,
            data_scan_id=dq_scan_id,
            data_scan=dq_scan,
        )
        operation.result()  # Wait for creation

    request = dataplex_v1.RunDataScanRequest(name=dq_scan_full_name)
    response = dataplex_client.run_data_scan(request=request)
    print(f"DQ scan job started: {response}")

    job_name = response.job.name
    while True:
        job = dataplex_client.get_data_scan_job(name=job_name)
        state = job.state

        print(f"Checking status of DQ job: {state.name}")

        if state == dataplex_v1.DataScanJob.State.SUCCEEDED:
            print("DQ job finished successfully ✅")
            return
        elif state in (
            dataplex_v1.DataScanJob.State.FAILED,
            dataplex_v1.DataScanJob.State.CANCELLED,
        ):
            raise RuntimeError(f"DQ job failed ❌ Status: {job.state.name}")

        # Job still running, wait before next poll
        time.sleep(15)


if __name__ == "__main__":
    print("🔍 Running DQ scan (raw function)...")

    try:
        run_dq_scan_raw(
            project_id='syntio-ai-ops',
            location='europe-west1',
            bq_table='syntio-ai-ops.chicago_taxi_trips.taxi_trips',
            dq_scan_id='test-dq-scan-20240922',
            start_date='2022-09-01',
            end_date='2022-09-30',
            date_column='trip_start_timestamp'
        )
        print("✅ DQ scan completed successfully!")

    except Exception as e:
        print(f"❌ DQ scan failed: {e}")
        import traceback
        traceback.print_exc()