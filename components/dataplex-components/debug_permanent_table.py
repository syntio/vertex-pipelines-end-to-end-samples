#!/usr/bin/env python3

import os
import time

# Set environment
os.environ['PROJECT_ID'] = 'syntio-ai-ops'

# Mock the KFP component for debugging
class MockComponent:
    def __init__(self, **kwargs):
        pass
    def __call__(self, func):
        func.python_func = func
        return func

import sys
sys.modules['kfp'] = type('MockModule', (), {'dsl': type('MockDSL', (), {'component': MockComponent})})()

from google.cloud import dataplex_v1

def test_dataplex_on_permanent_table():
    """Test Dataplex profiling on the permanent partitioned table"""

    project_id = "syntio-ai-ops"
    location = "europe-west1"

    # Use the permanent partitioned table instead of temp view
    permanent_table = f"{project_id}.chicago_taxi_trips.taxi_trips"
    resource_uri = f"//bigquery.googleapis.com/projects/{project_id}/datasets/chicago_taxi_trips/tables/taxi_trips"

    profile_scan_id = f"permanent-table-test-{int(time.time())}"

    print(f"🧪 Testing Dataplex profiling on PERMANENT table")
    print(f"📊 Table: {permanent_table}")
    print(f"🔗 Resource URI: {resource_uri}")

    # Initialize Dataplex client
    dataplex_client = dataplex_v1.DataScanServiceClient()

    # Create Dataplex profile scan
    parent = f"projects/{project_id}/locations/{location}"
    data_source = dataplex_v1.DataSource(resource=resource_uri)

    profile_scan = dataplex_v1.DataScan(
        data=data_source, data_profile_spec=dataplex_v1.DataProfileSpec()
    )

    scan_full_name = f"{parent}/dataScans/{profile_scan_id}"

    try:
        print(f"📝 Creating profile scan: {profile_scan_id}")
        operation = dataplex_client.create_data_scan(
            parent=parent, data_scan_id=profile_scan_id, data_scan=profile_scan
        )
        operation.result()  # Wait for creation
        print(f"✅ Created profile scan: {profile_scan_id}")

        # Run the profile scan
        print("🚀 Running profile scan on permanent table...")
        run_request = dataplex_v1.RunDataScanRequest(name=scan_full_name)
        run_response = dataplex_client.run_data_scan(request=run_request)

        print("⏳ Waiting for scan completion...")
        time.sleep(90)  # Wait longer for full table

        # Get scan results
        jobs = dataplex_client.list_data_scan_jobs(parent=scan_full_name)
        latest_job = None
        for job in jobs:
            if latest_job is None or job.start_time > latest_job.start_time:
                latest_job = job

        if latest_job:
            print(f"📋 Job state: {latest_job.state.name}")

            if hasattr(latest_job, 'message') and latest_job.message:
                print(f"📝 Job message: {latest_job.message}")

            if latest_job.data_profile_result:
                profile = latest_job.data_profile_result.profile
                print(f"✅ PERMANENT TABLE SUCCESS!")
                print(f"📊 Row count: {profile.row_count:,}")
                print(f"📋 Field count: {len(profile.fields) if profile.fields else 0}")
            else:
                print(f"❌ PERMANENT TABLE ALSO HAS NO RESULTS!")
                print(f"   Job succeeded but no data_profile_result")
        else:
            print("❌ No job found")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dataplex_on_permanent_table()