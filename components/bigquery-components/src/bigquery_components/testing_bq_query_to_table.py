from kfp import dsl, compiler
from google.cloud import aiplatform
from .bq_query_to_table import bq_query_to_table


@dsl.pipeline(
    name="extract-chicago-taxi-data",
    description="Extract sample data from public Chicago taxi dataset",
)
def extract_pipeline():
    bq_query_to_table(
        query="SELECT * FROM `syntio-ai-ops.chicago_taxi_trips.taxi_trips` LIMIT 10",
        bq_client_project_id="syntio-ai-ops",
        destination_project_id="syntio-ai-ops",
        dataset_id="chicago_taxi_trips",
        table_id="taxi_trips_sample_1",
        dataset_location="US",
    )


if __name__ == "__main__":
    pipeline_filename = "extract_pipeline.json"

    compiler.Compiler().compile(
        pipeline_func=extract_pipeline,
        package_path=pipeline_filename,
    )

    aiplatform.init(project="syntio-ai-ops", location="us-central1")

    aiplatform.PipelineJob(
        display_name="extract-chicago-taxi-data",
        template_path=pipeline_filename,
        pipeline_root="gs://test_bucket_for_bigquery_123//pipeline-root",  # prilagodi svom bucketu
        job_id="extract-chicago-taxi-data-job-v2",
    ).run()
