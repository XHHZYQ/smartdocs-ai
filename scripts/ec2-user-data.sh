#!/bin/bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

APP_DIR="/opt/smartdocs"
REPO_URL="${REPO_URL:-https://github.com/XHHZYQ/smartdocs-ai.git}"
ECR_REGISTRY="${ECR_REGISTRY:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# 1) Install dependencies
apt-get update
apt-get install -y ca-certificates curl git gnupg lsb-release unzip awscli

# 2) Install Docker CE + Docker Compose plugin (Ubuntu)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3) Start Docker and add ubuntu user to docker group
systemctl enable --now docker
usermod -aG docker ubuntu

# 4) Prepare app dir
mkdir -p "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

# 5) Clone repository
sudo -u ubuntu bash -lc "git clone \"$REPO_URL\" \"$APP_DIR\""

# 6) ECR login (required for image pull)
if [ -n "$ECR_REGISTRY" ]; then
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"
fi

# 7) Create prod env file
cat > "$APP_DIR/.env.prod" <<EOF
JWT_SECRET_KEY=$(openssl rand -hex 32)
EMBEDDING_API_KEY=TODO_REPLACE_WITH_REAL_KEY
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
CHAT_MODEL=deepseek-ai/DeepSeek-V4-Flash
RATE_LIMIT_ENABLED=true
EOF

chown ubuntu:ubuntu "$APP_DIR/.env.prod"
chmod 600 "$APP_DIR/.env.prod"

# 8) Initial startup
sudo -u ubuntu bash -lc "
  cd '$APP_DIR'
  docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
  docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head || true
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
"

echo "EC2 bootstrap complete"