#!/usr/bin/env python3

import os
import time

# Set environment
os.environ['PROJECT_ID'] = 'syntio-ai-ops'

# Mock the KFP component
class MockComponent:
    def __init__(self, **kwargs):
        pass
    def __call__(self, func):
        func.python_func = func
        return func

import sys
sys.modules['kfp'] = type('MockModule', (), {'dsl': type('MockDSL', (), {'component': MockComponent})})()

from google.cloud import dataplex_v1

def test_original_dataplex_approach():
    """Test Dataplex exactly like the original code - no time filtering, direct table access"""

    project_id = "syntio-ai-ops"
    location = "europe-west1"

    # Use the permanent partitioned table - EXACTLY like original code
    bq_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    # Parse table for resource URI
    project, dataset, table = bq_table.split(".")
    resource_uri = f"//bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}"

    profile_scan_id = f"original-approach-test-{int(time.time())}"

    print(f"🧪 Testing ORIGINAL Dataplex approach (no time filtering)")
    print(f"📊 Table: {bq_table}")
    print(f"🔗 Resource URI: {resource_uri}")

    try:
        # Initialize Dataplex client
        dataplex_client = dataplex_v1.DataScanServiceClient()

        # Create Dataplex profile scan - EXACTLY like original
        parent = f"projects/{project_id}/locations/{location}"
        data_source = dataplex_v1.DataSource(resource=resource_uri)

        profile_scan = dataplex_v1.DataScan(
            data=data_source, data_profile_spec=dataplex_v1.DataProfileSpec()
        )

        scan_full_name = f"{parent}/dataScans/{profile_scan_id}"

        print(f"📝 Creating original-style profile scan: {profile_scan_id}")
        operation = dataplex_client.create_data_scan(
            parent=parent, data_scan_id=profile_scan_id, data_scan=profile_scan
        )
        operation.result()  # Wait for creation
        print(f"✅ Created profile scan: {profile_scan_id}")

        # Run the profile scan
        print("🚀 Running profile scan on full table (like original code)...")
        run_request = dataplex_v1.RunDataScanRequest(name=scan_full_name)
        run_response = dataplex_client.run_data_scan(request=run_request)

        print("⏳ Waiting for scan completion...")
        max_wait_minutes = 15  # Longer for full table
        poll_interval = 15  # Longer intervals
        max_polls = (max_wait_minutes * 60) // poll_interval

        for poll_count in range(max_polls):
            print(f"🔍 Polling status ({poll_count + 1}/{max_polls})...")

            # Get current jobs
            jobs = dataplex_client.list_data_scan_jobs(parent=scan_full_name)
            latest_job = None
            for job in jobs:
                if latest_job is None or job.start_time > latest_job.start_time:
                    latest_job = job

            if not latest_job:
                print("⚠️ No job found yet, waiting...")
                time.sleep(poll_interval)
                continue

            job_state = latest_job.state.name
            print(f"📋 Job state: {job_state}")

            if job_state == "SUCCEEDED":
                print("✅ Original approach scan completed!")

                if hasattr(latest_job, 'data_profile_result') and latest_job.data_profile_result:
                    profile = latest_job.data_profile_result.profile
                    print(f"🎯 SUCCESS! Original approach works!")
                    print(f"📊 Row count: {profile.row_count:,}")
                    print(f"📋 Field count: {len(profile.fields) if profile.fields else 0}")
                else:
                    print(f"❌ Even original approach fails - no data_profile_result")
                    print(f"   This suggests a deeper Dataplex service issue")
                break
            elif job_state == "FAILED":
                error_msg = getattr(latest_job, 'message', 'Unknown error')
                print(f"❌ Original approach failed: {error_msg}")
                break
            elif job_state in ["RUNNING", "PENDING", "ACTIVE"]:
                print(f"⏳ Scan still {job_state.lower()}, waiting {poll_interval}s...")
                time.sleep(poll_interval)
                continue
            else:
                print(f"⚠️ Unknown job state: {job_state}, waiting...")
                time.sleep(poll_interval)
                continue
        else:
            print(f"❌ Timeout after {max_wait_minutes} minutes")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_original_dataplex_approach()