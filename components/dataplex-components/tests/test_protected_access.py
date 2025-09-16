import pytest
from unittest import mock
from datetime import datetime
from dataplex_components.protected_access import protected_table_access


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
    
    with pytest.raises(ValueError, match="start_date must be before or equal to end_date"):
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


