from kfp import dsl


@dsl.component(
    base_image="python:3.11",
    packages_to_install=["google-cloud-dataplex", "google-cloud-bigquery"],
)
def run_scan(
        project_id: str = None,
        location: str = None,
        bq_table: str = None,
        dq_scan_id: str = None,
) -> None:
    from google.cloud import dataplex_v1, bigquery

    dataplex_client = dataplex_v1.DataScanServiceClient()
    bq_client = bigquery.Client(project=project_id)

    parent = f"projects/{project_id}/locations/{location}"
    dq_scan_full_name = f"{parent}/dataScans/{dq_scan_id}"

    project, dataset, table = bq_table.split(".")
    resource_uri = f"//bigquery.googleapis.com/projects/{project}/datasets/{dataset}/tables/{table}"
    data_source = dataplex_v1.DataSource(resource=resource_uri)

    # Step 1: Query BigQuery metadata to get column information (FAST!)
    print("Dohvaćam metadata o tablici iz INFORMATION_SCHEMA...")
    
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
        print(f"Dobio metadata za {len(columns_metadata)} kolona")
        
        print("Generiram jednostavna pravila na temelju metapodataka...")
        
        generated_rules = []
        
        for column in columns_metadata:
            column_name = column.column_name
            data_type = column.data_type
            is_nullable = column.is_nullable
            
            print(f"Analiziram kolonu: {column_name} ({data_type}, nullable: {is_nullable})")
            
            # Simple null check rules for nullable columns
            if is_nullable == "YES":
                print(f"  -> Dodajem null check rule za {column_name}")
                generated_rules.append(
                    dataplex_v1.DataQualityRule(
                        column=column_name,
                        dimension="COMPLETENESS",
                        non_null_expectation=dataplex_v1.DataQualityRule.NonNullExpectation()
                    )
                )
        
        print(f"Generirano {len(generated_rules)} jednostavnih pravila")
        
    except Exception as e:
        print(f"Greška pri dohvaćanju metapodataka: {e}")
        print("Koristim fallback pravilo...")
        generated_rules = [
            dataplex_v1.DataQualityRule(
                column="trip_total",
                dimension="COMPLETENESS",
                non_null_expectation=dataplex_v1.DataQualityRule.NonNullExpectation()
            )
        ]


    # Step 3: Create and run DQ scan with generated rules
    dq_scan = dataplex_v1.DataScan(
        data=data_source,
        data_quality_spec=dataplex_v1.DataQualitySpec(
            rules=generated_rules
        ),
    )

    try:
        dataplex_client.get_data_scan(name=dq_scan_full_name)
        print(f"DQ scan '{dq_scan_id}' već postoji.")
    except Exception:
        print(f"DQ scan nije pronađen. Kreiram novi: {dq_scan_id}")

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
    print(f"Pokrenut DQ scan job: {response}")