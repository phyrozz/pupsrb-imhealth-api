#!/bin/bash
set -e

# Usage: ./deploy.sh <stage> <service_name>
# Example: ./deploy.sh dev auth

STAGE=$1
SERVICE_NAME=$2

if [ -z "$STAGE" ] || [ -z "$SERVICE_NAME" ]; then
  echo "Usage: $0 <stage> <service_name>"
  exit 1
fi

SERVICE_PATH="services/$SERVICE_NAME"

if [ ! -d "$SERVICE_PATH" ]; then
  echo "Service folder not found: $SERVICE_PATH"
  exit 1
fi

if ! command -v serverless &> /dev/null; then
  echo "'serverless' command not found. Make sure it's installed globally (npm i -g serverless)"
  exit 1
fi

if [ "$STAGE" = "prod" ]; then
  AWS_PROFILE="imhealth-prod"
elif [ "$STAGE" = "dev" ]; then
  AWS_PROFILE="imhealth-dev"
else
  echo "Unknown stage '$STAGE'. Use 'dev' or 'prod'."
  exit 1
fi

echo "Deploying service '$SERVICE_NAME' to stage '$STAGE' (profile: $AWS_PROFILE)..."
cd "$SERVICE_PATH"

AWS_PROFILE="$AWS_PROFILE" serverless deploy --stage "$STAGE"

cd - > /dev/null
echo "Deployment complete for service '$SERVICE_NAME' ($STAGE)"
