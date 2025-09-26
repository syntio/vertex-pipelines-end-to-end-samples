from kfp.dsl import component

@component(
    base_image=(
        "europe-west2-docker.pkg.dev/syntio-ai-ops/"
        "ml-ops-turbo-dev-ml-pipeline-containers/ml-pipeline-base:latest"
    ),
    packages_to_install=[
    "google-cloud-dataplex>=1.0.0",
    "google-cloud-bigquery>=3.25.0",
    "google-cloud-monitoring>=2.15.0",
    ],
)

def run_scan(
    project_id: str = None,
    location: str = None,
    bq_table: str = None,
    dq_scan_id: str = None,
    # TIME FILTERING PARAMETERS (REQUIRED)
    start_date: str = "",  # YYYY-MM-DD format (MANDATORY)
    end_date: str = "",  # YYYY-MM-DD format (MANDATORY)
    date_column: str = "trip_start_timestamp",  # Column to filter on
) -> None:
    import time
    from datetime import datetime
    from google.cloud import dataplex_v1
    from google.cloud import monitoring_v3
    from .cost_aware_client import Client as bigquery_Client
    import google.cloud.logging
    
    def push_metric(project_id, metric_type, value, labels=None):
        client = monitoring_v3.MetricServiceClient()
        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/{metric_type}"
        if labels:
            series.metric.labels.update(labels)
        series.resource.type = "global"

        point = monitoring_v3.Point()
        point.value.double_value = float(value)

        point.interval.end_time = datetime.now()

        series.points.append(point)
        project_name = f"projects/{project_id}"
        client.create_time_series(name=project_name, time_series=[series])
        time.sleep(1)
        
    # COST PROTECTION: Enforce time filtering
    if not start_date or not end_date:
        raise ValueError("Time filtering required - provide start_date and end_date")

    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery_Client(project=project_id)

    parent = f"projects/{project_id}/locations/{location}"
    dq_scan_full_name = f"{parent}/dataScans/{dq_scan_id}"

    try:
        project, dataset, table = bq_table.split(".")
    except ValueError:
        raise ValueError(f"Invalid bq_table format:'{bq_table}'.")
    resource_uri = (
        f"//bigquery.googleapis.com/projects/{project}"
        f"/datasets/{dataset}/tables/{table}"
    )
    data_source = dataplex_v1.DataSource(resource=resource_uri)

    # Step 1: Query BigQuery metadata to get column information (FAST!)
    print("Fetching table metadata from INFORMATION_SCHEMA...")

    metadata_query = f"""
    SELECT
        column_name,
        data_type,
        is_nullable,
        ordinal_position
    FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name = '{table}'
    ORDER BY ordinal_position
    """

    try:
        query_job = bq_client.query(metadata_query)
        columns_metadata = list(query_job.result())
        print(f"Fetched metadata for {len(columns_metadata)} columns.")

        print("Generating simple rules based on table metadata...")

        generated_rules = []
        for column in columns_metadata:
            column_name = column.column_name
            data_type = column.data_type
            is_nullable = column.is_nullable

            print(
                f"Analyzing column: {column_name} "
                f"({data_type}, nullable: {is_nullable})"
            )

            # Simple null check rules for nullable columns
            if is_nullable == "YES":
                print(f"  -> Adding null check rule for {column_name}")
                non_null_exp = dataplex_v1.DataQualityRule.NonNullExpectation()
                generated_rules.append(
                    dataplex_v1.DataQualityRule(
                        column=column_name,
                        dimension="COMPLETENESS",
                        non_null_expectation=non_null_exp,
                    )
                )

        print(f"Generated {len(generated_rules)} simple rules")

    except Exception as e:
        print(f"Error while fetching table metadata: {e}")
        print("Using fallback rule...")
        generated_rules = [
            dataplex_v1.DataQualityRule(
                column="trip_total",
                dimension="COMPLETENESS",
                non_null_expectation=dataplex_v1.DataQualityRule.NonNullExpectation(),
            )
        ]

    print("Generating smart DQ rules based on profiling results...")
    strict_mode = True

    lower_pct = 1 if strict_mode else 5
    upper_pct = 99 if strict_mode else 95

    profiling_sql = f"""
    SELECT
      APPROX_QUANTILES(trip_seconds, 100)[OFFSET({lower_pct})] AS trip_seconds_p{lower_pct},
      APPROX_QUANTILES(trip_seconds, 100)[OFFSET({upper_pct})] AS trip_seconds_p{upper_pct}
    FROM `{project}.{dataset}.{table}`
    """
    profile_row = list(bq_client.query(profiling_sql).result())[0]
    low = profile_row[f"trip_seconds_p{lower_pct}"]
    high = profile_row[f"trip_seconds_p{upper_pct}"]

    generated_rules.append(
        dataplex_v1.DataQualityRule(
            column="trip_seconds",
            dimension="VALIDITY",
            range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
                min_value=str(low), max_value=str(high)
            ),
            threshold=0.99,
        )
    )
    print(f"Adding trip_seconds rule: between {low:.2f} and {high:.2f}")

    # Add smart rule: trip_miles > 0
    print("Adding a rule: trip_miles > 0")
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            column="trip_miles",
            dimension="VALIDITY",
            range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
                min_value="0.00001"
            ),
        )
    )

    # Add rule: fare > 0 and fare < 1500
    print("Adding rule for fare : 0 < fare < 1500")
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            column="fare",
            dimension="VALIDITY",
            range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
                min_value="0.0", max_value="1500"
            ),
        )
    )

    # Add smart rules: lat/lon bounds (Chicago area)
    coord_rules = [
        ("pickup_latitude", "41.644", "42.023"),
        ("dropoff_latitude", "41.644", "42.023"),
        ("pickup_longitude", "-87.940", "-87.524"),
        ("dropoff_longitude", "-87.940", "-87.524"),
    ]

    for col, min_val, max_val in coord_rules:
        print(f"Adding geo-bound rule for {col}: [{min_val}, {max_val}]")
        generated_rules.append(
            dataplex_v1.DataQualityRule(
                column=col,
                dimension="VALIDITY",
                range_expectation=dataplex_v1.DataQualityRule.RangeExpectation(
                    min_value=min_val, max_value=max_val
                ),
                threshold=0.99,
            )
        )

    # Compound row condition: fare + tips + tolls >= 0
    print("Adding a rule for a condition: fare + tips + tolls >= 0")
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            dimension="INTEGRITY",
            row_condition_expectation=dataplex_v1.DataQualityRule.RowConditionExpectation(
                sql_expression="fare + IFNULL(tips,0) + IFNULL(tolls,0) >= 0"
            ),
        )
    )

    # Timestamp sanity check
    print("Adding a rule for trip_start_timestamp not in the future.")
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            dimension="FRESHNESS",
            row_condition_expectation=dataplex_v1.DataQualityRule.RowConditionExpectation(
                sql_expression="trip_start_timestamp <= CURRENT_TIMESTAMP()"
            ),
        )
    )

    print("Adding a rule for payment type to accept only specific payment types.")
    acceptable_payment_types = [
        "Prcard",
        "Mobile",
        "Credit Card",
        "Pcard",
        "Prepaid",
        "Cash",
        "Way2ride",
    ]
    generated_rules.append(
        dataplex_v1.DataQualityRule(
            column="payment_type",
            dimension="VALIDITY",
            set_expectation=dataplex_v1.DataQualityRule.SetExpectation(
                values=acceptable_payment_types
            ),
        )
    )

    row_filter = (
        f"{date_column} >= '{start_date} 00:00:00' "
        f"AND {date_column} <= '{end_date} 23:59:59'"
    )

    dq_scan = dataplex_v1.DataScan(
        data=data_source,
        data_quality_spec=dataplex_v1.DataQualitySpec(
            rules=generated_rules,
            row_filter=row_filter,   
        ),
    )

    try:
        dataplex_client.get_data_scan(name=dq_scan_full_name)
        print(f"DQ scan '{dq_scan_id}' already exists.")
    except Exception:
        print(f"DQ scan not found. Creating a new one: {dq_scan_id}")

        operation = dataplex_client.create_data_scan(
            parent=parent,
            data_scan_id=dq_scan_id,
            data_scan=dq_scan,
        )
        operation.result()  # čekaj da se kreira prije nego što nastaviš

    request = dataplex_v1.RunDataScanRequest(
        name=dq_scan_full_name,
    )

    response = dataplex_client.run_data_scan(request=request)
    print(f"DQ scan job started: {response}")
    job_name = response.job.name
    while True:
        job = dataplex_client.get_data_scan_job(name=job_name)
        state = job.state
        print(f"Checking status of DQ job: {state.name}")

        if state == dataplex_v1.DataScanJob.State.SUCCEEDED:
            print("DQ job finished successfully ✅")
            time.sleep(10)
            # Initialize a Logging client
            logging_client = google.cloud.logging.Client(project=project_id)

            # Get the job UUID from the end of the job name
            job_uuid = job.name.split('/')[-1]

            # Build a log filter to find the correct event
            log_filter = (
                f'resource.type="dataplex.googleapis.com/DataScan" '
                f'jsonPayload.jobId="{job_uuid}" '
                f'jsonPayload.dataQuality:*'  # This filters for events with the dataQuality object
            )

            print(f"Searching for log with filter: {log_filter}")

            # Get the log entries that match the filter
            log_entries = list(logging_client.list_entries(filter_=log_filter))
            
            if not log_entries:
                print("No matching log entries found. Cannot retrieve results.")
                break
            
            # The first entry should be the one we need - actually first is the only one
            log_entry = log_entries[0]
            
            # Extract the data quality result from the JSON payload
            try:
                dq_event = log_entry.payload
                dq_result = dq_event.get("dataQuality")
                
                if not dq_result:
                    print("Data quality result not found in log payload.")
                    break
                    
                print("\n--- SUCCESSFULLY EXTRACTED DQ RESULTS FROM LOGS ---")
                overall_score = dq_result.get('score', 0)
                total_rows = dq_result.get('rowCount', 0)
                print(f"Overall Score: {overall_score:.2f}")
                print(f"Total rows scanned: {total_rows}")

                # Overall score
                push_metric(
                    project_id=project_id,
                    metric_type="data_quality/overall_score",
                    value=overall_score,
                    labels={"scan_id": dq_scan_id}
                )
                # Total rows scanned
                push_metric(
                    project_id=project_id,
                    metric_type="data_quality/rows_scanned",
                    value=total_rows,
                    labels={"scan_id": dq_scan_id}
                )
                
               # 2. Iterate through dimension scores and push them
                for dimension, score in dq_result['dimensionScore'].items():
                    push_metric(
                        project_id=project_id,
                        metric_type="data_quality/dimension_score",
                        value=score,

                        labels={"scan_id": dq_scan_id, "dimension": dimension}
                    )
                print("Pushed all dimension scores.")

                # 3. Iterate through column scores and push them
                for column, score in dq_result['columnScore'].items():
                    push_metric(
                        project_id=project_id,
                        metric_type="data_quality/column_score",
                        value=score,
                        labels={"scan_id": dq_scan_id, "column": column}
                    )
                print("Pushed all column scores.")

                # 4. Push boolean values as 1 or 0 for easier graphing
                for dimension, passed in dq_result['dimensionPassed'].items():
                    push_metric(
                        project_id=project_id,
                        metric_type="data_quality/dimension_passed",
                        value=1.0 if passed else 0.0,
                        labels={"scan_id": dq_scan_id, "dimension": dimension}
                    )
                print("Pushed all dimension pass/fail statuses.")

            except Exception as e:
                print(f"Failed to parse log entry: {e}")
            
            break
            
        elif state in (
            dataplex_v1.DataScanJob.State.FAILED,
            dataplex_v1.DataScanJob.State.CANCELLED,
        ):
            raise RuntimeError(f"DQ job failed ❌ Status: {job.state.name}")
        
        time.sleep(15)
