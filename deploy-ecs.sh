#!/usr/bin/env bash
set -euo pipefail

# Development only. Builds and publishes :latest, then registers a Fargate task
# definition. It deliberately does not start a task or create an ECS service.

usage() {
  cat <<'EOF'
Usage: ./deploy-ecs.sh <service-name> [repository-name]

The service must provide services/<service-name>/Dockerfile and
services/<service-name>/ecs-task-definition.json. The image is always pushed as
:latest and a new task-definition revision is always registered.
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 2
fi

SERVICE_NAME=$1
REPOSITORY_NAME=${2:-"pupsrb-imhealth/${SERVICE_NAME}"}
AWS_PROFILE_NAME=imhealth-dev
REGION=ap-southeast-1
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SERVICE_PATH="$SCRIPT_DIR/services/$SERVICE_NAME"
DOCKERFILE="$SERVICE_PATH/Dockerfile"
TASK_TEMPLATE="$SERVICE_PATH/ecs-task-definition.json"
TASK_FAMILY="pupsrb-imhealth-${SERVICE_NAME//_/-}"
CONTAINER_NAME="$TASK_FAMILY"

[[ $SERVICE_NAME =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo 'Invalid service name.' >&2; exit 2; }
command -v aws >/dev/null || { echo 'AWS CLI is required.' >&2; exit 1; }
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
command -v jq >/dev/null || { echo 'jq is required.' >&2; exit 1; }
[[ -f $DOCKERFILE ]] || { echo "Dockerfile not found: $DOCKERFILE" >&2; exit 1; }
[[ -f $TASK_TEMPLATE ]] || { echo "Task definition template not found: $TASK_TEMPLATE" >&2; exit 1; }

aws_dev() { aws --profile "$AWS_PROFILE_NAME" --region "$REGION" "$@"; }

ACCOUNT_ID=$(aws_dev sts get-caller-identity --query Account --output text)
TASK_EXECUTION_ROLE_ARN=$(aws_dev ssm get-parameter \
  --name /pupsrb-imhealth/dev/iam/ecs_task_execution_role_arn \
  --query 'Parameter.Value' --output text)
TASK_ROLE_ARN=$(aws_dev ssm get-parameter \
  --name /pupsrb-imhealth/dev/iam/ecs_task_role_arn \
  --query 'Parameter.Value' --output text)
REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
IMAGE_URI="$REGISTRY/$REPOSITORY_NAME:latest"

if ! REPOSITORY_ERROR=$(aws_dev ecr describe-repositories --repository-names "$REPOSITORY_NAME" 2>&1); then
  if [[ $REPOSITORY_ERROR != *RepositoryNotFoundException* ]]; then
    echo "Unable to inspect ECR repository '$REPOSITORY_NAME': $REPOSITORY_ERROR" >&2
    exit 1
  fi
  aws_dev ecr create-repository --repository-name "$REPOSITORY_NAME" --image-scanning-configuration scanOnPush=true >/dev/null
fi

aws_dev ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
docker build --file "$DOCKERFILE" --tag "$IMAGE_URI" "$SCRIPT_DIR"
docker push "$IMAGE_URI"

LOG_GROUP_NAME=$(jq -r --arg container_name "$CONTAINER_NAME" \
  '.containerDefinitions[] | select(.name == $container_name) | .logConfiguration.options["awslogs-group"] // empty' \
  "$TASK_TEMPLATE")
[[ -n $LOG_GROUP_NAME ]] || { echo "Container '$CONTAINER_NAME' must define an awslogs-group." >&2; exit 1; }
LOG_GROUP=$(aws_dev logs describe-log-groups --log-group-name-prefix "$LOG_GROUP_NAME" \
  --query "logGroups[?logGroupName=='$LOG_GROUP_NAME'].logGroupName" --output text)
if [[ $LOG_GROUP != "$LOG_GROUP_NAME" ]]; then
  aws_dev logs create-log-group --log-group-name "$LOG_GROUP_NAME" >/dev/null
fi

TEMPORARY_DEFINITION=$(mktemp)
trap 'rm -f "$TEMPORARY_DEFINITION"' EXIT
jq \
  --arg family "$TASK_FAMILY" \
  --arg execution_role "$TASK_EXECUTION_ROLE_ARN" \
  --arg task_role "$TASK_ROLE_ARN" \
  --arg container_name "$CONTAINER_NAME" \
  --arg image "$IMAGE_URI" \
  '
    .family = $family |
    .executionRoleArn = $execution_role |
    .taskRoleArn = $task_role |
    (.containerDefinitions | map(select(.name == $container_name)) | length) as $matches |
    if $matches != 1 then error("expected exactly one matching container") else . end |
    (.containerDefinitions[] | select(.name == $container_name) | .image) = $image
  ' "$TASK_TEMPLATE" > "$TEMPORARY_DEFINITION"

TASK_DEFINITION_ARN=$(aws_dev ecs register-task-definition \
  --cli-input-json "file://$TEMPORARY_DEFINITION" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
printf 'Published %s\nRegistered %s\n' "$IMAGE_URI" "$TASK_DEFINITION_ARN"
