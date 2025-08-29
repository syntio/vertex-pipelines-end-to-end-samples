-- BigQuery schema for storing Dataplex profile scan results
-- Execute these in BigQuery Console or via terraform

-- 1. Create dataset for storing profiles
CREATE SCHEMA IF NOT EXISTS `syntio-ai-ops.data_profiles`
OPTIONS(
  location="europe-west2",
  description="Dataplex data profiling and quality results"
);

-- 2. Create profile scans results table
CREATE TABLE IF NOT EXISTS `syntio-ai-ops.data_profiles.profile_scans` (
  -- Metadata
  scan_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  pipeline_run_id STRING NOT NULL,
  pipeline_stage STRING NOT NULL,  -- "post-ingestion" | "post-preprocessing"
  table_name STRING NOT NULL,
  scan_id STRING NOT NULL,

  -- Column-level metrics
  column_name STRING NOT NULL,
  data_type STRING,

  -- Numeric statistics
  min_value FLOAT64,
  max_value FLOAT64,
  mean_value FLOAT64,
  median_value FLOAT64,
  stddev_value FLOAT64,
  variance_value FLOAT64,

  -- Data quality metrics
  null_count INT64,
  total_count INT64,
  null_percentage FLOAT64,

  -- Categorical metrics
  cardinality INT64,
  unique_count INT64,
  top_values ARRAY<STRUCT<value STRING, count INT64>>,

  -- Distribution samples (for advanced analysis)
  percentile_5 FLOAT64,
  percentile_25 FLOAT64,
  percentile_75 FLOAT64,
  percentile_95 FLOAT64,

  -- Geographic metrics (for Chicago taxi data)
  geographic_bounds STRUCT<
    min_lat FLOAT64,
    max_lat FLOAT64,
    min_lon FLOAT64,
    max_lon FLOAT64
  >
)
PARTITION BY DATE(scan_timestamp)
CLUSTER BY pipeline_stage, table_name, column_name;

-- 3. Create profile comparisons table
CREATE TABLE IF NOT EXISTS `syntio-ai-ops.data_profiles.profile_comparisons` (
  comparison_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  pipeline_run_id STRING NOT NULL,
  baseline_run_id STRING NOT NULL,

  table_name STRING NOT NULL,
  column_name STRING NOT NULL,
  pipeline_stage STRING NOT NULL,

  metric_name STRING NOT NULL,  -- "mean", "stddev", "null_percentage", etc.
  current_value FLOAT64,
  baseline_value FLOAT64,
  absolute_change FLOAT64,
  percent_change FLOAT64,

  is_significant BOOLEAN,       -- TRUE if exceeds deviation_threshold
  deviation_threshold FLOAT64,  -- Usually 0.1 (10%)

  significance_level STRING     -- "WARNING" | "CRITICAL"
)
PARTITION BY DATE(comparison_timestamp)
CLUSTER BY pipeline_stage, table_name;