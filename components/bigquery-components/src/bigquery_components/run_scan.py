from kfp import dsl


@dsl.component(
    base_image="python:3.11",
    packages_to_install=["google-cloud-dataplex"],
)
def run_scan(
        project_id: str = None,
        location: str = None,
        bq_table: str = None,
        dq_scan_id: str = None,
) -> None:
    from google.cloud import dataplex_v1
    import time

    client = dataplex_v1.DataScanServiceClient()

    parent = f"projects/{project_id}/locations/{location}"
    profile_scan_id = f"{dq_scan_id}-profile"
    profile_scan_full_name = f"{parent}/dataScans/{profile_scan_id}"
    dq_scan_full_name = f"{parent}/dataScans/{dq_scan_id}"

    project, dataset, table = bq_table.split(".")

    resource_uri = f"//bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}"

    data_source = dataplex_v1.DataSource(resource=resource_uri)

    # Step 1: Create and run profile scan to collect metrics
    profile_scan = dataplex_v1.DataScan(
        data=data_source,
        data_profile_spec=dataplex_v1.DataProfileSpec(),
    )

    try:
        client.get_data_scan(name=profile_scan_full_name)
        print(f"Profile scan '{profile_scan_id}' već postoji.")
    except Exception:
        print(f"Kreiram novi profile scan: {profile_scan_id}")
        
        operation = client.create_data_scan(
            parent=parent,
            data_scan_id=profile_scan_id,
            data_scan=profile_scan,
        )
        operation.result()

    # Run profile scan
    profile_request = dataplex_v1.RunDataScanRequest(
        name=profile_scan_full_name,
    )
    
    profile_response = client.run_data_scan(request=profile_request)
    print(f"Pokrenut profile scan job: {profile_response}")
    
    print("Čekam da se profile scan završi...")
    time.sleep(60)

    # Step 2: Create DQ scan with existing rule (Phase 2 will generate rules from metrics)
    non_null_rule = dataplex_v1.DataQualityRule(
        column="trip_total",
        dimension="COMPLETENESS",
        non_null_expectation=dataplex_v1.DataQualityRule.NonNullExpectation()
    )

    dq_scan = dataplex_v1.DataScan(
        data=data_source,
        data_quality_spec=dataplex_v1.DataQualitySpec(
            rules=[non_null_rule]
        ),
    )

    try:
        client.get_data_scan(name=dq_scan_full_name)
        print(f"DQ scan '{dq_scan_id}' već postoji.")
    except Exception:
        print(f"DQ scan nije pronađen. Kreiram novi: {dq_scan_id}")

        operation = client.create_data_scan(
            parent=parent,
            data_scan_id=dq_scan_id,
            data_scan=dq_scan,
        )
        operation.result()  # čekaj da se kreira prije nego što nastaviš


    request = dataplex_v1.RunDataScanRequest(
        name=dq_scan_full_name,
    )

    response = client.run_data_scan(request=request)
    print(f"Pokrenut DQ scan job: {response}")