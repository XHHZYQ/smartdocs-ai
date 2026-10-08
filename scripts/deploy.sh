#!/usr/bin/env bash
# 在 EC2 上执行的部署脚本
#
# 由 GitHub Actions 通过 SSH 调用，也可以手动跑：
#   IMAGE_TAG=sha-abc1234 bash /opt/smartdocs/scripts/deploy.sh
#
# 流程：记录旧 tag → pull → alembic 迁移 → 先起 worker 再起 api → 健康检查
# 健康检查失败会自动回滚到上一个 tag。

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/smartdocs}"
IMAGE_TAG="${IMAGE_TAG:?必须指定 IMAGE_TAG，例如 IMAGE_TAG=sha-abc1234}"
HEALTH_URL="${HEALTH_URL:-http://localhost/health}"
MAX_WAIT="${MAX_WAIT:-60}"

cd "$APP_DIR"

# 用函数包一层，避免把带空格的命令塞进变量后被当成命令名
compose() {
    IMAGE_TAG="$IMAGE_TAG" IMAGE_NAME="${IMAGE_NAME:-ghcr.io/xhhzyq/smartdocs-ai}" \
        docker compose -f docker-compose.prod.yml "$@"
}

rollback() {
    if [ -z "${PREV_TAG:-}" ]; then
        echo "!! 没有可回滚的版本，保持现状"
        return 0
    fi
    echo "!! 回滚到 $PREV_TAG"
    IMAGE_TAG="$PREV_TAG" compose up -d --no-deps api worker
    echo "   回滚完成。排查命令：docker compose -f docker-compose.prod.yml logs --tail=100 api"
}

# 上一个成功部署的 tag，用于回滚
TAG_FILE="$APP_DIR/.current_tag"
PREV_TAG="$(cat "$TAG_FILE" 2>/dev/null || true)"

echo "==> 目标镜像 tag: $IMAGE_TAG"
echo "==> 上一个 tag:   ${PREV_TAG:-（无，首次部署）}"

echo "==> [1/5] 拉取镜像"
compose pull api worker migrate

echo "==> [2/5] 数据库迁移"
# 必须在 api 启动前做完，否则新代码会撞上旧表结构
compose run --rm migrate

echo "==> [3/5] 启动 worker"
# 先换 worker：它不接外部流量，重启期间不影响线上请求
compose up -d --no-deps worker

echo "==> [4/5] 启动 api + nginx"
compose up -d --no-deps api
compose up -d --no-deps nginx

echo "==> [5/5] 健康检查（最多 ${MAX_WAIT}s）"
for i in $(seq 1 $((MAX_WAIT / 5))); do
    sleep 5
    if curl -fsS "$HEALTH_URL" > /dev/null 2>&1; then
        echo "$IMAGE_TAG" > "$TAG_FILE"
        echo "==> 部署成功（${i}x5s），当前 tag: $IMAGE_TAG"
        exit 0
    fi
    echo "   等待就绪... (${i}/$((MAX_WAIT / 5)))"
done

echo "!! 健康检查超时"
rollback

echo "==> 当前容器状态"
compose ps
exit 1
