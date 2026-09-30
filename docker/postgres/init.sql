-- pgvector 扩展：在数据库首次初始化时由 postgres 镜像自动执行
-- 必须在 public schema 创建，SQLModel 的 chunk 表才能引用 vector 类型
CREATE EXTENSION IF NOT EXISTS vector;
