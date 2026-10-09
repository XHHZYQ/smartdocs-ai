#!/bin/bash
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

APP_DIR="/opt/smartdocs"
REPO_URL="${REPO_URL:-https://github.com/XHHZYQ/smartdocs-ai.git}"
ECR_REGISTRY="${ECR_REGISTRY:-}"
AWS_REGION="${AWS_REGION:-ap-southeast-1}"

# 允许覆盖安全组的 CIDR。默认全网；生产环境建议收窄到办公网 IP。
SG_CIDR="${SG_CIDR:-0.0.0.0/0}"

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

# 7b) Open port 80 in the security group
#
# Why here and not in docker-compose: the security group lives in the AWS VPC
# control plane and must allow inbound 80 BEFORE the instance serves traffic.
# docker compose cannot do this at all -- it has no ability to call AWS APIs,
# and by the time compose runs the traffic is already being dropped.
#
# Requires an IAM instance profile with ec2:AuthorizeSecurityGroupIngress on
# this instance's security group. Without it we fall back to a clear manual
# notice rather than failing the whole bootstrap.
if SG_ID=$(aws ec2 describe-instances --region "$AWS_REGION" \
      --instance-id "$(curl -fsS -m 5 -X PUT http://169.254.169.254/latest/api/token \
        -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
        | { read -r t; curl -fsS -m 5 -H "X-aws-ec2-metadata-token: $t" \
            http://169.254.169.254/latest/meta-data/instance-id; } 2>/dev/null)" \
      --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text 2>/dev/null) \
   && [ -n "$SG_ID" ] && [ "$SG_ID" != "None" ]; then
  echo "==> Opening port 80 in security group $SG_ID (CIDR: $SG_CIDR)"
  if aws ec2 authorize-security-group-ingress --region "$AWS_REGION" --group-id "$SG_ID" \
      --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=$SG_CIDR,Description=\"HTTP for SmartDocs web\"}]" 2>/dev/null; then
    echo "==> Port 80 opened"
  else
    # Already-authorized returns a duplicate error; that is not a failure
    echo "==> Port 80 rule already exists or could not be added (check manually)"
  fi
else
  cat <<'NOTICE'

  ┌──────────────────────────────────────────────────────────────┐
  │ ACTION REQUIRED: port 80 is not open yet.                   │
  │ Public traffic will be dropped until you open it:           │
  │   EC2 console → Security Groups → inbound rule → TCP 80     │
  │   or: aws ec2 authorize-security-group-ingress ...          │
  └──────────────────────────────────────────────────────────────┘
NOTICE
fi

# 8) Initial startup
sudo -u ubuntu bash -lc "
  cd '$APP_DIR'
  docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
  docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head || true
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
"

echo "EC2 bootstrap complete"