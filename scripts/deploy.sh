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

# 部署成功后额外做一次公网可达性体检。
# 为什么必须单独查：HEALTH_URL 打的是 localhost（内网），公网断掉时它照样返回 200，
# 会出现"部署成功但用户访问不了"。EC2 无法 curl 自己的公网 IP（AWS 不支持
# hairpin NAT），所以只能借第三方探测节点从外部验证。
verify_public_reachable() {
    local host="54.254.154.60"
    echo
    echo "==> 公网可达性检查（经第三方节点从外部探测 $host:80）"

    if ! command -v curl >/dev/null 2>&1; then
        echo "   跳过：本机无 curl"
        return 0
    fi

    local req resp
    req=$(curl -s -m 20 -H "Accept: application/json" \
        "https://check-host.net/check-http?host=http%3A%2F%2F${host}%2Fhealth&max_nodes=2" || true)
    local id
    id=$(printf '%s' "$req" | sed -n 's/.*"request_id":"\([^"]*\)".*/\1/p')
    if [ -z "$id" ]; then
        echo "   跳过：探测服务无响应（不影响部署结果）"
        return 0
    fi

    sleep 10
    resp=$(curl -s -m 20 -H "Accept: application/json" \
        "https://check-host.net/check-result/${id}" || true)

    if printf '%s' "$resp" | grep -q 'timed out\|Connection refused\|error'; then
        echo "   !! 公网 $host:80 不可达！"
        echo "      容器内已就绪，但外部访问不通。最常见原因：安全组未开放 80 端口。"
        echo "      修复：EC2 控制台 → 安全组 → 入站规则 → TCP 80 → 来源 0.0.0.0/0"
        echo "      注意：本机无法自测公网（AWS 不支持 hairpin NAT），"
        echo "            修完请从外部浏览器访问 http://${host}/health 确认。"
        return 1
    fi

    echo "   ✓ 公网可达"
    return 0
}

echo "==> 目标镜像 tag: $IMAGE_TAG"
echo "==> 上一个 tag:   ${PREV_TAG:-（无，首次部署）}"

echo "==> [1/6] 拉取镜像"
compose pull api worker migrate

echo "==> [2/6] 数据库迁移"
# 必须在 api 启动前做完，否则新代码会撞上旧表结构
compose run --rm migrate

echo "==> [3/6] 启动 worker"
# 先换 worker：它不接外部流量，重启期间不影响线上请求
compose up -d --no-deps worker

echo "==> [4/6] 启动 api + nginx"
compose up -d --no-deps api
compose up -d --no-deps nginx

echo "==> [5/6] 健康检查（最多 ${MAX_WAIT}s）"
for i in $(seq 1 $((MAX_WAIT / 5))); do
    sleep 5
    if curl -fsS "$HEALTH_URL" > /dev/null 2>&1; then
        echo "$IMAGE_TAG" > "$TAG_FILE"
        echo "==> 部署成功（${i}x5s），当前 tag: $IMAGE_TAG"
        verify_public_reachable
        exit 0
    fi
    echo "   等待就绪... (${i}/$((MAX_WAIT / 5)))"
done

echo "!! 健康检查超时"
rollback

echo "==> 当前容器状态"
compose ps
exit 1
