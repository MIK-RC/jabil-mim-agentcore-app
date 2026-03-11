#!/bin/bash
# Deploy to AWS Bedrock AgentCore
# Reads credentials from .env file
set -e
cd "$(dirname "$0")/.."

# Load environment and EXPORT variables to child processes
if [ -f .env ]; then
  set -a  # Enable auto-export mode
  source .env
  set +a  # Disable auto-export mode
fi

# Install CLI if needed
pip install -q bedrock-agentcore-starter-toolkit 2>/dev/null || true

agentcore configure -c \
  -n "${AGENT_NAME}" \
  -e "src/main.py" \
  -dt "container" \
  -r "${AWS_REGION:-us-east-1}" \
  -er "$EXECUTION_ROLE_ARN" \
  -cber "$CODEBUILD_ROLE_ARN" \
  -ecr "$ECR_REPOSITORY" \
  -ni

# Deploy
agentcore deploy -a "${AGENT_NAME}" \
  -env "SERVICENOW_INSTANCE=$SERVICENOW_INSTANCE" \
  -env "SERVICENOW_USER=$SERVICENOW_USER" \
  -env "AGENTCORE_MEMORY_ID=$AGENTCORE_MEMORY_ID" \
  -auc

echo ""
echo "Deployed. Run 'agentcore status' to check."
