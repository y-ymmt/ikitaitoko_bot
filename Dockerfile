# Bedrock AgentCore Runtime base image
FROM public.ecr.aws/bedrock-agentcore/runtime:latest

# Install Node.js for npx (MCP server)
USER root
RUN dnf install -y nodejs npm && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Pre-install Notion MCP server to speed up startup
RUN npm install -g @notionhq/notion-mcp-server

# Switch back to non-root user
USER 1000

# Copy application code
COPY --chown=1000:1000 . /var/task/

# Install Python dependencies
WORKDIR /var/task
RUN pip install --no-cache-dir -r requirements.txt

# Set entrypoint
ENV AGENTCORE_ENTRYPOINT=agentcore_app.py
