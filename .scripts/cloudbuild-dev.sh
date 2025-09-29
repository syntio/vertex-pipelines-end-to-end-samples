#!/usr/bin/env bash
set -euo pipefail

usage(){
  cat <<EOF
Usage: $0 <compile|test|run> [--project <PROJECT_ID>] [--config-substs "KEY=VALUE,..."]

Examples:
  $0 compile --project my-admin-project --config-substs _PIPELINE_TEMPLATE=xgboost,_PIPELINE=training,_PIPELINE_FILES_GCS_PATH=gs://my-bucket/compiled
  $0 test --project my-admin-project
  $0 run --project my-dev-project --config-substs _PROJECT_ID=my-dev-project,_REGION=us-central1
EOF
}

if [ $# -lt 1 ]; then usage; exit 1; fi
COMMAND=$1; shift
PROJECT=''
CONFIG_SUBSTS=''

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT=$2; shift 2;;
    --config-substs) CONFIG_SUBSTS=$2; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

case "$COMMAND" in
  compile) CONFIG=cloudbuild/compile.yaml ;;
  test) CONFIG=cloudbuild/test.yaml ;;
  run) CONFIG=cloudbuild/run.yaml ;;
  *) echo "Unknown command: $COMMAND"; usage; exit 1;;
esac

GCLOUD_SUBSTS=''
if [ -n "$CONFIG_SUBSTS" ]; then
  IFS=',' read -ra PAIRS <<< "$CONFIG_SUBSTS"
  for p in "${PAIRS[@]}"; do
    GCLOUD_SUBSTS+="--substitutions=$p "
  done
fi

GCLOUD_PROJECT_FLAG=''
if [ -n "$PROJECT" ]; then
  GCLOUD_PROJECT_FLAG="--project=$PROJECT"
fi

echo "Submitting Cloud Build: $CONFIG"
set -x
gcloud builds submit . --config "$CONFIG" $GCLOUD_PROJECT_FLAG $GCLOUD_SUBSTS
