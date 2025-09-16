# Dataplex Profiling Implementation

## Overview

Complete implementation of Dataplex profiling scans with profile comparison and deviation detection for pipeline quality monitoring.

**Features:**
- Profile scans at two pipeline stages (post-ingestion, post-preprocessing)
- Column statistics capture and BigQuery export
- Historical profile comparison with deviation flagging
- Automated pipeline halt/continue decisions

## Components

### Profile Scans
- `run_profile_scan()` - Execute Dataplex profile scan with time filtering
- Mandatory time filtering for cost protection (99.99% cost reduction)
- Export results to BigQuery table for analysis
- Synchronous polling with health checks

### Profile Comparison
- `compare_profiles()` - Compare current vs historical profiles
- `detect_significant_changes()` - Flag deviations >10% threshold
- Automated HALT/CONTINUE pipeline decisions
- Storage in profile_comparisons table

### Data Quality Integration
- `run_dq_scan()` - Data quality scans with smart rule generation
- Time filtering protection for cost optimization
- Integration with profile results for comprehensive monitoring

## Usage

### Basic Profile Scan
```python
from dataplex_components.profile_scan import run_profile_scan

profile_results, scan_id, summary = run_profile_scan(
    project_id="syntio-ai-ops",
    bq_table="syntio-ai-ops.chicago_taxi_trips.taxi_trips",
    profile_scan_id="taxi-profile-001",
    pipeline_stage="post-ingestion",
    start_date="2022-09-01",
    end_date="2022-09-01",
    date_column="trip_start_timestamp"
)
```

### Profile Comparison
```python
from dataplex_components.comparison import compare_profiles, detect_significant_changes

# Compare with historical baseline
comparison_results, significant_changes, summary = compare_profiles(
    current_profile=profile_results,
    project_id="syntio-ai-ops",
    deviation_threshold=0.1  # 10%
)

# Determine pipeline action
action = detect_significant_changes(
    significant_changes=significant_changes,
    project_id="syntio-ai-ops",
    pipeline_run_id="run-123"
)
# Returns: "CONTINUE" or "HALT"
```

### Pipeline Integration
```python
@dsl.pipeline(name="taxi-training-pipeline")
def training_pipeline(
    project_id: str,
    table_filter_start_date: str,
    table_filter_end_date: str
):
    # Profile scan after ingestion
    profile_task = run_profile_scan(
        project_id=project_id,
        bq_table=f"{project_id}.chicago_taxi_trips.taxi_trips",
        pipeline_stage="post-ingestion",
        start_date=table_filter_start_date,
        end_date=table_filter_end_date
    )

    # Compare with baseline
    comparison_task = compare_profiles(
        current_profile=profile_task.outputs["profile_results"],
        project_id=project_id
    )

    # Check if pipeline should continue
    decision_task = detect_significant_changes(
        significant_changes=comparison_task.outputs["significant_changes"],
        project_id=project_id
    )
```

## Profile Metrics Captured

### Table-Level Metrics
- Total row count (time-filtered)
- Column count
- Scan metadata (timestamp, pipeline stage, run ID)

### Column-Level Metrics
- **Numeric columns**: min, max, mean, stddev, percentiles
- **Categorical columns**: cardinality, top values, unique count
- **Data quality**: null ratio, distinct ratio
- **Geographic data**: coordinate bounds for lat/lon columns

## Export Schema

### Profile Results Table
```sql
-- syntio-ai-ops.chicago_taxi_trips.profile_scan_results
CREATE TABLE profile_scan_results (
  data_profile_scan STRUCT<data_scan_id STRING>,
  job_start_time TIMESTAMP,
  job_rows_scanned INT64,
  column_name STRING,
  column_data_type STRING,
  null_count INT64,
  non_null_count INT64,
  distinct_count INT64,
  min_value FLOAT64,
  max_value FLOAT64,
  avg_value FLOAT64,
  std_dev_value FLOAT64
);
```

### Profile Comparisons Table
```sql
-- syntio-ai-ops.data_profiles.profile_comparisons
CREATE TABLE profile_comparisons (
  comparison_timestamp TIMESTAMP,
  pipeline_run_id STRING,
  table_name STRING,
  column_name STRING,
  metric_name STRING,
  current_value FLOAT64,
  baseline_value FLOAT64,
  percent_change FLOAT64,
  is_significant BOOLEAN,
  significance_level STRING  -- "WARNING" | "CRITICAL"
);
```

## Deviation Detection

### Thresholds
- **WARNING**: 10-20% deviation from baseline
- **CRITICAL**: >20% deviation from baseline

### Pipeline Actions
- **No changes**: CONTINUE
- **WARNING changes**: CONTINUE (with monitoring)
- **CRITICAL changes**: HALT (manual review required)

### Baseline Calculation
- Uses last 30 days of historical profiles
- Requires minimum 3 historical samples
- Calculates average baseline values per column

## Testing

### Integration Tests
```bash
# Profile scan with time filtering
python -m pytest tests/test_bigquery_time_filtering.py::test_real_profile_scan_cost_protection -v -s

# Profile comparison logic
python -m pytest tests/test_comparison.py -v

# All profiling tests
python -m pytest tests/test_profile_scan.py -v
```

### Test Coverage
- ✅ Profile scan execution (4 tests)
- ✅ Time filtering protection (4 tests)
- ✅ Profile comparison logic (6 tests)
- ✅ Deviation detection (3 tests)
- ✅ Cost protection (2 tests)

## Cost Optimization

### Time Filtering Benefits
- **Full table scan**: €0.32 (211M rows)
- **Filtered scan**: €0.0001 (19K rows)
- **Cost reduction**: 99.99%
- **Time reduction**: 30+ minutes → 2-3 minutes

### Partition Pruning
- Table partitioned by trip_start_timestamp
- 4,000 daily partitions (2013-2023)
- Automatic partition pruning for date-filtered queries

## Environment Setup

```bash
export PROJECT_ID=syntio-ai-ops
export TABLE_FILTER_START_DATE=2022-09-01
export TABLE_FILTER_END_DATE=2022-09-01
export TABLE_FILTER_COLUMN=trip_start_timestamp
export VERTEX_LOCATION=europe-west1
```

## Production Deployment

### Prerequisites
- Dataplex API enabled
- BigQuery export tables created
- Time-partitioned source tables
- Service account permissions

### Pipeline Parameters
```yaml
parameters:
  - name: table_filter_start_date
    type: STRING
    default: "2022-09-01"
  - name: table_filter_end_date
    type: STRING
    default: "2022-09-01"
  - name: profile_scan_id
    type: STRING
    default: "pipeline-profile-{timestamp}"
```

## Monitoring

### Health Checks
- Profile scan status: 30s intervals, 1hr timeout
- Export table population verification
- Cost threshold monitoring

### Alerts
- CRITICAL profile deviations detected
- Profile scan failures
- Export table population issues
- Cost threshold exceeded

## Files

### Core Components
- `src/dataplex_components/profile_scan.py` - Profile scan execution
- `src/dataplex_components/comparison.py` - Profile comparison logic
- `src/dataplex_components/protected_access.py` - Time filtering protection
- `src/dataplex_components/dq_scan.py` - Data quality integration

### Tests
- `tests/test_profile_scan.py` - Profile scan tests
- `tests/test_comparison.py` - Comparison logic tests
- `tests/test_bigquery_time_filtering.py` - Integration tests

### Documentation
- `docs/DATAPLEX_PROFILING.md` - This document
- `docs/BIGQUERY_TIME_FILTERING_PROTECTION.md` - Cost optimization
- `README.md` - Component overview