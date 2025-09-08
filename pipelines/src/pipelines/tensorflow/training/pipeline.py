# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime
import os
import pathlib

from kfp import compiler, dsl
from pipelines import generate_query
from bigquery_components import bq_query_to_table, extract_bq_to_dataset, run_scan
from vertex_components import (
    lookup_model,
    custom_train_job,
    import_model_evaluation,
    update_best_model,
)
from dataplex_components import (
    run_profile_scan,
    store_profile_results,
    compare_profiles,
    detect_significant_changes
)


@dsl.pipeline(name="tensorflow-train-pipeline")
def tensorflow_pipeline(
    project_id: str = os.environ.get("VERTEX_PROJECT_ID"),
    project_location: str = os.environ.get("VERTEX_LOCATION"),
    ingestion_project_id: str = os.environ.get("VERTEX_PROJECT_ID"),
    model_name: str = "simple_tensorflow",
    dataset_id: str = "preprocessing",
    dataset_location: str = os.environ.get("VERTEX_LOCATION"),
    ingestion_dataset_id: str = "chicago_taxi_trips",
    timestamp: str = "2022-12-01 00:00:00",
    staging_bucket: str = os.environ.get("VERTEX_PIPELINE_ROOT"),
    pipeline_files_gcs_path: str = os.environ.get("PIPELINE_FILES_GCS_PATH"),
    test_dataset_uri: str = "",
):
    """
    Tensorflow Keras training pipeline which:
     1. Splits and extracts a dataset from BQ to GCS
     2. Trains a model via Vertex AI CustomTrainingJob
     3. Evaluates the model against the current champion model
     4. If better the model becomes the new default model

    Args:
        project_id (str): project id of the Google Cloud project
        project_location (str): location of the Google Cloud project
        pipeline_files_gcs_path (str): GCS path where the pipeline files are located
        ingestion_project_id (str): project id containing the source bigquery data
            for ingestion. This can be the same as `project_id` if the source data is
            in the same project where the ML pipeline is executed.
        model_name (str): name of model
        model_label (str): label of model
        dataset_id (str): id of BQ dataset used to store all staging data & predictions
        dataset_location (str): location of dataset
        ingestion_dataset_id (str): dataset id of ingestion data
        timestamp (str): Optional. Empty or a specific timestamp in ISO 8601 format
            (YYYY-MM-DDThh:mm:ss.sss±hh:mm or YYYY-MM-DDThh:mm:ss).
            If any time part is missing, it will be regarded as zero.
        staging_bucket (str): Staging bucket for pipeline artifacts.
        pipeline_files_gcs_path (str): GCS path where the pipeline files are located
        test_dataset_uri (str): Optional. GCS URI of statis held-out test dataset.
    """

    # Create variables to ensure the same arguments are passed
    # into different components of the pipeline
    label_column_name = "total_fare"
    time_column = "trip_start_timestamp"
    ingestion_table = "taxi_trips"
    table_suffix = "_tf_training"  # suffix to table names
    ingested_table = "ingested_data" + table_suffix
    preprocessed_table = "preprocessed_data" + table_suffix
    train_table = "train_data" + table_suffix
    valid_table = "valid_data" + table_suffix
    test_table = "test_data" + table_suffix
    primary_metric = "rootMeanSquaredError"
    train_script_uri = f"{pipeline_files_gcs_path}/training/assets/train_tf_model.py"
    hparams = dict(
        batch_size=100,
        epochs=5,
        loss_fn="MeanSquaredError",
        optimizer="Adam",
        learning_rate=0.01,
        hidden_units=[[64, "relu"], [32, "relu"]],
        distribute_strategy="single",
        early_stopping_epochs=5,
    )

    # generate sql queries which are used in ingestion and preprocessing
    # operations

    queries_folder = pathlib.Path(__file__).parent / "queries"

    ingest_query = generate_query(
        queries_folder / "ingest.sql",
        source_dataset=f"{ingestion_project_id}.{ingestion_dataset_id}",
        source_table=ingestion_table,
        filter_column=time_column,
        target_column=label_column_name,
        filter_start_value=timestamp,
    )
    split_train_query = generate_query(
        queries_folder / "sample.sql",
        source_dataset=dataset_id,
        source_table=ingested_table,
        num_lots=10,
        lots=tuple(range(8)),
    )
    split_valid_query = generate_query(
        queries_folder / "sample.sql",
        source_dataset=dataset_id,
        source_table=ingested_table,
        num_lots=10,
        lots="(8)",
    )
    split_test_query = generate_query(
        queries_folder / "sample.sql",
        source_dataset=dataset_id,
        source_table=ingested_table,
        num_lots=10,
        lots="(9)",
    )
    data_cleaning_query = generate_query(
        queries_folder / "engineer_features.sql",
        source_dataset=dataset_id,
        source_table=train_table,
    )

    # data ingestion and preprocessing operations

    kwargs = dict(
        bq_client_project_id=project_id,
        destination_project_id=project_id,
        dataset_id=dataset_id,
        dataset_location=dataset_location,
        query_job_config=dict(write_disposition="WRITE_TRUNCATE"),
    )
    ingest = bq_query_to_table(
        query=ingest_query, table_id=ingested_table, **kwargs
    ).set_display_name("Ingest data")

    scan = (
        run_scan(
            project_id=project_id,
            location=project_location,
            bq_table=f"{project_id}.{dataset_id}.{ingested_table}",
            dq_scan_id=f"taxi-trips-scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        )
        .after(ingest)
        .set_display_name("Run DQ scan")
    )

    # exporting data to GCS from BQ
    split_train_data = (
        bq_query_to_table(query=split_train_query, table_id=train_table, **kwargs)
        .after(scan)
        .set_display_name("Split train data")
    )
    split_valid_data = (
        bq_query_to_table(query=split_valid_query, table_id=valid_table, **kwargs)
        .after(scan)
        .set_display_name("Split validation data")
    )
    split_test_data = (
        bq_query_to_table(query=split_test_query, table_id=test_table, **kwargs)
        .after(scan)
        .set_display_name("Split test data")
    )
    data_cleaning = (
        bq_query_to_table(
            query=data_cleaning_query, table_id=preprocessed_table, **kwargs
        )
        .after(split_train_data)
        .set_display_name("Clean data")
    )

    # PROFILING: After data ingestion (post-ingestion stage)
    profile_post_ingestion = run_profile_scan(
        project_id=project_id,
        location=project_location,
        bq_table=f"{project_id}.{dataset_id}.{ingested_table}",
        profile_scan_id=f"tf-training-post-ingestion-{timestamp.replace(' ', '-').replace(':', '-')}",
        pipeline_stage="post-ingestion",
        pipeline_run_id="{{$.pipeline_job_name}}",
        start_date=os.environ.get("TABLE_FILTER_START_DATE", "2022-09-01"),
        end_date=os.environ.get("TABLE_FILTER_END_DATE", "2022-09-30")
    ).after(ingest).set_display_name("Profile scan: Post-ingestion")

    # PROFILING: After preprocessing (post-preprocessing stage)
    profile_post_preprocessing = run_profile_scan(
        project_id=project_id,
        location=project_location,
        bq_table=f"{project_id}.{dataset_id}.{preprocessed_table}",
        profile_scan_id=f"tf-training-post-preprocessing-{timestamp.replace(' ', '-').replace(':', '-')}",
        pipeline_stage="post-preprocessing",
        pipeline_run_id="{{$.pipeline_job_name}}",
        start_date=os.environ.get("TABLE_FILTER_START_DATE", "2022-09-01"),
        end_date=os.environ.get("TABLE_FILTER_END_DATE", "2022-09-30")
    ).after(data_cleaning).set_display_name("Profile scan: Post-preprocessing")

    # STORAGE: Store profile results in BigQuery
    store_ingestion_profiles = store_profile_results(
        profile_results=profile_post_ingestion.outputs["profile_results"],
        project_id=project_id
    ).after(profile_post_ingestion).set_display_name("Store ingestion profiles")

    store_preprocessing_profiles = store_profile_results(
        profile_results=profile_post_preprocessing.outputs["profile_results"],
        project_id=project_id
    ).after(profile_post_preprocessing).set_display_name("Store preprocessing profiles")

    # COMPARISON: Compare current profiles with historical baselines
    compare_ingestion_profiles = compare_profiles(
        current_profile=profile_post_ingestion.outputs["profile_results"],
        project_id=project_id
    ).after(store_ingestion_profiles).set_display_name("Compare ingestion profiles")

    compare_preprocessing_profiles = compare_profiles(
        current_profile=profile_post_preprocessing.outputs["profile_results"],
        project_id=project_id
    ).after(store_preprocessing_profiles).set_display_name("Compare preprocessing profiles")

    # VALIDATION: Check for significant changes (>10% deviation)
    validate_ingestion_changes = detect_significant_changes(
        significant_changes=compare_ingestion_profiles.outputs["significant_changes"],
        project_id=project_id,
        pipeline_run_id="{{$.pipeline_job_name}}"
    ).after(compare_ingestion_profiles).set_display_name("Validate ingestion changes")

    validate_preprocessing_changes = detect_significant_changes(
        significant_changes=compare_preprocessing_profiles.outputs["significant_changes"],
        project_id=project_id,
        pipeline_run_id="{{$.pipeline_job_name}}"
    ).after(compare_preprocessing_profiles).set_display_name("Validate preprocessing changes")

    # data extraction to gcs

    train_dataset = (
        extract_bq_to_dataset(
            bq_client_project_id=project_id,
            source_project_id=project_id,
            dataset_id=dataset_id,
            table_name=preprocessed_table,
            dataset_location=dataset_location,
        )
        .after(data_cleaning, validate_ingestion_changes, validate_preprocessing_changes)
        .set_display_name("Extract train data to storage")
    ).outputs["dataset"]
    valid_dataset = (
        extract_bq_to_dataset(
            bq_client_project_id=project_id,
            source_project_id=project_id,
            dataset_id=dataset_id,
            table_name=valid_table,
            dataset_location=dataset_location,
        )
        .after(split_valid_data)
        .set_display_name("Extract validation data to storage")
    ).outputs["dataset"]
    test_dataset = (
        extract_bq_to_dataset(
            bq_client_project_id=project_id,
            source_project_id=project_id,
            dataset_id=dataset_id,
            table_name=test_table,
            dataset_location=dataset_location,
            destination_gcs_uri=test_dataset_uri,
        )
        .after(split_test_data)
        .set_display_name("Extract test data to storage")
        .set_caching_options(False)
    ).outputs["dataset"]

    existing_model = (
        lookup_model(
            model_name=model_name,
            project_location=project_location,
            project_id=project_id,
            fail_on_model_not_found=False,
        )
        .set_display_name("Lookup past model")
        .set_caching_options(False)
        .outputs["model_resource_name"]
    )

    train_model = custom_train_job(
        train_script_uri=train_script_uri,
        train_data=train_dataset,
        valid_data=valid_dataset,
        test_data=test_dataset,
        project_id=project_id,
        project_location=project_location,
        model_display_name=model_name,
        train_container_uri="europe-docker.pkg.dev/vertex-ai/training/tf-cpu.2-6:latest",  # noqa: E501
        serving_container_uri="europe-docker.pkg.dev/vertex-ai/prediction/tf2-cpu.2-6:latest",  # noqa: E501
        hparams=hparams,
        staging_bucket=staging_bucket,
        parent_model=existing_model,
    ).set_display_name("Train model")

    evaluation = import_model_evaluation(
        model=train_model.outputs["model"],
        metrics=train_model.outputs["metrics"],
        test_dataset=test_dataset,
        pipeline_job_id="{{$.pipeline_job_name}}",
        project_location=project_location,
    ).set_display_name("Import evaluation")

    with dsl.If(existing_model != "", "champion-exists"):
        update_best_model(
            challenger=train_model.outputs["model"],
            challenger_evaluation=evaluation.outputs["model_evaluation"],
            parent_model=existing_model,
            eval_metric=primary_metric,
            eval_lower_is_better=True,
            project_id=project_id,
            project_location=project_location,
        ).set_display_name("Update best model")


if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=tensorflow_pipeline,
        package_path="training.json",
        type_check=False,
    )
