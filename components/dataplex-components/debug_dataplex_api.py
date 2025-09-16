#!/usr/bin/env python3

import os
import sys

# Set environment
os.environ['PROJECT_ID'] = 'syntio-ai-ops'

# Mock the KFP component
class MockComponent:
    def __init__(self, **kwargs):
        pass
    def __call__(self, func):
        func.python_func = func
        return func

sys.modules['kfp'] = type('MockModule', (), {'dsl': type('MockDSL', (), {'component': MockComponent})})()

from google.cloud import dataplex_v1

def debug_dataplex_job_details():
    """Debug what fields are actually available in Dataplex job responses"""

    project_id = "syntio-ai-ops"
    location = "europe-west1"

    # Check the most recent job from our test
    datascan_name = "real-test-1758015732"
    job_id = "71366691-cec0-4ce6-af22-0f8592513983"

    print(f"🔍 Debugging Dataplex job response fields...")
    print(f"📊 DataScan: {datascan_name}")
    print(f"🆔 Job ID: {job_id}")

    try:
        # Initialize client
        client = dataplex_v1.DataScanServiceClient()

        # Get job details
        job_name = f"projects/{project_id}/locations/{location}/dataScans/{datascan_name}/jobs/{job_id}"
        job = client.get_data_scan_job(name=job_name)

        print(f"\n📋 Job Type: {type(job)}")
        print(f"📋 Job State: {job.state}")
        print(f"📋 Job UID: {job.uid}")

        # List all available attributes
        print(f"\n🔍 Available job attributes:")
        for attr in dir(job):
            if not attr.startswith('_'):
                try:
                    value = getattr(job, attr)
                    print(f"   {attr}: {type(value)} = {value if not callable(value) else 'method'}")
                except Exception as e:
                    print(f"   {attr}: Error accessing - {e}")

        # Check specifically for profile results
        print(f"\n🎯 Profile result fields:")
        if hasattr(job, 'data_profile_result'):
            profile_result = job.data_profile_result
            print(f"   data_profile_result: {profile_result}")

            if profile_result:
                print(f"   Profile result type: {type(profile_result)}")
                for attr in dir(profile_result):
                    if not attr.startswith('_'):
                        try:
                            value = getattr(profile_result, attr)
                            print(f"      {attr}: {value if not callable(value) else 'method'}")
                        except Exception as e:
                            print(f"      {attr}: Error - {e}")
        else:
            print("   ❌ No data_profile_result attribute found")

        # Check if there are other result fields
        print(f"\n🔍 Checking for other result fields:")
        result_fields = [attr for attr in dir(job) if 'result' in attr.lower() or 'data' in attr.lower()]
        for field in result_fields:
            try:
                value = getattr(job, field)
                print(f"   {field}: {value if not callable(value) else 'method'}")
            except Exception as e:
                print(f"   {field}: Error - {e}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_dataplex_job_details()