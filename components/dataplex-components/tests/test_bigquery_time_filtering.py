"""
Real integration tests using actual GCP resources and 211M row dataset.
Tests time filtering protection with real BigQuery/Dataplex calls.
"""

import pytest
import os
import time
from dataplex_components.profile_scan import run_profile_scan
from dataplex_components.dq_scan import run_scan
from dataplex_components.protected_access import protected_table_access


@pytest.mark.integration
def test_real_protected_table_access():
    """Test protected access creates real filtered view on 211M row dataset"""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        pytest.skip("PROJECT_ID not set - source env.dev.sh first")

    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    # Test single day filter (should be ~700K rows instead of 211M)
    with protected_table_access(
        bq_table=big_table, start_date="2022-09-01", end_date="2022-09-01"
    ) as filtered_view:
        print(f"Created filtered view: {filtered_view}")
        assert "filtered_" in filtered_view
        assert "syntio-ai-ops" in filtered_view

        # TODO: Add BigQuery client check that view exists and has correct row count


@pytest.mark.integration
def test_real_profile_scan_cost_protection():
    """Test profile scan with real 211M dataset using time filtering"""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        pytest.skip("PROJECT_ID not set - source env.dev.sh first")

    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    # Profile single day only - should cost ~€0.05 instead of €0.60
    profile_results, scan_id, metrics = run_profile_scan.python_func(
        project_id=project_id,
        location="europe-west1",
        bq_table=big_table,
        profile_scan_id=f"real-test-{int(time.time())}",
        pipeline_stage="test",
        pipeline_run_id="integration-test",
        start_date="2022-09-01",
        end_date="2022-09-01",
    )

    print(f"✅ Profile scan completed: {scan_id}")
    print(f"📊 Row count scanned: {metrics.get('table_row_count', 'unknown')}")

    # Verify we got real results
    assert profile_results["table_metrics"]["row_count"] > 0
    assert (
        profile_results["table_metrics"]["row_count"] < 1000000
    )  # Should be much less than 211M


@pytest.mark.integration
def test_real_dq_scan_cost_protection():
    """Test DQ scan with real 211M dataset using time filtering"""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        pytest.skip("PROJECT_ID not set - source env.dev.sh first")

    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    # DQ scan single day only
    scan_result = run_scan.python_func(
        project_id=project_id,
        location="europe-west1",
        bq_table=big_table,
        dq_scan_id=f"real-dq-test-{int(time.time())}",
        start_date="2022-09-01",
        end_date="2022-09-01",
    )

    print(f"✅ DQ scan completed: {scan_result}")


@pytest.mark.integration
def test_cost_protection_prevents_full_scan():
    """Verify protection mechanism blocks expensive full-table access"""
    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        pytest.skip("PROJECT_ID not set")

    big_table = f"{project_id}.chicago_taxi_trips.taxi_trips"

    # This should FAIL - no time filtering provided
    with pytest.raises(ValueError, match="Time filtering required"):
        run_profile_scan.python_func(
            project_id=project_id, bq_table=big_table, profile_scan_id="should-fail"
        )

    print("✅ Cost protection working - blocked expensive scan")
