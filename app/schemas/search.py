from sqlmodel import SQLModel


class SearchRequest(SQLModel):
    query: str
    top_k: int = 5


class SearchResult(SQLModel):
    chunk_id: int
    document_id: int
    document_title: str
    content: str
    distance: float  # 越小越相似（cosine distance）