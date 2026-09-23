"""本地磁盘文件存储。

职责单一：原始上传文件的保存 / 读取 / 删除。
以后换 S3 时保持这三个函数签名不变、只替换实现即可，API 与 worker 都不感知。
注意：这是同步阻塞 IO，调用方（async 上下文）需用 run_in_threadpool 包裹。
"""

from pathlib import Path

from app.core.config import settings


def _path_for(doc_file_id: int) -> Path:
    # 以 DocumentFile 主键命名，路径可由 id 直接派生，无需再入库存路径
    return Path(settings.upload_dir) / f"{doc_file_id}.bin"


def save_file(doc_file_id: int, data: bytes) -> Path:
    path = _path_for(doc_file_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_file(doc_file_id: int) -> bytes:
    path = _path_for(doc_file_id)
    if not path.exists():
        raise FileNotFoundError(f"Uploaded file not found on disk: {path}")
    return path.read_bytes()


def file_exists(doc_file_id: int) -> bool:
    return _path_for(doc_file_id).exists()


def delete_file(doc_file_id: int) -> None:
    # missing_ok: 重复删/文件已不在都不报错
    _path_for(doc_file_id).unlink(missing_ok=True)
