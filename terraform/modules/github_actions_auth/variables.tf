/**
 * Copyright 2024 Google LLC
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

variable "project_id" {
  description = "The GCP project ID"
  type        = string
}

variable "github_repository_owner" {
  description = "GitHub repository owner (organization or user)"
  type        = string
  # No default - must be explicitly provided
}

variable "github_repository_name" {
  description = "GitHub repository name"
  type        = string
  # No default - must be explicitly provided
}

variable "github_actions_sa_roles" {
  description = "List of IAM roles to grant to the GitHub Actions service account"
  type        = list(string)
  default = [
    # Terraform state management
    "roles/storage.admin",

    # Terraform resource management
    "roles/editor",

    # IAM management for service accounts
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountKeyAdmin",

    # Secret Manager
    "roles/secretmanager.admin",

    # Artifact Registry
    "roles/artifactregistry.admin",

    # Cloud Functions
    "roles/cloudfunctions.admin",
    "roles/cloudbuild.builds.editor",

    # Pub/Sub
    "roles/pubsub.admin",

    # Vertex AI
    "roles/aiplatform.admin",

    # Cloud Storage
    "roles/storage.objectAdmin",

    # Enable APIs
    "roles/serviceusage.serviceUsageAdmin",

    # Monitoring and logging
    "roles/monitoring.editor",
    "roles/logging.configWriter"
  ]
}

variable "enable_apis" {
  description = "Dependency to ensure APIs are enabled before creating resources"
  type        = any
  default     = null
}

# workload_identity_pool_id is now auto-generated from project_id + repository hash
