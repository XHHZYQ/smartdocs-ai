"""通过真实 HTTP 调用验证限流。验证后可删。"""
import time

import httpx

BASE = "http://127.0.0.1:8765"

print("=== /auth/register 限流测试 (limit=5/minute, IP 维度) ===")
prefix = f"rt{int(time.time())}"
with httpx.Client(base_url=BASE, timeout=10) as client:
    for i in range(1, 8):
        r = client.post(
            "/auth/register",
            json={"email": f"{prefix}_{i}@test.com", "password": "Pass1234!"},
        )
        print(f"  #{i}: status={r.status_code} body={r.text[:140]}")
        if r.status_code == 429:
            print(f"  -> Retry-After: {r.headers.get('Retry-After')}")
            print(f"  -> X-RateLimit-Remaining: {r.headers.get('X-RateLimit-Remaining')}")
            print(f"  -> X-RateLimit-Reset: {r.headers.get('X-RateLimit-Reset')}")
            break
