# Dataplex Components

Advanced data profiling and quality monitoring components for Vertex AI Pipelines using Google Cloud Dataplex.

## Overview

This component library provides **dual data governance capabilities**:

1. **📊 Statistical Data Profiling** - Comprehensive statistical analysis and historical trend monitoring
2. **🛡️ Data Quality (DQ) Scanning** - Rule-based validation with domain-specific checks for Chicago taxi data

Both capabilities work together to provide complete data governance throughout your ML pipeline lifecycle.

## Architecture Integration

```
📈 Chicago Taxi Data Pipeline Flow
         ↓
   DATA INGESTION
         ↓
   🛡️ DQ SCAN ────────────→ Rule validation & quality checks
         ↓
   📊 PROFILE SCAN #1 ─────→ Statistical profiling (post-ingestion)
         ↓
   DATA PREPROCESSING  
         ↓
   📊 PROFILE SCAN #2 ─────→ Statistical profiling (post-preprocessing)
         ↓
   💾 STORE PROFILES ─────→ BigQuery storage with timestamps
         ↓
   🔍 COMPARE PROFILES ───→ Against 30-day historical baseline
         ↓
   ⚠️ DETECT CHANGES ─────→ Flag >10% deviations (WARNING/CRITICAL)
         ↓
   ✅ CONTINUE PIPELINE (if no critical changes)
```

## Components

### 1. Data Quality Scanning (`run_dq_scan`)

**Purpose**: Rule-based validation with smart Chicago taxi domain knowledge

**Features**:
- **Auto-Generated Rules**: Based on INFORMATION_SCHEMA analysis
- **8+ Rule Types**: Null checks, range validation, geographic bounds, payment types
- **Chicago-Specific**: Lat/lon bounds (41.644-42.023, -87.940--87.524)
- **Smart Profiling**: Dynamic percentile-based range rules
- **Job Polling**: Monitors scan completion automatically

**Example Rules Generated**:
```sql
-- Geographic bounds for Chicago area
pickup_latitude BETWEEN 41.644 AND 42.023
pickup_longitude BETWEEN -87.940 AND -87.524

-- Business logic validation  
fare + IFNULL(tips,0) + IFNULL(tolls,0) >= 0
trip_start_timestamp <= CURRENT_TIMESTAMP()

-- Payment type validation
payment_type IN ('Cash', 'Credit Card', 'Mobile', 'Pcard', 'Prepaid', 'Way2ride')
```

### 2. Profile Scanning (`run_profile_scan`)

**Purpose**: Comprehensive statistical profiling of BigQuery tables

**Extracted Metrics**:
- **Table-Level**: Row count, column count
- **Numeric Columns**: min, max, mean, stddev, percentiles (p5, p25, p50, p75, p95)
- **Categorical Columns**: cardinality, unique count, top values with frequencies  
- **Quality Metrics**: null ratios, distinct ratios
- **Geographic Data**: Special handling for lat/lon Chicago taxi coordinates

**Output Structure**:
```python
{
  "scan_metadata": {
    "scan_id": "xgb-training-post-ingestion",
    "table_name": "project.dataset.table", 
    "pipeline_stage": "post-ingestion|post-preprocessing",
    "pipeline_run_id": "pipeline-execution-123",
    "scan_timestamp": "2024-01-15T10:30:00+00:00"
  },
  "table_metrics": {
    "row_count": 1000000,
    "column_count": 15
  },
  "column_metrics": {
    "trip_total": {
      "min_value": 0.0, "max_value": 150.75,
      "mean_value": 45.5, "stddev_value": 15.2,
      "percentiles": {"p5": 10.0, "p25": 25.0, "p95": 95.0}
    },
    "payment_type": {
      "unique_count": 4, "cardinality": 4,
      "top_values": [{"value": "Cash", "count": 150}]
    }
  }
}
```

### 3. Profile Storage (`store_profile_results`)

**Purpose**: Store profile results in BigQuery for historical analysis

**Storage Features**:
- **Time-Partitioned**: Partitioned by scan_timestamp for efficient querying
- **Clustered**: By pipeline_stage, table_name, column_name for fast access
- **Normalized Schema**: Each column's metrics stored as separate rows
- **Geographic Handling**: Special bounds handling for Chicago taxi coordinates

**BigQuery Schema**: See `bigquery_schema.sql` for complete table definitions

### 4. Profile Comparison (`compare_profiles`) 

**Purpose**: Compare current profiles against 30-day historical baselines

**Comparison Logic**:
- **30-Day Baseline**: Uses AVG() of last 30 days as baseline (minimum 3 samples)
- **Deviation Detection**: Flags changes exceeding threshold (default 10%)
- **Significance Levels**: 
  - **WARNING**: 10-20% deviation
  - **CRITICAL**: >20% deviation
- **Metrics Compared**: mean, stddev, null_percentage, cardinality

**Output**:
```python
{
  "trip_total": {
    "comparisons": {
      "mean_value": {
        "current_value": 45.5, "baseline_value": 40.0,
        "percent_change": 0.1375,  # 13.75% increase
        "is_significant": True
      }
    }
  }
}
```

### 5. Change Detection (`detect_significant_changes`)

**Purpose**: Determine pipeline continuation based on significance levels

**Decision Logic**:
- **CONTINUE**: No changes OR only WARNING-level changes
- **HALT**: Any CRITICAL-level changes detected (>20% deviation)

**Storage**: All significant changes stored in `profile_comparisons` table for audit trail

## Usage in Pipelines

### XGBoost Training Pipeline Integration

```python
from dataplex_components import (
    run_dq_scan,
    run_profile_scan, 
    store_profile_results,
    compare_profiles,
    detect_significant_changes
)

# After data ingestion
dq_scan = run_dq_scan(
    project_id=project_id,
    location=project_location,
    bq_table=f"{project_id}.{dataset_id}.{ingested_table}",
    dq_scan_id=f"taxi-trips-scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
).after(ingest).set_display_name("Run DQ scan")

# Profile post-ingestion data
profile_post_ingestion = run_profile_scan(
    project_id=project_id,
    location=project_location,
    bq_table=f"{project_id}.{dataset_id}.{ingested_table}",
    profile_scan_id="xgb-training-post-ingestion",
    pipeline_stage="post-ingestion",
    pipeline_run_id="{{$.pipeline_job_name}}"
).after(ingest).set_display_name("Profile scan: Post-ingestion")

# Store and compare profiles
store_profiles = store_profile_results(
    profile_results=profile_post_ingestion.outputs["profile_results"],
    project_id=project_id
).after(profile_post_ingestion)

compare_profiles_task = compare_profiles(
    current_profile=profile_post_ingestion.outputs["profile_results"],
    project_id=project_id
).after(store_profiles)

validate_changes = detect_significant_changes(
    significant_changes=compare_profiles_task.outputs["significant_changes"],
    project_id=project_id,
    pipeline_run_id="{{$.pipeline_job_name}}"
).after(compare_profiles_task)

# Continue pipeline only after validation
train_model = custom_train_job(...).after(validate_changes)
```

## BigQuery Setup

### 1. Create Dataset
```sql
CREATE SCHEMA IF NOT EXISTS `your-project.data_profiles`
OPTIONS(
  location="europe-west2",
  description="Dataplex data profiling and quality results"
);
```

### 2. Create Tables
Execute the complete schema from `bigquery_schema.sql`:
- `profile_scans` - Stores detailed profiling metrics
- `profile_comparisons` - Stores significant changes and comparisons

## Testing

### Unit Tests (15 tests - all passing ✅)

```bash
cd components/dataplex-components
PYTHONPATH=src ../../pipelines/venv311/Scripts/python.exe -m pytest tests/ -v
```

**Test Coverage**:
- **Profile Scan Tests (4)**: Success flow, existing scan reuse, error handling, percentile parsing  
- **Comparison Tests (6)**: Historical baselines, first runs, thresholds, continue/halt decisions
- **Storage Tests (5)**: BigQuery insertion, data types, geographic columns, error handling

### Integration Testing

```bash
# Pipeline compilation test
cd pipelines/src
../../venv311/Scripts/python.exe -m pipelines.xgboost.training.pipeline

# E2E testing (requires GCP setup)
make e2e-tests pipeline=training enable_pipeline_caching=False
```

## Configuration

### Default Settings

```python
# Profile scanning
location = "europe-west2"
profile_dataset = "data_profiles" 
profiles_table = "profile_scans"

# Comparison thresholds
deviation_threshold = 0.1  # 10%
warning_level = 0.1        # 10-20%
critical_level = 0.2       # >20%

# Historical baseline
baseline_days = 30
min_baseline_samples = 3
```

### Environment Variables

```bash
# Required for pipeline execution
export VERTEX_PROJECT_ID="your-gcp-project"
export VERTEX_LOCATION="europe-west2" 
export VERTEX_PIPELINE_ROOT="gs://your-bucket/pipeline-root"
```

## Monitoring & Alerts

### Key Metrics to Monitor

1. **Profile Scan Success Rate**: Monitor scan job completions
2. **Significant Changes**: Track WARNING/CRITICAL change frequency  
3. **Baseline Coverage**: Ensure >3 samples for reliable baselines
4. **Pipeline Halts**: Alert on CRITICAL changes causing pipeline stops

### Querying Results

```sql
-- Recent significant changes
SELECT column_name, metric_name, percent_change, significance_level
FROM `project.data_profiles.profile_comparisons` 
WHERE DATE(comparison_timestamp) = CURRENT_DATE()
  AND is_significant = TRUE
ORDER BY ABS(percent_change) DESC;

-- Profile trends over time  
SELECT DATE(scan_timestamp) as date,
       AVG(mean_value) as avg_trip_total
FROM `project.data_profiles.profile_scans`
WHERE column_name = 'trip_total' 
  AND pipeline_stage = 'post-ingestion'
GROUP BY DATE(scan_timestamp)
ORDER BY date DESC;
```

## Best Practices

### 1. Scan ID Naming Convention
- Use descriptive, consistent IDs: `{pipeline}-{stage}-{date}`  
- Example: `xgb-training-post-ingestion-20240115`

### 2. Threshold Tuning
- Start with 10% threshold, adjust based on data volatility
- Use stricter thresholds (5%) for critical production pipelines
- Monitor false positive rates

### 3. Baseline Management  
- Ensure regular pipeline runs to maintain baseline freshness
- Consider seasonal adjustments for time-series data
- Archive old profiles beyond retention period

### 4. Error Handling
- All components include comprehensive error handling
- Failed scans don't block pipeline execution
- Errors are logged with detailed context

## Troubleshooting

### Common Issues

**1. "No scan job found!" Error**
- Increase wait time if Dataplex scan takes longer than 60 seconds
- Check Dataplex service availability in your region

**2. "No historical baseline found"**  
- Expected for first runs - pipeline continues normally
- Ensure consistent table/stage names for baseline matching

**3. BigQuery Permission Errors**
- Verify service account has BigQuery Data Editor role
- Ensure dataset exists and is in correct region

**4. Geography Bounds Errors**
- Check coordinate columns exist and have valid lat/lon data
- Verify Chicago taxi data format matches expected schema

## Dependencies

```toml
[dependencies]
google-cloud-dataplex = ">=1.0.0"
google-cloud-bigquery = ">=3.25.0" 
pandas = ">=2.0.0"
kfp = ">=2.0.0"
```

## Contributing

### Adding New Components

1. Create new component in `src/dataplex_components/`
2. Add comprehensive tests in `tests/`
3. Export component in `__init__.py`  
4. Update pipeline integration
5. Document in this README

### Extending DQ Rules

Add domain-specific rules in `dq_scan.py`:
```python
# Custom business rule example
generated_rules.append(
    dataplex_v1.DataQualityRule(
        column="your_column",
        dimension="VALIDITY",
        range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
            min_value="0", max_value="1000"
        ),
        threshold=0.95
    )
)
```

## Version History

- **v0.1.0** - Initial release with profile scanning and DQ scanning
- **Current** - Integrated with XGBoost and TensorFlow pipelines, comprehensive testing suite

---

**📊 Production-Ready Data Governance for ML Pipelines**

*For questions or issues, please check the test suite for examples or refer to the main project documentation.*