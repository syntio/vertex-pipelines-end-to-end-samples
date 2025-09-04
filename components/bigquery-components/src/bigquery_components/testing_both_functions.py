import os
from kfp import dsl, compiler
from google.cloud import aiplatform
from bq_query_to_table import bq_query_to_table
from extract_bq_to_dataset import extract_bq_to_dataset


@dsl.pipeline(
    name="extract-and-export-chicago-taxi-data",
    description="Query Chicago taxi data and export result to GCS",
)
def extract_pipeline():
    query_task = bq_query_to_table(
        query=(
            f"SELECT * FROM `{os.environ.get('PROJECT_ID')}.chicago_taxi_trips.taxi_trips` "
            "WHERE trip_total = 13 "
            "LIMIT 10"
        ),
        bq_client_project_id=os.environ.get("PROJECT_ID"),
        destination_project_id=os.environ.get("PROJECT_ID"),
        dataset_id="chicago_taxi_trips",
        table_id="taxi_trips_sample_2",
        dataset_location="europe-west1",
        query_job_config={"write_disposition": "WRITE_TRUNCATE"},
    )

    extract_task = extract_bq_to_dataset(
        bq_client_project_id=os.environ.get("PROJECT_ID"),
        source_project_id=os.environ.get("PROJECT_ID"),
        dataset_id="chicago_taxi_trips",
        table_name="taxi_trips_sample_2",
        dataset_location="europe-west1",
        destination_gcs_uri=(
            "gs://test-for-bigquery-eu-123/exported_data/taxi_trips_sample_2.csv"
        ),
    )
    extract_task.after(query_task)


if __name__ == "__main__":
    from datetime import datetime

    pipeline_filename = "extract_export_pipeline.json"
    job_id = f"extract-chicago-taxi-data-job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    compiler.Compiler().compile(
        pipeline_func=extract_pipeline,
        package_path=pipeline_filename,
    )

    aiplatform.init(project=os.environ.get("PROJECT_ID"), location="europe-west1")

    aiplatform.PipelineJob(
        display_name="extract-and-export-chicago-taxi-data",
        template_path=pipeline_filename,
        pipeline_root="gs://test-for-bigquery-eu-123/pipeline-root",
        job_id=job_id,
    ).run()
