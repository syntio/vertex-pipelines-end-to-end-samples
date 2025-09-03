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

output "workload_identity_provider" {
  description = "The full name of the workload identity provider"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "service_account_email" {
  description = "Email of the GitHub Actions service account"
  value       = google_service_account.github_actions.email
}

output "workload_identity_pool_id" {
  description = "The workload identity pool ID"
  value       = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
}

output "github_actions_setup_instructions" {
  description = "Instructions for setting up GitHub Actions secrets"
  value       = <<-EOT
    Add these secrets to your GitHub repository:
    
    1. WORKLOAD_IDENTITY_PROVIDER: ${google_iam_workload_identity_pool_provider.github.name}
    2. SERVICE_ACCOUNT: ${google_service_account.github_actions.email}
    3. PROJECT_ID_DEV: your-dev-project-id
    4. PROJECT_ID_TEST: your-test-project-id  
    5. PROJECT_ID_PROD: your-prod-project-id
    6. REGION: ${var.project_id != "" ? "europe-west2" : "your-preferred-region"}
    
    Set up GitHub Environments:
    - development (no protection rules)
    - test (optional protection rules)
    - production (require reviewers, restrict to main branch)
  EOT
}

output "terraform_backend_bucket" {
  description = "GCS bucket name for terraform state (format: PROJECT_ID-tfstate)"
  value       = "${var.project_id}-tfstate"
}
