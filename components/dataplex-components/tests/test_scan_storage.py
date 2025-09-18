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
from dataplex_components.scan_storage import store_profile_results


def test_store_profile_results_success(sample_profile_results):
    """Test successful storage of profile results to BigQuery"""

    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []  # No errors

        result = store_profile_results.python_func(
            profile_results=sample_profile_results,
            project_id="test-project",
            dataset_id="data_profiles",
            table_id="profile_scans",
        )

        # Verify function returned success message
        assert "Successfully stored 2 profile records" in result

        # Verify BigQuery insert was called
        mock_client.insert_rows_json.assert_called_once()

        # Get the inserted rows to verify format
        call_args = mock_client.insert_rows_json.call_args
        table_ref, rows = call_args[0]

        assert table_ref == "test-project.data_profiles.profile_scans"
        assert len(rows) == 2  # Two columns in sample data

        # Verify row format for numeric column
        trip_total_row = next(row for row in rows if row["column_name"] == "trip_total")

        # Metadata fields
        assert (
            trip_total_row["scan_timestamp"]
            == sample_profile_results["scan_metadata"]["scan_timestamp"]
        )
        assert trip_total_row["pipeline_run_id"] == "test-pipeline-run-456"
        assert trip_total_row["pipeline_stage"] == "post-ingestion"
        assert trip_total_row["table_name"] == "project-id.preprocessing.test_table"
        assert trip_total_row["scan_id"] == "test-scan-123"

        # Column info
        assert trip_total_row["column_name"] == "trip_total"
        assert trip_total_row["data_type"] == "FLOAT64"

        # Numeric statistics
        assert trip_total_row["min_value"] == 0.0
        assert trip_total_row["max_value"] == 100.0
        assert trip_total_row["mean_value"] == 45.5
        assert trip_total_row["stddev_value"] == 15.2

        # Quality metrics (calculated from ratios)
        assert trip_total_row["null_count"] == 50  # 0.05 * 1000 rows
        assert trip_total_row["total_count"] == 1000
        assert trip_total_row["null_percentage"] == 5.0  # 0.05 * 100

        # Percentiles
        assert trip_total_row["percentile_5"] == 10.0
        assert trip_total_row["percentile_25"] == 25.0
        assert trip_total_row["percentile_75"] == 75.0
        assert trip_total_row["percentile_95"] == 95.0


def test_store_profile_results_string_column(sample_profile_results):
    """Test storage of string/categorical column metrics"""

    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []

        store_profile_results.python_func(
            profile_results=sample_profile_results, project_id="test-project"
        )

        # Get the inserted rows
        call_args = mock_client.insert_rows_json.call_args
        rows = call_args[0][1]

        # Find string column row
        payment_type_row = next(
            row for row in rows if row["column_name"] == "payment_type"
        )

        # Verify categorical metrics
        assert payment_type_row["cardinality"] == 4
        assert payment_type_row["unique_count"] == 4
        assert payment_type_row["top_values"] == [{"value": "Cash", "count": 150}]

        # Verify null calculation for string column
        assert payment_type_row["null_count"] == 20  # 0.02 * 1000 rows
        assert payment_type_row["null_percentage"] == 2.0  # 0.02 * 100


def test_store_profile_results_geographic_columns():
    """Test storage of geographic columns with bounds data"""

    # Create profile results with geographic columns
    geo_profile_results = {
        "scan_metadata": {
            "scan_id": "geo-scan",
            "table_name": "test-table",
            "pipeline_stage": "post-ingestion",
            "pipeline_run_id": "geo-pipeline",
            "scan_timestamp": "2024-01-15T10:30:00+00:00",
            "job_state": "SUCCEEDED",
        },
        "table_metrics": {"row_count": 500, "column_count": 2},
        "column_metrics": {
            "pickup_latitude": {
                "name": "pickup_latitude",
                "type": "FLOAT64",
                "min_value": 41.8,
                "max_value": 42.0,
                "mean_value": 41.9,
                "null_ratio": 0.01,
            },
            "pickup_longitude": {
                "name": "pickup_longitude",
                "type": "FLOAT64",
                "min_value": -87.8,
                "max_value": -87.5,
                "mean_value": -87.65,
                "null_ratio": 0.01,
            },
        },
    }

    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []

        store_profile_results.python_func(
            profile_results=geo_profile_results, project_id="test-project"
        )

        # Get inserted rows
        call_args = mock_client.insert_rows_json.call_args
        rows = call_args[0][1]

        # Find latitude row
        lat_row = next(row for row in rows if row["column_name"] == "pickup_latitude")
        assert lat_row["geographic_bounds"]["min_lat"] == 41.8
        assert lat_row["geographic_bounds"]["max_lat"] == 42.0
        assert lat_row["geographic_bounds"]["min_lon"] is None  # Not longitude column

        # Find longitude row
        lon_row = next(row for row in rows if row["column_name"] == "pickup_longitude")
        assert lon_row["geographic_bounds"]["min_lon"] == -87.8
        assert lon_row["geographic_bounds"]["max_lon"] == -87.5
        assert lon_row["geographic_bounds"]["min_lat"] is None  # Not latitude column


def test_store_profile_results_bigquery_error(sample_profile_results):
    """Test handling of BigQuery insertion errors"""

    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = [{"error": "Invalid schema"}]

        # Should raise exception on BigQuery errors
        with pytest.raises(Exception, match="BigQuery insert errors"):
            store_profile_results.python_func(
                profile_results=sample_profile_results, project_id="test-project"
            )


def test_store_profile_results_empty_metrics():
    """Test storage with empty column metrics"""

    empty_profile_results = {
        "scan_metadata": {
            "scan_id": "empty-scan",
            "table_name": "empty-table",
            "pipeline_stage": "post-ingestion",
            "pipeline_run_id": "empty-pipeline",
            "scan_timestamp": "2024-01-15T10:30:00+00:00",
            "job_state": "SUCCEEDED",
        },
        "table_metrics": {"row_count": 0, "column_count": 0},
        "column_metrics": {},
    }

    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []

        result = store_profile_results.python_func(
            profile_results=empty_profile_results, project_id="test-project"
        )

        # Should handle empty data gracefully
        assert "Successfully stored 0 profile records" in result

        # Verify empty list was passed to BigQuery
        call_args = mock_client.insert_rows_json.call_args
        rows = call_args[0][1]
        assert len(rows) == 0
