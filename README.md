类比Fastify
  1、sqlmodel 同时替代了 Drizzle 的 schema 定义能力 + Zod 校验能力（因为它底层是 Pydantic）。
  2、app/core/config.py — 读环境变量，对应 process.env.DATABASE_URL