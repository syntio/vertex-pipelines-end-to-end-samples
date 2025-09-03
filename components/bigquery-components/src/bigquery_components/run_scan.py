import os
from kfp.dsl import component


@component(
    base_image=(
        f"europe-west2-docker.pkg.dev/{os.environ.get('PROJECT_ID')}/"
        "ml-ops-turbo-dev-ml-pipeline-containers/ml-pipeline-base:latest"
    ),
)
def run_scan(
    project_id: str = None,
    location: str = None,
    bq_table: str = None,
    dq_scan_id: str = None,
) -> None:
    from google.cloud import dataplex_v1, bigquery
    import time

    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery.Client(project=project_id)

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

    # Step 3: Create and run DQ scan with generated rules
    dq_scan = dataplex_v1.DataScan(
        data=data_source,
        data_quality_spec=dataplex_v1.DataQualitySpec(rules=generated_rules),
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
            return
        elif state in (
            dataplex_v1.DataScanJob.State.FAILED,
            dataplex_v1.DataScanJob.State.CANCELLED,
        ):
            raise RuntimeError(f"DQ job failed ❌ Status: {job.state.name}")

        # Job still running, wait before next poll
        time.sleep(15)
