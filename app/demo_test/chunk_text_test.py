from app.services.chunking import chunk_text

with open("/Users/xuhonghui/Downloads/docker compose 插值语法.md", encoding="utf-8") as f:
    text = f.read()

chunks = chunk_text(text)
for i, c in enumerate(chunks):
    print(f"--- chunk {i} (长度 {len(c)}) ---")
    print(c)
    print()