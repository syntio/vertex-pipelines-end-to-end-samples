#!/usr/bin/env python3

import os
import time

# Set environment
os.environ["PROJECT_ID"] = "syntio-ai-ops"


# Mock the KFP component for debugging
class MockComponent:
    def __init__(self, **kwargs):
        pass

    def __call__(self, func):
        func.python_func = func
        return func


import sys

sys.modules["kfp"] = type(
    "MockModule", (), {"dsl": type("MockDSL", (), {"component": MockComponent})}
)()

# Now import our modules
from src.dataplex_components.protected_access import protected_table_access
from google.cloud import dataplex_v1


def debug_dataplex_scan():
    """Debug what happens during Dataplex profiling of temporary view"""

    project_id = "syntio-ai-ops"
    location = "europe-west1"
    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"
    profile_scan_id = f"debug-scan-{int(time.time())}"

    print(f"🔍 DEBUG: Starting Dataplex scan debugging")
    print(f"📊 Table: {big_table}")
    print(f"📍 Location: {location}")

    # Initialize Dataplex client
    dataplex_client = dataplex_v1.DataScanServiceClient()

    # Use protected table access
    with protected_table_access(
        bq_table=big_table,
        start_date="2022-09-01",
        end_date="2022-09-01",
        date_column="trip_start_timestamp",
        project_id=project_id,
    ) as filtered_view_name:

        print(f"🔒 Created filtered view: {filtered_view_name}")

        # Parse filtered view reference for Dataplex
        project, dataset, table = filtered_view_name.replace("`", "").split(".")
        resource_uri = f"//bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}"

        print(f"🔗 Dataplex resource URI: {resource_uri}")

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
        print("📈 Getting scan job results...")
        jobs = dataplex_client.list_data_scan_jobs(parent=scan_full_name)
        latest_job = None
        job_count = 0

        for job in jobs:
            job_count += 1
            print(f"📄 Job {job_count}: {job.name}")
            print(f"   State: {job.state.name}")
            print(f"   Start: {job.start_time}")
            if hasattr(job, "end_time") and job.end_time:
                print(f"   End: {job.end_time}")

            if latest_job is None or job.start_time > latest_job.start_time:
                latest_job = job

        if not latest_job:
            print("❌ No scan job found!")
            return

        print(f"\n🎯 Latest job state: {latest_job.state.name}")

        if hasattr(latest_job, "message") and latest_job.message:
            print(f"📝 Job message: {latest_job.message}")

        if latest_job.data_profile_result:
            profile = latest_job.data_profile_result.profile
            print(f"✅ Profile result found!")
            print(f"📊 Row count: {profile.row_count}")
            print(f"📋 Field count: {len(profile.fields) if profile.fields else 0}")

            if profile.fields:
                for i, field in enumerate(profile.fields[:3]):  # Show first 3 fields
                    print(f"   Field {i+1}: {field.name} ({field.type_})")
        else:
            print("❌ No data_profile_result found!")
            print("🔍 Checking job details...")
            print(f"   Job type: {type(latest_job)}")
            print(
                f"   Available attributes: {[attr for attr in dir(latest_job) if not attr.startswith('_')]}"
            )


if __name__ == "__main__":
    debug_dataplex_scan()
