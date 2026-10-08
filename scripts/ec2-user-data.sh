#!/usr/bin/env bash
# EC2 user-data 模板：实例首次启动时自动执行
# 职责：装 Docker + 拉项目代码 + 配置 ECR 登录 + 首次启动服务
#
# 使用方式
# 1. 创建 EC2 时把这个文件作为 user-data 贴入
# 2. 实例角色需要附加权限：
#    - AmazonEC2ContainerRegistryReadOnly（拉 ECR 镜像）
#    - AmazonSSMManagedInstanceCore（可选，方便日后运维）
# 3. 安全组开放 80 端口给公网（443 留给以后加 SSL）

set -euo pipefail

APP_DIR="/opt/smartdocs"
REPO_URL="${REPO_URL}"          # 例：https://github.com/your-org/smartdocs-ai
ECR_REGISTRY="${ECR_REGISTRY}"  # 例：123456789012.dkr.ecr.us-east-1.amazonaws.com
AWS_REGION="${AWS_REGION:-us-east-1}"

# ===== 1. 装 Docker + docker compose plugin =====
amazon-linux-extras install docker -y
systemctl enable --now docker

# docker compose v2 plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# ec2-user 加入 docker 组，免 sudo
usermod -aG docker ec2-user

# ===== 2. 拉项目代码 =====
yum install -y git
mkdir -p "$APP_DIR"
chown ec2-user:ec2-user "$APP_DIR"

# 用 token 拉私有仓库（建议用 AWS Secrets Manager + git credential helper）
# 这里简化为公开仓库
runuser -u ec2-user -- git clone "$REPO_URL" "$APP_DIR"

cd "$APP_DIR"

# ===== 3. ECR 登录（user-data 在实例启动时跑一次） =====
# 后续 deploy.sh 不用再 login，docker 会缓存凭据
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ===== 4. 创建 .env.prod（敏感配置，user-data 生成或手动 SSM 拉） =====
# 生产 env 文件不放仓库，这里用占位符，实际值用 SSM Parameter Store 或 Secrets Manager
cat > "$APP_DIR/.env.prod" <<EOF
JWT_SECRET_KEY=$(openssl rand -hex 32)
EMBEDDING_API_KEY=TODO_REPLACE_WITH_REAL_KEY
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
CHAT_MODEL=deepseek-ai/DeepSeek-V4-Flash
RATE_LIMIT_ENABLED=true
EOF
chmod 600 "$APP_DIR/.env.prod"
chown ec2-user:ec2-user "$APP_DIR/.env.prod"

# 提示：用 SSM 拉真值的命令模板（注释保留，以后改用）
# aws ssm get-parameter --name "/smartdocs/prod/embedding_key" --with-decryption \
#     --query 'Parameter.Value' --output text

# ===== 5. 配置生产环境变量 =====
# compose 读 .env.prod + 环境变量覆盖
cat > /etc/profile.d/smartdocs.sh <<EOF
export ECR_REGISTRY="$ECR_REGISTRY"
export ECR_REPO="smartdocs-ai"
export AWS_REGION="$AWS_REGION"
EOF
chmod +x /etc/profile.d/smartdocs.sh

# ===== 6. 执行 Alembic 迁移 + 首次启动 =====
# 生产 RDS endpoint 通过 .env.prod 的 DATABASE_URL 覆盖
# ElastiCache endpoint 通过 .env.prod 的 REDIS_URL/ARQ_REDIS_URL 覆盖
cd "$APP_DIR"
source /etc/profile.d/smartdocs.sh

# 拉镜像
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# 跑迁移（用一次性 api 容器）
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api \
    alembic upgrade head

# 启动服务
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "==> EC2 启动完成"
echo "    健康检查：curl http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)/health"
