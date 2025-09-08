from kfp import dsl, compiler
from google.cloud import aiplatform
from bq_query_to_table import bq_query_to_table
from extract_bq_to_dataset import extract_bq_to_dataset
from dataplex_components import run_dq_scan as run_scan

from datetime import datetime
import os


@dsl.pipeline(
    name="extract-and-export-and-check-chicago-taxi-data",
    description="Query Chicago taxi data, check it and export result to GCS",
)
def extract_pipeline():
    project_id = os.environ.get("PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION", "europe-west1")
    
    query_task = bq_query_to_table(
        query=(
            f"SELECT * FROM `{project_id}.chicago_taxi_trips.taxi_trips`"
            "WHERE trip_total = 13 LIMIT 10"
        ),
        bq_client_project_id=project_id,
        destination_project_id=project_id,
        dataset_id="chicago_taxi_trips",
        table_id="taxi_trips_sample_2",
        dataset_location=location,
        query_job_config={"write_disposition": "WRITE_TRUNCATE"},
    )

    extract_task = extract_bq_to_dataset(
        bq_client_project_id=project_id,
        source_project_id=project_id,
        dataset_id="chicago_taxi_trips",
        table_name="taxi_trips_sample_2",
        dataset_location=location,
        destination_gcs_uri=(
            f"gs://{project_id}-exported-data/taxi_trips_sample_2.csv"
        ),
    )

    dq_scan = run_scan(
        project_id=project_id,
        location=location,
        bq_table=f"{project_id}.chicago_taxi_trips.taxi_trips_sample_2",
        dq_scan_id=f"taxi-trips-scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        start_date=os.environ.get("DATAPLEX_FILTER_START_DATE", "2022-09-01"),
        end_date=os.environ.get("DATAPLEX_FILTER_END_DATE", "2022-09-30"),
    )

    dq_scan.after(query_task)
    extract_task.after(dq_scan)


if __name__ == "__main__":
    project_id = os.environ.get("PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION", "europe-west1")
    pipeline_root = os.environ.get("VERTEX_PIPELINE_ROOT", f"gs://{project_id}-pipeline-root")

    pipeline_filename = "extract_export_check_pipeline.json"
    job_id = f"extract-chicago-taxi-data-job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    compiler.Compiler().compile(
        pipeline_func=extract_pipeline,
        package_path=pipeline_filename,
    )

    aiplatform.init(project=project_id, location=location)

    aiplatform.PipelineJob(
        display_name="extract-and-export-and-check-chicago-taxi-data",
        template_path=pipeline_filename,
        pipeline_root=pipeline_root,
        job_id=job_id,
    ).run()
