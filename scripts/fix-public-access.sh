#!/usr/bin/env bash
# 修复 smartdocs-ai EC2 (i-09fc0d2a5ceddba5b) 公网访问问题
# 根因：安全组未开放 80 端口；worker 容器仍用旧 healthcheck 配置
#
# ===================== 执行位置：必须在你自己的电脑上 =====================
# 不能在 EC2 上执行，原因有两条（均已实测确认）：
#   1. 改安全组要调 AWS API，需要凭证。EC2 上执行 aws CLI 报
#      "Unable to locate credentials"，且实例没挂 IAM Instance Profile
#      （IMDS 的 iam/security-credentials/ 返回 404），拿不到任何凭证。
#   2. 脚本还要 SSH 进 EC2 重建容器，私钥 ~/.ssh/smartdocs-ai-key.pem
#      只存在于你的本机，EC2 上没有（EC2 的 ~/.ssh 里只有 authorized_keys）。
# 换句话说：aws CLI 那步在你本机跑，ssh 那步从你本机发出去，两步都在本机。
# =======================================================================
#
# 用法（在本机执行）：
#   brew install awscli                # 仅首次
#   export AWS_PROFILE=你的profile     # 或 export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
#   ./scripts/fix-public-access.sh check    # 只看现状，不做任何修改
#   ./scripts/fix-public-access.sh apply    # 开放 80 端口 + 重建容器
#
# 不处理 443：没有证书，HTTPS 无意义，因此既不开安全组也不动证书配置。

set -euo pipefail

REGION="${AWS_REGION:-ap-southeast-1}"
INSTANCE_ID="${INSTANCE_ID:-i-09fc0d2a5ceddba5b}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/smartdocs-ai-key.pem}"
SSH_USER="ubuntu"
MODE="${1:-check}"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
grn() { printf '\033[32m%s\033[0m\n' "$*"; }

# ---------- 前置检查：aws cli 与凭证 ----------
if ! command -v aws >/dev/null 2>&1; then
  red "✗ 本机未安装 aws cli。安装：brew install awscli"
  exit 1
fi
if ! aws sts get-caller-identity --region "$REGION" >/dev/null 2>&1; then
  red "✗ AWS 凭证无效。设置其一："
  echo "    export AWS_PROFILE=<你的profile>    # 需先 aws configure 创建"
  echo "    export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=..."
  exit 1
fi
if [ ! -f "$SSH_KEY" ]; then
  red "✗ 找不到 SSH 私钥：$SSH_KEY"
  echo "    可用 SSH_KEY=/path/to/key.pem 指定"
  exit 1
fi

# ---------- 查出这台机器挂的安全组 ----------
mapfile -t SGS < <(aws ec2 describe-instances --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[].Instances[].SecurityGroups[].GroupId' --output text | tr '\t' '\n')

if [ "${#SGS[@]}" -eq 0 ]; then
  red "✗ 未查到实例 $INSTANCE_ID 的安全组"
  exit 1
fi

echo "实例: $INSTANCE_ID    区域: $REGION"
echo "安全组: ${SGS[*]}"
echo

# ---------- 展示当前入站规则 ----------
echo "──────── 当前安全组入站规则 ────────"
aws ec2 describe-security-groups --region "$REGION" --group-ids "${SGS[@]}" \
  --query 'SecurityGroups[].{Name:GroupName,ID:GroupId,Rules:IpPermissions[].{Proto:IpProtocol,From:FromPort,To:ToPort,CIDR:IpRanges[].CidrIp}}' \
  --output table
echo

# 判断 80 是否已对全网放行
port80_open=$(aws ec2 describe-security-groups --region "$REGION" --group-ids "${SGS[@]}" \
  --query "SecurityGroups[].IpPermissions[?IpProtocol=='tcp' && FromPort==\`80\` && IpRanges[?CidrIp=='0.0.0.0/0']] | length(@)" \
  --output text | tr '\t' '\n' | grep -c '[1-9]' || true)

if [ "$MODE" = "check" ]; then
  echo "──────── 诊断结论 ────────"
  if [ "$port80_open" -gt 0 ]; then
    grn "✓ 80 端口已对 0.0.0.0/0 放行"
  else
    red "✗ 80 端口未放行  ← 这就是浏览器/curl 访问不了的原因"
  fi
  echo
  echo "执行 $0 apply 可自动修复"
  exit 0
fi

# ---------- apply：开放 80 ----------
if [ "$port80_open" -eq 0 ]; then
  echo "→ 正在对安全组开放 80/TCP (0.0.0.0/0) ..."
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "${SGS[0]}" \
    --ip-permissions IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges='[{CidrIp="0.0.0.0/0",Description="HTTP for SmartDocs web"}]' \
    && grn "✓ 80 端口已开放"
else
  grn "✓ 80 端口已开放，跳过"
fi

# ---------- 重建 worker / nginx 容器，让新 compose 配置生效 ----------
echo
echo "→ 重建 worker 与 nginx 容器，使 healthcheck.disable 生效 ..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$SSH_USER@$INSTANCE_ID" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/smartdocs
# --force-recreate 保证按新 compose 定义重建，否则旧 healthcheck 会残留
sudo docker compose -f docker-compose.prod.yml up -d --force-recreate worker nginx
echo "--- 重建后状态 ---"
sudo docker compose -f docker-compose.prod.yml ps
REMOTE

echo
grn "──────── 完成 ────────"
echo "验证公网访问（安全组规则生效有延迟，最多等 1 分钟）："
echo "  curl -v http://54.254.154.60/health"
echo "  浏览器打开 http://54.254.154.60/health"
echo
echo "预期返回： {\"status\":\"ok\"}"
