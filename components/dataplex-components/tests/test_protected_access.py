import pytest
from unittest import mock
from datetime import datetime
from dataplex_components.protected_access import protected_table_access


def test_protected_access_success():
    """Test successful protected table access with time filtering"""
    
    with mock.patch("google.cloud.bigquery.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.query.return_value.result.return_value = None
        mock_client.query.return_value.to_dataframe.return_value.iloc = [
            type('obj', (object,), {'total_rows': 1000000, 'filtered_rows': 50000})
        ]
        
        with protected_table_access(
            bq_table="test-project.dataset.taxi_trips",
            start_date="2022-09-01", 
            end_date="2022-09-30",
            date_column="trip_start_timestamp"
        ) as view_name:
            # Verify view name format
            assert "taxi_trips_filtered_" in view_name
            assert "test-project.dataset." in view_name
            
        # Verify cleanup was called
        assert mock_client.query.call_count >= 2  # Create + cleanup calls


def test_protected_access_missing_dates():
    """Test that missing dates raises ValueError"""
    
    with pytest.raises(ValueError, match="Time filtering required"):
        with protected_table_access(
            bq_table="test-project.dataset.table",
            start_date="",
            end_date="2022-09-30"
        ) as view_name:
            pass


def test_protected_access_invalid_date_format():
    """Test that invalid date format raises ValueError"""
    
    with pytest.raises(ValueError, match="Dates must be in YYYY-MM-DD format"):
        with protected_table_access(
            bq_table="test-project.dataset.table",
            start_date="2022/09/01",  # Wrong format
            end_date="2022-09-30"
        ) as view_name:
            pass


def test_protected_access_invalid_date_range():
    """Test that start_date >= end_date raises ValueError"""
    
    with pytest.raises(ValueError, match="start_date must be before end_date"):
        with protected_table_access(
            bq_table="test-project.dataset.table",
            start_date="2022-09-30",
            end_date="2022-09-01"  # After start date
        ) as view_name:
            pass


def test_protected_access_invalid_table_format():
    """Test that invalid table format raises ValueError"""
    
    with pytest.raises(ValueError, match="bq_table must be in format"):
        with protected_table_access(
            bq_table="invalid_table_name",  # Missing project.dataset
            start_date="2022-09-01",
            end_date="2022-09-30"
        ) as view_name:
            pass


def test_protected_access_view_creation_failure():
    """Test handling of view creation failure"""
    
    with mock.patch("google.cloud.bigquery.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.query.side_effect = Exception("BigQuery error")
        
        with pytest.raises(Exception, match="View creation failed"):
            with protected_table_access(
                bq_table="test-project.dataset.table",
                start_date="2022-09-01",
                end_date="2022-09-30"
            ) as view_name:
                pass


def test_protected_access_cost_estimation():
    """Test cost estimation logging"""
    
    with mock.patch("google.cloud.bigquery.Client") as mock_client_class, \
         mock.patch("builtins.print") as mock_print:
        
        mock_client = mock_client_class.return_value
        
        # Mock responses for cost estimation queries
        mock_total_result = mock.Mock()
        mock_total_result.to_dataframe.return_value.iloc = [
            type('obj', (object,), {'total_rows': 1000000})()
        ]
        
        mock_filtered_result = mock.Mock()
        mock_filtered_result.to_dataframe.return_value.iloc = [
            type('obj', (object,), {'filtered_rows': 50000})()
        ]
        
        # First call for total count, second for filtered count, third for view creation
        mock_client.query.side_effect = [
            mock_total_result,
            mock_filtered_result, 
            mock.Mock()  # View creation
        ]
        mock_client.query.return_value.result.return_value = None
        
        with protected_table_access(
            bq_table="test-project.dataset.table",
            start_date="2022-09-01",
            end_date="2022-09-30"
        ) as view_name:
            pass
            
        # Verify cost estimation was logged
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        cost_logs = [msg for msg in print_calls if "cost reduction" in msg.lower()]
        assert len(cost_logs) > 0


def test_protected_access_cleanup_always_runs():
    """Test that cleanup runs even if main code fails"""
    
    with mock.patch("google.cloud.bigquery.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.query.return_value.result.return_value = None
        
        try:
            with protected_table_access(
                bq_table="test-project.dataset.table",
                start_date="2022-09-01",
                end_date="2022-09-30"
            ) as view_name:
                raise Exception("Simulated failure")
        except Exception:
            pass  # Expected
            
        # Verify cleanup was still called despite the exception
        cleanup_calls = [call for call in mock_client.query.call_args_list 
                        if "DROP VIEW" in str(call)]
        assert len(cleanup_calls) > 0


def test_protected_access_unique_view_names():
    """Test that concurrent access creates unique view names"""
    
    with mock.patch("google.cloud.bigquery.Client") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.query.return_value.result.return_value = None
        
        view_names = []
        
        # Create multiple views "concurrently"
        for i in range(3):
            with protected_table_access(
                bq_table="test-project.dataset.table",
                start_date="2022-09-01",
                end_date="2022-09-30"
            ) as view_name:
                view_names.append(view_name)
                
        # Verify all view names are unique
        assert len(view_names) == len(set(view_names))