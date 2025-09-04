import os
from kfp import dsl, compiler
from google.cloud import aiplatform
from bq_query_to_table import bq_query_to_table


@dsl.pipeline(
    name="extract-chicago-taxi-data",
    description="Extract sample data from public Chicago taxi dataset",
)
def extract_pipeline():
    bq_query_to_table(
        query=f"SELECT * FROM `{os.environ.get('PROJECT_ID')}.chicago_taxi_trips.taxi_trips` LIMIT 10",
        bq_client_project_id=os.environ.get("PROJECT_ID"),
        destination_project_id=os.environ.get("PROJECT_ID"),
        dataset_id="chicago_taxi_trips",
        table_id="taxi_trips_sample_1",
        dataset_location="europe-west1",
    )


if __name__ == "__main__":
    pipeline_filename = "extract_pipeline.json"

    compiler.Compiler().compile(
        pipeline_func=extract_pipeline,
        package_path=pipeline_filename,
    )

    aiplatform.init(project=os.environ.get("PROJECT_ID"), location="europe-west1")

    aiplatform.PipelineJob(
        display_name="extract-chicago-taxi-data",
        template_path=pipeline_filename,
        pipeline_root="gs://test-for-bigquery-eu-123//pipeline-root",
        job_id="extract-chicago-taxi-data-job-28-07-2025",
        # tu se mora promijenit da nije isti svaki put
    ).run()
