# SmartDocs 部署说明

## 架构

```
本地开发                     GitHub                         EC2
─────────                   ────────                       ─────
docker compose up  ──push──▶ Actions
(docker-compose.yml)           │
                               ├─ test    pytest + pgvector/redis 服务容器
                               ├─ build   buildx → push ghcr.io/<repo>:sha-xxxxxxx
                               └─ deploy  scp 配置 → ssh 执行 deploy.sh
                                                              │
                                              pull → migrate → up -d → healthcheck
                                              （失败自动回滚上一个 tag）
```

三个要点：

- **镜像仓库是 GHCR**，不再有 ECR 登录那一套
- **两个 compose 文件完全独立**，不再用 `-f a -f b` 叠加 —— 这也是之前 `depends on undefined service "postgres"` 的根因
- **EC2 只在创建时执行一次 user-data**，之后你不需要 ssh 上去做任何事

---

## 首次配置（一次性，约 10 分钟）

### 1. 建 EC2 实例

Ubuntu 22.04，安全组开 **22**（仅你的 IP）和 **80**（0.0.0.0/0）。
创建时展开 *Advanced details*，把 `scripts/ec2-user-data.sh` 的内容粘进 **User data** 框。

实例起来后**不需要 ssh 上去做任何操作**。想确认初始化结果可以看：

```bash
ssh ubuntu@<EC2_IP> 'cat /var/log/smartdocs-bootstrap.log'
```

### 2. 把 GHCR 镜像设为公开（推荐）

`https://github.com/XHHZYQ/smartdocs-ai/pkgs/container/smartdocs-ai`
→ *Package settings* → *Danger Zone* → **Change visibility → Public**

设为公开后 EC2 无需任何凭证即可拉镜像。保持私有也可以，多配一个 `GHCR_PAT` secret 就行。

### 3. 配置 GitHub Secrets

仓库 *Settings → Secrets and variables → Actions → New repository secret*：

| Secret | 说明 |
|---|---|
| `EC2_HOST` | EC2 公网 IP 或域名，如 `54.123.45.67` |
| `EC2_USER` | Ubuntu 镜像填 `ubuntu` |
| `EC2_SSH_KEY` | SSH **私钥全文**（含 `-----BEGIN ... END-----` 行） |
| `ENV_PROD` | 生产 `.env` 的完整内容，见下 |
| `GHCR_PAT` | 可选。镜像为私有时才需要，`read:packages` 权限的 PAT |

`ENV_PROD` 示例：

```bash
POSTGRES_USER=smartdocs
POSTGRES_PASSWORD=换成强密码
POSTGRES_DB=smartdocsdb

JWT_SECRET_KEY=openssl rand -hex 32 生成的值
EMBEDDING_API_KEY=你的真实 key
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
CHAT_MODEL=deepseek-ai/DeepSeek-V4-Flash

DEBUG=false
RATE_LIMIT_ENABLED=true
UPLOAD_DIR=/app/data/uploads
```

> `DATABASE_URL` / `REDIS_URL` / `ARQ_REDIS_URL` **不要写进 .env**。
> compose 会用 `POSTGRES_*` 自动拼出正确的容器内地址，写死反而容易和数据库容器的真实密码不一致。

---

## 日常使用

```bash
git push origin main     # 然后就没有然后了
```

去 Actions 页面看流水线即可。想手动触发：*Actions → CI/CD → Run workflow*。

---

## 文件清单

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 多阶段构建，uv 装依赖，一个镜像跑 API 和 Worker |
| `docker-compose.yml` | 本地开发栈，全部本地构建 |
| `docker-compose.prod.yml` | 生产栈，从 GHCR 拉镜像，含一次性 `migrate` 服务 |
| `.env.example` | 环境变量模板 |
| `.dockerignore` | 避免把 tests / .venv / .env 打进镜像 |
| `.github/workflows/ci-cd.yml` | 全流程：test → build → deploy |
| `scripts/deploy.sh` | 在 EC2 上跑的部署脚本，带自动回滚 |
| `scripts/ec2-user-data.sh` | EC2 一次性初始化 |
| `docker/nginx/nginx.conf` | 反代配置，SSE 已关缓冲 |
| `docker/postgres/init.sql` | 首次建库时启用 pgvector |

---

## 从旧配置迁移

以下东西可以删掉了：

- `docker-compose.prod.yml` 里的 `!reset` / `profiles` 写法（旧版）
- 所有 `aws ecr get-login-password` 相关脚本和 IAM 授权
- CI 里的 ruff / lint 步骤
- 部署文档里"先 ssh 上机器手动改 .env"的步骤

机器上如果之前起过旧容器，清一次：

```bash
ssh ubuntu@<EC2_IP>
cd /opt/smartdocs 2>/dev/null && docker compose down -v
```

---

## 常见问题

**部署失败想看日志**

```bash
ssh ubuntu@<EC2_IP> -t 'cd /opt/smartdocs && docker compose -f docker-compose.prod.yml logs --tail=100 api'
```

**手动回滚**

```bash
ssh ubuntu@<EC2_IP> -t 'cd /opt/smartdocs && cat .current_tag'
# 拿到上一个 tag 后：
ssh ubuntu@<EC2_IP> -t 'cd /opt/smartdocs && IMAGE_TAG=sha-xxxxxxx bash scripts/deploy.sh'
```

**健康检查一直不过**

大概率是 api 容器根本没起来，先看 `docker compose ps` 和 `logs api`。
常见原因：`.env` 缺 `JWT_SECRET_KEY` 导致启动时校验失败；或者数据库迁移失败（`migrate` 服务的退出码非 0）。

**想加 HTTPS**

在 EC2 上跑个 certbot 拿证书，然后给 nginx 挂 443 server 块，compose 里加 `"443:443"` 端口映射。
这一步建议等 HTTP 版本跑稳了再动。

**t2.micro 跑不动**

1G 内存同时跑 postgres + redis + api + worker + nginx 确实紧。user-data 已经自动加了 1G swap，
还不行就升到 t3.small（2G）。
