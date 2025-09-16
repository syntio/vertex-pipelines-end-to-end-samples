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
from datetime import datetime, timezone


@pytest.fixture
def mock_dataplex_profile_result():
    """Mock Dataplex profile scan result for testing"""

    # Create mock objects for nested profile structure
    mock_quartiles = [10.0, 25.0, 50.0, 75.0, 95.0]

    mock_double_profile = mock.Mock()
    mock_double_profile.min = 0.0
    mock_double_profile.max = 100.0
    mock_double_profile.mean = 45.5
    mock_double_profile.standard_deviation = 15.2
    mock_double_profile.quartiles = mock_quartiles

    mock_top_value = mock.Mock()
    mock_top_value.value = "Cash"
    mock_top_value.count = 150

    mock_string_profile = mock.Mock()
    mock_string_profile.unique_count = 4
    mock_string_profile.top_n_values = [mock_top_value]

    mock_field_profile = mock.Mock()
    mock_field_profile.null_ratio = 0.05
    mock_field_profile.distinct_ratio = 0.8
    mock_field_profile.double_profile = mock_double_profile
    mock_field_profile.string_profile = None

    mock_string_field_profile = mock.Mock()
    mock_string_field_profile.null_ratio = 0.02
    mock_string_field_profile.distinct_ratio = 0.1
    mock_string_field_profile.double_profile = None
    mock_string_field_profile.string_profile = mock_string_profile

    mock_numeric_field = mock.Mock()
    mock_numeric_field.name = "trip_total"
    mock_numeric_field.type_ = "FLOAT64"
    mock_numeric_field.mode = "NULLABLE"
    mock_numeric_field.profile = mock_field_profile

    mock_string_field = mock.Mock()
    mock_string_field.name = "payment_type"
    mock_string_field.type_ = "STRING"
    mock_string_field.mode = "NULLABLE"
    mock_string_field.profile = mock_string_field_profile

    mock_profile = mock.Mock()
    mock_profile.row_count = 1000
    mock_profile.fields = [mock_numeric_field, mock_string_field]

    mock_profile_result = mock.Mock()
    mock_profile_result.profile = mock_profile

    mock_job = mock.Mock()
    mock_job.data_profile_result = mock_profile_result
    mock_job.start_time = datetime.now(timezone.utc)
    mock_job.state.name = "SUCCEEDED"

    return mock_job


@pytest.fixture
def sample_profile_results():
    """Sample profile results structure for testing storage and comparison"""
    return {
        "scan_metadata": {
            "scan_id": "test-scan-123",
            "table_name": "project-id.preprocessing.test_table",
            "pipeline_stage": "post-ingestion",
            "pipeline_run_id": "test-pipeline-run-456",
            "scan_timestamp": "2024-01-15T10:30:00+00:00",
            "job_state": "SUCCEEDED",
        },
        "table_metrics": {"row_count": 1000, "column_count": 2},
        "column_metrics": {
            "trip_total": {
                "name": "trip_total",
                "type": "FLOAT64",
                "mode": "NULLABLE",
                "null_ratio": 0.05,
                "distinct_ratio": 0.8,
                "min_value": 0.0,
                "max_value": 100.0,
                "mean_value": 45.5,
                "stddev_value": 15.2,
                "percentiles": {
                    "p5": 10.0,
                    "p25": 25.0,
                    "p50": 50.0,
                    "p75": 75.0,
                    "p95": 95.0,
                },
            },
            "payment_type": {
                "name": "payment_type",
                "type": "STRING",
                "mode": "NULLABLE",
                "null_ratio": 0.02,
                "distinct_ratio": 0.1,
                "unique_count": 4,
                "top_values": [{"value": "Cash", "count": 150}],
            },
        },
    }
