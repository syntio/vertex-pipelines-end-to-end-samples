from kfp import dsl


@dsl.component(
    base_image="python:3.11",
    packages_to_install=["google-cloud-dataplex"],
)
def run_auto_dq_scan(
        project_id: str = None,
        location: str = None,
        bq_table: str = None,
        dq_scan_id: str = None,
        profile_scan_id: str = None,
) -> None:
    return None
