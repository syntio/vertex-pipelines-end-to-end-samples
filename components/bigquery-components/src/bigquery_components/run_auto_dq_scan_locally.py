def run_auto_dq_scan_test(
        project_id: str = None,
        location: str = None,
        bq_table: str = None,
        dq_scan_id: str = None,
        profile_scan_id: str = None,
):
    import google.auth
    from google.cloud import dataplex_v1
    from google.protobuf import duration_pb2
    import time

    credentials, _ = google.auth.default()
    dq_client = dataplex_v1.DataScanServiceClient(credentials=credentials)

    parent = f"projects/{project_id}/locations/{location}"
    #
    profile_scan = dataplex_v1.DataScan(
        data_scan_type="DATA_PROFILE",
        data=dataplex_v1.DataSource(
            entity=f"bq://{bq_table}"
        ),
        data_profile_spec=dataplex_v1.DataProfileSpec(),
    )


#
# profile_request = dataplex_v1.CreateDataScanRequest(
#    parent=parent,
#    data_scan_id=profile_scan_id,
#    data_scan=profile_scan,
# )
#
# dq_client.create_data_scan(request=profile_request)

# print(f"[INFO] Started profile scan: {profile_scan_id}. Waiting for 30s...")
# time.sleep(30)
#
# dq_scan = dataplex_v1.DataScan(
#    data_scan_type="DATA_QUALITY",
#    data=dataplex_v1.DataSource(
#        entity=f"bq://{bq_table}"
#    ),
#    data_quality_spec=dataplex_v1.DataQualitySpec(
#        rules=[],
#        post_scan_actions=[
#            dataplex_v1.DataQualitySpec.PostScanActions.AUTO_GENERATE
#        ]
#    ),
# )
#
# dq_request = dataplex_v1.CreateDataScanRequest(
#    parent=parent,
#    data_scan_id=dq_scan_id,
#    data_scan=dq_scan,
# )
#
# dq_client.create_data_scan(request=dq_request)
#
# print(f"[INFO] Started AutoDQ scan: {dq_scan_id}")

if __name__ == "__main__":
    run_auto_dq_scan_test(project_id="syntio-ai-ops",
                          location="europe-west1",
                          bq_table="syntio-ai-ops.chicago_taxi_trips.taxi_trips_sample_2",
                          dq_scan_id="taxi-trips-auto-dq-scan",
                          profile_scan_id="taxi-trips-profile-scan")
