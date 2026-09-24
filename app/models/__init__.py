"""所有 model 的统一注册入口。

SQLModel/SQLAlchemy 用共享的 metadata 注册表：只有被 import 过的 model 类
才会把它的表注册进去。任何有外键引用（foreign_key="xxx.id"）的 model，
都必须保证被引用表在 metadata 生成/查询前已经 import。

所以所有「不走 FastAPI lifespan 的独立入口」（arq worker、脚本、
migrations）都应该 `import app.models` 一次，确保全部表注册到位，
否则会报 NoReferencedTableError。
"""

from app.models.chunk import Chunk  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType  # noqa: F401
from app.models.message import Message, MessageRole  # noqa: F401
from app.models.tenant import Tenant, TenantMembership, TenantRole  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "Chunk",
    "Conversation",
    "Document",
    "DocumentFile",
    "ExtractionStatus",
    "SourceType",
    "Message",
    "MessageRole",
    "Tenant",
    "TenantMembership",
    "TenantRole",
    "User",
]
