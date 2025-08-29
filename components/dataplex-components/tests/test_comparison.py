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
import pandas as pd
from unittest import mock
from dataplex_components.comparison import compare_profiles, detect_significant_changes


def test_compare_profiles_with_baseline(sample_profile_results):
    """Test profile comparison when historical baseline exists"""
    
    # Mock baseline data from BigQuery
    baseline_data = {
        'column_name': ['trip_total', 'payment_type'],
        'baseline_mean': [40.0, None],  # Current: 45.5, Baseline: 40.0 = 13.75% increase
        'baseline_stddev': [12.0, None],  # Current: 15.2, Baseline: 12.0 = 26.67% increase  
        'baseline_null_pct': [3.0, 1.5],  # Current: 5.0, 2.0 vs Baseline: 3.0, 1.5
        'baseline_cardinality': [None, 3],  # Current: None, 4 vs Baseline: None, 3
        'baseline_sample_count': [5, 5]
    }
    baseline_df = pd.DataFrame(baseline_data)
    
    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.query.return_value.to_dataframe.return_value = baseline_df
        
        comparison_results, significant_changes, comparison_summary = compare_profiles.python_func(
            current_profile=sample_profile_results,
            project_id="test-project",
            deviation_threshold=0.1  # 10%
        )
        
        # Verify comparison results structure
        assert len(comparison_results) == 2
        assert "trip_total" in comparison_results
        assert "payment_type" in comparison_results
        
        # Verify trip_total comparison (numeric metrics)
        trip_total_comparisons = comparison_results["trip_total"]["comparisons"]
        
        # Mean comparison: 45.5 vs 40.0 = 13.75% increase (significant)
        mean_comparison = trip_total_comparisons["mean_value"]
        assert mean_comparison["current_value"] == 45.5
        assert mean_comparison["baseline_value"] == 40.0
        assert abs(mean_comparison["percent_change"] - 0.1375) < 0.001
        assert mean_comparison["is_significant"] == True
        
        # Stddev comparison: 15.2 vs 12.0 = 26.67% increase (significant)
        stddev_comparison = trip_total_comparisons["stddev_value"]
        assert stddev_comparison["current_value"] == 15.2
        assert stddev_comparison["baseline_value"] == 12.0
        assert stddev_comparison["is_significant"] == True
        
        # Verify significant changes detected
        assert len(significant_changes) > 0
        
        trip_total_changes = [c for c in significant_changes if c["column_name"] == "trip_total"]
        assert len(trip_total_changes) >= 2  # mean and stddev both significant
        
        # Verify summary
        assert comparison_summary["total_columns_compared"] == 2
        assert comparison_summary["significant_changes_count"] > 0
        assert comparison_summary["status"] == "completed"


def test_compare_profiles_no_baseline(sample_profile_results):
    """Test profile comparison when no historical baseline exists"""
    
    # Empty baseline (first run)
    empty_baseline_df = pd.DataFrame()
    
    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.query.return_value.to_dataframe.return_value = empty_baseline_df
        
        comparison_results, significant_changes, comparison_summary = compare_profiles.python_func(
            current_profile=sample_profile_results,
            project_id="test-project"
        )
        
        # Should return empty results for first scan
        assert comparison_results == {}
        assert significant_changes == []
        assert comparison_summary["status"] == "no_baseline"
        assert comparison_summary["first_scan"] == True


def test_compare_profiles_deviation_thresholds(sample_profile_results):
    """Test different deviation thresholds for significance detection"""
    
    baseline_data = {
        'column_name': ['trip_total'],
        'baseline_mean': [40.0],  # 13.75% change vs current 45.5
        'baseline_stddev': [14.0],  # 8.57% change vs current 15.2  
        'baseline_null_pct': [4.8],  # 4.17% change vs current 5.0
        'baseline_cardinality': [None],
        'baseline_sample_count': [5]
    }
    baseline_df = pd.DataFrame(baseline_data)
    
    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.query.return_value.to_dataframe.return_value = baseline_df
        
        # Test with 10% threshold - mean should be significant (13.75% > 10%)
        comparison_results, significant_changes, _ = compare_profiles.python_func(
            current_profile=sample_profile_results,
            project_id="test-project",
            deviation_threshold=0.1
        )
        
        mean_significant_changes = [c for c in significant_changes if c["metric"] == "mean_value"]
        assert len(mean_significant_changes) == 1
        assert mean_significant_changes[0]["significance_level"] == "WARNING"  # 13.75% < 20%
        
        # Test with 15% threshold - mean should NOT be significant (13.75% < 15%)
        comparison_results, significant_changes, _ = compare_profiles.python_func(
            current_profile=sample_profile_results,
            project_id="test-project", 
            deviation_threshold=0.15
        )
        
        mean_significant_changes = [c for c in significant_changes if c["metric"] == "mean_value"]
        assert len(mean_significant_changes) == 0


def test_detect_significant_changes_continue():
    """Test significant changes detection - should continue pipeline"""
    
    significant_changes = [
        {
            "column_name": "trip_total",
            "metric": "mean_value",
            "current_value": 45.5,
            "baseline_value": 40.0,
            "percent_change": 13.75,
            "significance_level": "WARNING",  # No CRITICAL changes
            "deviation_threshold": 10.0,
            "table_name": "test-table",
            "pipeline_stage": "post-ingestion"
        }
    ]
    
    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []  # No errors
        mock_client.query.return_value.to_dataframe.return_value = pd.DataFrame({"current_timestamp": ["2024-01-15T10:30:00"]})
        
        action = detect_significant_changes.python_func(
            significant_changes=significant_changes,
            project_id="test-project",
            pipeline_run_id="test-pipeline"
        )
        
        assert action == "CONTINUE"


def test_detect_significant_changes_halt():
    """Test significant changes detection - should halt pipeline"""
    
    significant_changes = [
        {
            "column_name": "trip_total",
            "metric": "mean_value", 
            "current_value": 100.0,
            "baseline_value": 40.0,
            "percent_change": 150.0,
            "significance_level": "CRITICAL",  # CRITICAL change detected
            "deviation_threshold": 10.0,
            "table_name": "test-table",
            "pipeline_stage": "post-ingestion"
        }
    ]
    
    with mock.patch("google.cloud.bigquery.Client") as mock_bq_client:
        mock_client = mock_bq_client.return_value
        mock_client.insert_rows_json.return_value = []
        mock_client.query.return_value.to_dataframe.return_value = pd.DataFrame({"current_timestamp": ["2024-01-15T10:30:00"]})
        
        action = detect_significant_changes.python_func(
            significant_changes=significant_changes,
            project_id="test-project",
            pipeline_run_id="test-pipeline"
        )
        
        assert action == "HALT"


def test_detect_significant_changes_no_changes():
    """Test significant changes detection with no changes"""
    
    with mock.patch("google.cloud.bigquery.Client"):
        action = detect_significant_changes.python_func(
            significant_changes=[],
            project_id="test-project", 
            pipeline_run_id="test-pipeline"
        )
        
        assert action == "CONTINUE"