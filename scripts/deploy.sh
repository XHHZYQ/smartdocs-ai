#!/usr/bin/env bash
# SmartDocs EC2 部署脚本
# 在 EC2 上由 CI 通过 SSH 触发：拉新镜像 → 滚动重启 → 健康检查
#
# 前置条件（user-data 已自动准备）：
# - Docker + docker compose plugin 已装
# - /opt/smartdocs 是项目目录，含 docker-compose.yml + .env.prod
# - EC2 实例角色有 ECR 拉镜像权限（ecr:GetDownloadUrlForLayer / ecr:BatchGetImage）
# - 已 docker login 过 ECR（user-data 里跑一次 aws ecr get-login-password | docker login）

: "${ECR_REGISTRY:?Set ECR_REGISTRY before running deploy.sh}"
: "${ECR_REPO:?Set ECR_REPO before running deploy.sh}"

set -euo pipefail

APP_DIR="/opt/smartdocs"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"
IMAGE_TAG="${IMAGE_TAG:-latest}"  # CI 可通过 IMAGE_TAG=sha-x deploy.sh 指定版本

cd "$APP_DIR"

echo "==> [1/4] 拉最新镜像 (tag=$IMAGE_TAG)"
# compose 文件用 build:，生产 override 成 image:，从 ECR 拉
# 这里假设 docker-compose.prod.yml override 了 image 字段
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull api worker

echo "==> [2/4] 备份当前状态（出错可回滚）"
# 记录当前镜像 sha，方便回滚
CURRENT_API_IMAGE=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml images -q api 2>/dev/null || echo "")
echo "    当前 api 镜像 sha: ${CURRENT_API_IMAGE:-（首次部署）}"

echo "==> [3/4] 滚动重启 api + worker"
# 滚动策略：先重启 worker（不影响 API 响应），再重启 api
# nginx depends_on api healthcheck，api 起来前 nginx 不会转发流量
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps worker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps api

echo "==> [4/4] 健康检查（最多等 60s）"
for i in $(seq 1 12); do
    sleep 5
    if curl -fsS http://localhost/health > /dev/null 2>&1; then
        echo "    健康检查通过 (${i}x5s)"
        echo "==> 部署成功"
        exit 0
    fi
    echo "    等待 API 就绪... (${i}/12)"
done

echo "==> 部署失败：API 健康检查超时"
echo "    查看日志：docker compose logs --tail=100 api"
exit 1
