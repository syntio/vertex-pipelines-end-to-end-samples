#!/usr/bin/env python3

import os
import time

# Set environment
os.environ['PROJECT_ID'] = 'syntio-ai-ops'

# Mock the KFP component for testing
class MockComponent:
    def __init__(self, **kwargs):
        pass
    def __call__(self, func):
        func.python_func = func
        return func

import sys
sys.modules['kfp'] = type('MockModule', (), {'dsl': type('MockDSL', (), {'component': MockComponent})})()

# Import the fixed profile scan
from src.dataplex_components.profile_scan import run_profile_scan

def test_fixed_profile_scan():
    """Test the fixed profile scan with synchronous waiting"""

    project_id = "syntio-ai-ops"
    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    print("🧪 Testing fixed Dataplex profiling with synchronous scan waiting...")
    print(f"📊 Table: {big_table}")
    print(f"📅 Date: 2022-09-01")

    try:
        # Test the fixed profile scan
        profile_results, scan_id, metrics = run_profile_scan.python_func(
            project_id=project_id,
            location="europe-west1",
            bq_table=big_table,
            profile_scan_id=f"fix-test-{int(time.time())}",
            pipeline_stage="test",
            pipeline_run_id="manual-test",
            start_date="2022-09-01",
            end_date="2022-09-01"
        )

        print(f"✅ Profile scan completed: {scan_id}")
        print(f"📊 Row count scanned: {metrics.get('table_row_count', 'unknown')}")

        # Check if we got real results
        if "row_count" in profile_results["table_metrics"]:
            row_count = profile_results["table_metrics"]["row_count"]
            print(f"🎯 SUCCESS: Got {row_count} rows in profile results")

            if row_count > 0 and row_count < 1000000:
                print("✅ Row count looks correct (filtered, not full table)")
            else:
                print(f"⚠️ Row count seems wrong: {row_count}")
        else:
            print("❌ FAILURE: No row_count in table_metrics")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fixed_profile_scan()