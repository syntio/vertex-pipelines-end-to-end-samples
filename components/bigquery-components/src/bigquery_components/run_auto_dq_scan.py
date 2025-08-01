from kfp.dsl import component


@dsl.component
def run_auto_dq_scan(
    project_id: str,
    location: str,
    bq_table: str,
    scan_id: str,
):
    import subprocess

    # 1. Profile Scan (ako već nije napravljen)
    subprocess.run([
        "gcloud", "dataplex", "data-profiles", "create",
        scan_id,
        "--project", project_id,
        "--location", location,
        "--resource", f"bq://{bq_table}",
        "--display-name", f"{scan_id}-profile",
    ], check=True)

    # 2. AutoDQ Scan
    subprocess.run([
        "gcloud", "dataplex", "data-quality-scans", "create",
        scan_id,
        "--project", project_id,
        "--location", location,
        "--resource", f"bq://{bq_table}",
        "--display-name", f"{scan_id}-dq",
        "--auto",  # Triggers auto-rule generation based on profiling
    ], check=True)
