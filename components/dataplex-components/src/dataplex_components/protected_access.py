from contextlib import contextmanager
from datetime import datetime
import uuid
from typing import Optional


@contextmanager
def protected_table_access(
    bq_table: str,
    start_date: str,
    end_date: str,
    date_column: str = "trip_start_timestamp",
    project_id: Optional[str] = None
):
    """
    Context manager for protected table access with mandatory time filtering.
    
    Creates temporary filtered BigQuery view, yields view name, ensures cleanup.
    
    Args:
        bq_table: Full table name (project.dataset.table)
        start_date: Start date filter (YYYY-MM-DD format)
        end_date: End date filter (YYYY-MM-DD format)  
        date_column: Column to filter on (default: trip_start_timestamp)
        project_id: Optional project ID for view creation
        
    Yields:
        str: Temporary view name to use instead of original table
        
    Raises:
        ValueError: If start_date or end_date not provided
        Exception: If view creation/cleanup fails
        
    Example:
        with protected_table_access(
            "project.dataset.taxi_trips", 
            "2022-09-01", 
            "2022-09-30"
        ) as view_name:
            # Use view_name instead of original table
            dataplex_scan(view_name)
    """
    from .cost_aware_client import Client as bigquery_Client
    
    # Validate required parameters
    if not start_date or not end_date:
        raise ValueError("Time filtering required - provide start_date and end_date")
    
    # Validate date format (basic check)
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Dates must be in YYYY-MM-DD format")
    
    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")
    
    # Parse table components
    parts = bq_table.split(".")
    if len(parts) != 3:
        raise ValueError("bq_table must be in format: project.dataset.table")
    
    table_project, dataset, table = parts
    
    # Use provided project_id or extract from table
    target_project = project_id or table_project
    
    # Generate unique view name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = str(uuid.uuid4())[:8]
    view_name = f"{table}_filtered_{timestamp}_{random_suffix}"
    full_view_name = f"{target_project}.{dataset}.{view_name}"
    
    # Initialize cost-aware BigQuery client
    client = bigquery_Client(project=target_project)
    
    print(f"🔒 Creating protected view: {view_name}")
    print(f"📅 Date range: {start_date} to {end_date}")
    print(f"🗓️ Filter column: {date_column}")
    
    # Estimate cost savings
    try:
        # Get original table row count for cost estimation
        count_query = f"SELECT COUNT(*) as total_rows FROM `{bq_table}`"
        total_rows = client.query(count_query).to_dataframe().iloc[0]['total_rows']
        
        # Estimate filtered row count (rough approximation)
        filtered_query = f"""
        SELECT COUNT(*) as filtered_rows 
        FROM `{bq_table}` 
        WHERE DATE({date_column}) BETWEEN '{start_date}' AND '{end_date}'
        """
        filtered_rows = client.query(filtered_query).to_dataframe().iloc[0]['filtered_rows']
        
        cost_reduction = ((total_rows - filtered_rows) / total_rows * 100) if total_rows > 0 else 0
        print(f"💰 Estimated cost reduction: {cost_reduction:.1f}% ({filtered_rows:,} vs {total_rows:,} rows)")
        
    except Exception as e:
        print(f"⚠️ Could not estimate cost savings: {e}")
    
    # Create temporary filtered view
    create_view_sql = f"""
    CREATE OR REPLACE VIEW `{full_view_name}` AS
    SELECT * 
    FROM `{bq_table}`
    WHERE DATE({date_column}) BETWEEN '{start_date}' AND '{end_date}'
    """
    
    try:
        client.query(create_view_sql).result()
        print(f"✅ Created temporary view: {view_name}")
        
        # Yield the view name for use
        yield full_view_name
        
    except Exception as e:
        print(f"❌ Failed to create view: {e}")
        raise Exception(f"View creation failed: {e}")
    
    finally:
        # Always cleanup the view
        try:
            cleanup_sql = f"DROP VIEW IF EXISTS `{full_view_name}`"
            client.query(cleanup_sql).result()
            print(f"🧹 Cleaned up view: {view_name}")
        except Exception as e:
            print(f"⚠️ Failed to cleanup view {view_name}: {e}")
            # Don't raise here - we don't want cleanup failures to break the main flow