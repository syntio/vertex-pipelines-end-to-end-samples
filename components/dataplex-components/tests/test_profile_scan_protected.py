import pytest
from unittest import mock
from dataplex_components.profile_scan import run_profile_scan


def test_run_profile_scan_with_time_filtering(mock_dataplex_profile_result):
    """Test profile scan with mandatory time filtering"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("dataplex_components.profile_scan.protected_table_access") as mock_protected_access, \
         mock.patch("time.sleep"):
        
        # Setup mocks
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.side_effect = Exception("Not found")
        mock_client.create_data_scan.return_value.result.return_value = None
        mock_client.list_data_scan_jobs.return_value = [mock_dataplex_profile_result]
        
        # Mock the protected access context manager
        mock_protected_access.return_value.__enter__.return_value = "test-project.dataset.taxi_trips_filtered_20220901_abc123"
        
        # Execute with time filtering
        profile_results, scan_id, metrics_summary = run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.taxi_trips",
            profile_scan_id="test-scan-filtered",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline-123",
            start_date="2022-09-01",
            end_date="2022-09-30",
            date_column="trip_start_timestamp"
        )
        
        # Verify protected access was called with correct parameters
        mock_protected_access.assert_called_once_with(
            bq_table="test-project.dataset.taxi_trips",
            start_date="2022-09-01",
            end_date="2022-09-30", 
            date_column="trip_start_timestamp",
            project_id="test-project"
        )
        
        # Verify results include time filtering metadata
        assert metrics_summary["time_filtered"] is True
        assert metrics_summary["filter_start_date"] == "2022-09-01"
        assert metrics_summary["filter_end_date"] == "2022-09-30"
        assert metrics_summary["filter_column"] == "trip_start_timestamp"
        
        # Verify scan was created on filtered view
        create_calls = mock_client.create_data_scan.call_args_list
        assert len(create_calls) == 1


def test_run_profile_scan_missing_start_date():
    """Test that missing start_date raises ValueError"""
    
    with pytest.raises(ValueError, match="Time filtering required - provide start_date and end_date"):
        run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.taxi_trips",
            profile_scan_id="test-scan",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline",
            start_date="",  # Missing
            end_date="2022-09-30"
        )


def test_run_profile_scan_missing_end_date():
    """Test that missing end_date raises ValueError"""
    
    with pytest.raises(ValueError, match="Time filtering required - provide start_date and end_date"):
        run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2", 
            bq_table="test-project.dataset.taxi_trips",
            profile_scan_id="test-scan",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline",
            start_date="2022-09-01",
            end_date=""  # Missing
        )


def test_run_profile_scan_both_dates_missing():
    """Test that missing both dates raises ValueError"""
    
    with pytest.raises(ValueError, match="Time filtering required - provide start_date and end_date"):
        run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.taxi_trips", 
            profile_scan_id="test-scan",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline",
            start_date="",  # Missing
            end_date=""     # Missing
        )


def test_run_profile_scan_custom_date_column(mock_dataplex_profile_result):
    """Test profile scan with custom date column"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("dataplex_components.profile_scan.protected_table_access") as mock_protected_access, \
         mock.patch("time.sleep"):
        
        # Setup mocks
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.side_effect = Exception("Not found")
        mock_client.create_data_scan.return_value.result.return_value = None
        mock_client.list_data_scan_jobs.return_value = [mock_dataplex_profile_result]
        
        mock_protected_access.return_value.__enter__.return_value = "test-project.dataset.table_filtered_20220901_abc123"
        
        # Execute with custom date column
        profile_results, scan_id, metrics_summary = run_profile_scan.python_func(
            project_id="test-project",
            location="europe-west2",
            bq_table="test-project.dataset.events_table",
            profile_scan_id="test-scan-events",
            pipeline_stage="post-ingestion", 
            pipeline_run_id="test-pipeline-123",
            start_date="2022-09-01",
            end_date="2022-09-30",
            date_column="event_timestamp"  # Custom column
        )
        
        # Verify custom date column was used
        mock_protected_access.assert_called_once_with(
            bq_table="test-project.dataset.events_table",
            start_date="2022-09-01",
            end_date="2022-09-30",
            date_column="event_timestamp",  # Custom column
            project_id="test-project"
        )
        
        assert metrics_summary["filter_column"] == "event_timestamp"


def test_run_profile_scan_view_cleanup_on_failure():
    """Test that view cleanup happens even if scan fails"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("dataplex_components.profile_scan.protected_table_access") as mock_protected_access, \
         mock.patch("time.sleep"):
        
        # Setup mocks - scan will fail
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.side_effect = Exception("Not found")
        mock_client.create_data_scan.side_effect = Exception("Dataplex error")  # Scan creation fails
        
        mock_context = mock.MagicMock()
        mock_protected_access.return_value = mock_context
        mock_context.__enter__.return_value = "test-project.dataset.table_filtered_20220901_abc123"
        
        # Should raise exception but still cleanup
        with pytest.raises(Exception):
            run_profile_scan.python_func(
                project_id="test-project",
                location="europe-west2",
                bq_table="test-project.dataset.table",
                profile_scan_id="test-scan",
                pipeline_stage="post-ingestion",
                pipeline_run_id="test-pipeline",
                start_date="2022-09-01",
                end_date="2022-09-30"
            )
        
        # Verify context manager was entered and exited (cleanup)
        assert mock_context.__enter__.called
        assert mock_context.__exit__.called


def test_run_profile_scan_monthly_period_example():
    """Test monthly profiling use case from ticket example"""
    
    with mock.patch("google.cloud.dataplex_v1.DataScanServiceClient") as mock_client_class, \
         mock.patch("google.cloud.bigquery.Client") as mock_bq_client, \
         mock.patch("dataplex_components.profile_scan.protected_table_access") as mock_protected_access, \
         mock.patch("time.sleep"):
        
        mock_client = mock_client_class.return_value
        mock_client.get_data_scan.side_effect = Exception("Not found")
        mock_client.create_data_scan.return_value.result.return_value = None
        mock_client.list_data_scan_jobs.return_value = [mock.Mock(
            start_time=mock.Mock(isoformat=lambda: "2022-09-15T10:00:00Z"),
            state=mock.Mock(name="SUCCEEDED"),
            data_profile_result=mock.Mock(
                profile=mock.Mock(
                    row_count=50000,  # Much smaller than 211M
                    fields=[]
                )
            )
        )]
        
        mock_protected_access.return_value.__enter__.return_value = "syntio-ai-ops.chicago_taxi_trips.taxi_trips_filtered_20220901_abc123"
        
        # Execute September 2022 profiling (example from ticket)
        profile_results, scan_id, metrics_summary = run_profile_scan.python_func(
            project_id="syntio-ai-ops",
            location="europe-west2",
            bq_table="syntio-ai-ops.chicago_taxi_trips.taxi_trips",
            profile_scan_id="profile-sep-2022",
            pipeline_stage="post-ingestion",
            pipeline_run_id="test-pipeline",
            start_date="2022-09-01",
            end_date="2022-09-30"
        )
        
        # Verify significant cost savings (50K vs 211M rows)
        assert metrics_summary["table_row_count"] == 50000
        assert scan_id == "profile-sep-2022"
        assert metrics_summary["time_filtered"] is True