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

## GitHub Actions Workload Identity Federation Setup ##

# Workload Identity Pool for GitHub Actions
resource "google_iam_workload_identity_pool" "github_actions" {
  project                   = var.project_id
  workload_identity_pool_id = "gh-${join("", [for word in split("-", var.github_repository_name) : substr(word, 0, 1)])}-${substr(md5(var.project_id), 0, 12)}"
  display_name              = "GitHub Actions Identity Pool"
  description               = "Identity pool for GitHub Actions workflows"

  depends_on = [var.enable_apis]
}

# Workload Identity Provider for GitHub
resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"
  description                        = "OIDC identity provider for GitHub Actions"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.actor"            = "assertion.actor"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  # Restrict to specific repository and branches
  # NOTE: matea/cloud-build-to-github-actions branch is TEMPORARY - remove after testing
  attribute_condition = <<-EOT
    assertion.repository_owner == "${var.github_repository_owner}" &&
    assertion.repository == "${var.github_repository_owner}/${var.github_repository_name}" &&
    (
      assertion.ref == "refs/heads/develop" ||
      assertion.ref == "refs/heads/main" ||
      assertion.ref == "refs/heads/matea/cloud-build-to-github-actions" ||
      assertion.ref_type == "tag" ||
      assertion.event_name == "workflow_dispatch"
    )
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service account for GitHub Actions deployments
resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "github-actions-deploy"
  display_name = "GitHub Actions Deployment Service Account"
  description  = "Service account for GitHub Actions CI/CD deployments"
}

# Grant the service account necessary permissions for deployment
resource "google_project_iam_member" "github_actions_permissions" {
  for_each = toset(var.github_actions_sa_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.github_actions.email}"
}

# Allow GitHub Actions to impersonate the service account
resource "google_service_account_iam_member" "github_actions_workload_identity" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/*"
}

# Grant access to specific repositories (more restrictive alternative)
resource "google_service_account_iam_member" "github_actions_repo_specific" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/${var.github_repository_owner}/${var.github_repository_name}"
}
