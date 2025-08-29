# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from unittest import mock
from dataplex_components.profile_scan import run_profile_scan


def test_run_profile_scan_success(mock_dataplex_profile_result):
    """Test successful profile scan execution and metrics extraction"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("time.sleep"):  # Skip the wait time
        
        # Setup mocks
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.side_effect = Exception("Not found")  # First call fails, triggers creation
        mock_client.create_data_scan.return_value.result.return_value = None
        mock_client.list_data_scan_jobs.return_value = [mock_dataplex_profile_result]
        
        # Execute the function
        profile_results, scan_id, metrics_summary = run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.table",
            profile_scan_id="test-scan-123",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline-456"
        )
        
        # Verify results structure
        assert profile_results["scan_metadata"]["scan_id"] == "test-scan-123"
        assert profile_results["scan_metadata"]["pipeline_stage"] == "post-ingestion"
        assert profile_results["table_metrics"]["row_count"] == 1000
        assert profile_results["table_metrics"]["column_count"] == 2
        
        # Verify numeric column metrics
        trip_total_metrics = profile_results["column_metrics"]["trip_total"]
        assert trip_total_metrics["min_value"] == 0.0
        assert trip_total_metrics["max_value"] == 100.0
        assert trip_total_metrics["mean_value"] == 45.5
        assert trip_total_metrics["stddev_value"] == 15.2
        assert trip_total_metrics["null_ratio"] == 0.05
        
        # Verify string column metrics
        payment_type_metrics = profile_results["column_metrics"]["payment_type"]
        assert payment_type_metrics["unique_count"] == 4
        assert payment_type_metrics["top_values"][0]["value"] == "Cash"
        assert payment_type_metrics["top_values"][0]["count"] == 150
        
        # Verify return values
        assert scan_id == "test-scan-123"
        assert metrics_summary["total_columns_profiled"] == 2
        assert metrics_summary["table_row_count"] == 1000
        assert metrics_summary["scan_status"] == "completed"


def test_run_profile_scan_existing_scan(mock_dataplex_profile_result):
    """Test profile scan when scan already exists (no creation needed)"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("time.sleep"):
        
        # Setup mocks - scan already exists
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.return_value = mock.Mock()  # Scan exists
        mock_client.list_data_scan_jobs.return_value = [mock_dataplex_profile_result]
        
        # Execute
        profile_results, scan_id, metrics_summary = run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2", 
            bq_table="test-project.dataset.table",
            profile_scan_id="existing-scan",
            pipeline_stage="post-preprocessing",
            pipeline_run_id="test-pipeline"
        )
        
        # Verify scan creation was NOT called
        mock_client.create_data_scan.assert_not_called()
        
        # Verify results are still correct
        assert scan_id == "existing-scan"
        assert profile_results["scan_metadata"]["pipeline_stage"] == "post-preprocessing"


def test_run_profile_scan_no_job_results():
    """Test profile scan when no job results are found"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("time.sleep"):
        
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.return_value = mock.Mock()
        mock_client.list_data_scan_jobs.return_value = []  # No jobs found
        
        # Should raise exception
        with pytest.raises(Exception, match="No scan job found!"):
            run_profile_scan.python_func(
                project_id="test-project",
                location="europe-west2",
                bq_table="test-project.dataset.table", 
                profile_scan_id="test-scan",
                pipeline_stage="post-ingestion",
                pipeline_run_id="test-pipeline"
            )


def test_run_profile_scan_percentiles_parsing(mock_dataplex_profile_result):
    """Test that percentiles are correctly parsed from quartiles array"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("time.sleep"):
        
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.return_value = mock.Mock()
        mock_client.list_data_scan_jobs.return_value = [mock_dataplex_profile_result]
        
        profile_results, _, _ = run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.table",
            profile_scan_id="test-scan",
            pipeline_stage="post-ingestion", 
            pipeline_run_id="test-pipeline"
        )
        
        # Verify percentiles mapping
        percentiles = profile_results["column_metrics"]["trip_total"]["percentiles"]
        assert percentiles["p5"] == 10.0
        assert percentiles["p25"] == 25.0
        assert percentiles["p50"] == 50.0
        assert percentiles["p75"] == 75.0
        assert percentiles["p95"] == 95.0