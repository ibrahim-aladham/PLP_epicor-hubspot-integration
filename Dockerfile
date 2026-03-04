FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/workspace/epicor-hubspot-integration

# System tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl openssh-client vim tmux jq ca-certificates \
    gnupg lsb-release apt-transport-https gcc \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code
RUN npm install -g @anthropic-ai/claude-code

# Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

# Azure Functions Core Tools v4 (via npm - avoids Debian repo signing issues)
RUN npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Project files
WORKDIR /workspace/epicor-hubspot-integration
COPY . .

# Python dependencies
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Create logs directory
RUN mkdir -p logs

CMD ["/bin/bash"]
