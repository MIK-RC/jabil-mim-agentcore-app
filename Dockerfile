# AIOps Proactive Workflow - AgentCore Runtime
# Deployed on AWS Bedrock AgentCore

# FROM python:3.12-slim
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy configuration
COPY config/ ./config/

# Copy source code
COPY src/ ./src/

# Copy environment file (if present)
COPY .env* ./

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV AIOPS_CONFIG_DIR=/app/config

# Expose the AgentCore server port
EXPOSE 8080

# Start the AgentCore server
CMD ["python", "-m", "src.main"]
