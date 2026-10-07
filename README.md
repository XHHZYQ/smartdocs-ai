# docker 健康检查
curl http://localhost/health     # {"status":"ok"}            ← nginx :80
curl http://localhost/readiness  # db/redis 都 ok

# docker 操作
make up / make logs / make ps / make down  # 日常操作