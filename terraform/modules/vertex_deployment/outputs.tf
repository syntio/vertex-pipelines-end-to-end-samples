/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

output "pubsub_topic_id" {
  value = google_pubsub_topic.pipeline_trigger_topic.id
}

output "cf_staging_bucket_name" {
  value = google_storage_bucket.cf_staging_bucket.name
}

output "pipeline_root_bucket_name" {
  value = google_storage_bucket.pipeline_root_bucket.name
}

output "pipeline_assets_bucket_name" {
  value = google_storage_bucket.pipeline_assets_bucket.name
}

output "vertex_pipelines_sa_email" {
  value = google_service_account.pipelines_sa.email
}

output "cloudfunction_sa_email" {
  value = google_service_account.vertex_cloudfunction_sa.email
}

output "artifact_registry_repository_url" {
  value = "${google_artifact_registry_repository.container_repository.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.container_repository.repository_id}"
}

output "pipeline_config_secret_id" {
  value = google_secret_manager_secret.pipeline_config.secret_id
}

output "model_config_secret_id" {
  value = google_secret_manager_secret.model_config.secret_id
}

output "gcp_services" {
  value = google_project_service.gcp_services
  description = "GCP services enabled for the project"
}
