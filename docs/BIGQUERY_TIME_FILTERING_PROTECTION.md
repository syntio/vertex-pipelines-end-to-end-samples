# BigQuery Time Filtering Protection

## Overview

Implementation of mandatory time filtering protection for BigQuery operations, preventing expensive full-table scans and achieving 99% cost reduction through table partitioning.

**Result**: Reduced profiling costs from €0.32 to €0.000001 per single-day scan.

## Components

### Protected Table Access
- `protected_table_access()` - Context manager enforcing time filtering
- Automatic temporary view creation with date filters
- Cost estimation and automatic cleanup

### Dataplex Profile Scans
- BigQuery export configuration for results storage
- Export table: `syntio-ai-ops.chicago_taxi_trips.profile_scan_results`
- Synchronous polling with 30s health checks, 1hr timeout
- Automatic result parsing from export table

### Profile Comparison System
- `compare_profiles()` - Compare current vs historical profiles
- `detect_significant_changes()` - Flag >10% deviations
- Automatic HALT/CONTINUE pipeline decisions
- Storage in `profile_comparisons` table

### Cost-Aware BigQuery Client
- Drop-in replacement for standard BigQuery client
- Interactive cost approval for expensive queries
- Configurable cost thresholds per environment

## Environment Setup

Required variables:
```bash
export PROJECT_ID=syntio-ai-ops
export TABLE_FILTER_START_DATE=2022-09-01
export TABLE_FILTER_END_DATE=2022-09-30
export TABLE_FILTER_COLUMN=trip_start_timestamp
export BIGQUERY_COST_WARNING_THRESHOLD=1.0
export BIGQUERY_REQUIRE_APPROVAL=true
```

Environment files:
- `env.dev.sh` - Development with user approval
- `env.prod.sh` - Production with logging only
- `env.test.sh` - Testing with low thresholds

## Usage

### Basic Usage
```python
from dataplex_components.protected_access import protected_table_access

with protected_table_access(
    bq_table="project.dataset.table",
    start_date="2022-09-01",
    end_date="2022-09-30"
) as filtered_view:
    # Operations on filtered_view cost €0.000001 instead of €0.32
    results = run_analysis(filtered_view)
```

### Pipeline Integration
```python
@dsl.pipeline(name="training-pipeline")
def training_pipeline(
    project_id: str,
    table_filter_start_date: str = "2022-09-01",
    table_filter_end_date: str = "2022-09-30"
):
    profile_task = run_profile_scan(
        project_id=project_id,
        bq_table=f"{project_id}.chicago_taxi_trips.taxi_trips",
        start_date=table_filter_start_date,
        end_date=table_filter_end_date
    )
```

## Table Partitioning

The `taxi_trips` table was replaced with a partitioned version:
- 4,000 daily partitions (2013-01-18 to 2023-12-31)
- **Data exclusion**: First 17 days of 2013 removed (794,506 rows, 0.375%) to stay under BigQuery's 4,000 partition limit
- Original data span: 4,017 days (exceeded limit by 17 days)
- Partition pruning reduces scan costs by 99%

### Partition Information
```sql
SELECT partition_id, total_rows
FROM `syntio-ai-ops.chicago_taxi_trips.INFORMATION_SCHEMA.PARTITIONS`
WHERE table_name = 'taxi_trips' AND partition_id IS NOT NULL
ORDER BY partition_id DESC LIMIT 5;
```

## Cost Optimization Results

| Query Type | Before | After | Savings |
|------------|--------|-------|---------|
| Single day | €0.32 (82GB) | €0.000001 (0.15MB) | 99.9% |
| Monthly | €0.32 (82GB) | €0.05 (~1GB) | 84% |
| Full table | €0.32 (82GB) | Blocked | 100% |

**Break-even**: 2 operations (investment: €0.38 partitioning cost)

## Testing

Run integration tests:
```bash
cd components/dataplex-components
source env.dev.sh
python -m pytest tests/test_bigquery_time_filtering.py::test_real_protected_table_access -v
```

Expected output:
```
💰 Cost estimate - Full scan: €0.32 → Filtered: €0.00 (saves €0.32)
📊 Row reduction: 100.0% (19,237 vs 210,860,953 rows)
✅ PASSED
```

## Common Issues

### Missing Parameters
```python
# Error: Time filtering required
# Solution: Add start_date/end_date parameters
```

### Environment Not Loaded
```bash
# Error: PROJECT_ID not set
# Solution: source env.dev.sh
```

### Cost Threshold Exceeded
```bash
# Error: Query cost exceeds threshold
# Solution: Reduce date range or increase BIGQUERY_COST_WARNING_THRESHOLD
```

### Import Issues
```bash
# Error: ModuleNotFoundError: dataplex_components
# Solution: PYTHONPATH=src python your_script.py
```

## Migration Notes

- Migration completed 2024-09-15
- Original table renamed to backup then deleted
- Partitioned table promoted to production name
- All existing code works without changes (with added time parameters)
- 7-day time travel available for emergency recovery

## Files Modified

Core components:
- `components/dataplex-components/src/dataplex_components/protected_access.py`
- `components/dataplex-components/src/dataplex_components/cost_aware_client.py`
- `components/dataplex-components/src/dataplex_components/profile_scan.py`
- `components/dataplex-components/src/dataplex_components/dq_scan.py`

Pipeline integration:
- `pipelines/src/pipelines/tensorflow/training/pipeline.py`
- `pipelines/src/pipelines/xgboost/training/pipeline.py`

Environment files:
- `env.dev.sh`, `env.prod.sh`, `env.test.sh`

Tests:
- `components/dataplex-components/tests/test_bigquery_time_filtering.py`
- `components/dataplex-components/tests/test_protected_access.py`