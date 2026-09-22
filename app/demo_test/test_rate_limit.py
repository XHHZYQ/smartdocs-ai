"""临时验证脚本:验证限流是否生效。验证后可删。"""
import traceback

from fastapi.testclient import TestClient

from app.main import app

# raise_server_exceptions=True(默认):让服务端异常原样抛出,定位问题
client = TestClient(app)

print("=== /auth/register 限流测试 (limit=5/minute, IP 维度) ===")
import time

prefix = f"rt{int(time.time())}"
for i in range(1, 8):
    try:
        r = client.post(
            "/auth/register",
            json={"email": f"{prefix}_{i}@test.com", "password": "Pass1234!"},
        )
        body = r.text if not r.text else r.text[:140]
        print(f"  #{i}: status={r.status_code} body={body}")
        if r.status_code == 429:
            print(f"  -> Retry-After: {r.headers.get('Retry-After')}")
            break
    except Exception as e:
        print(f"  #{i}: RAISED {type(e).__name__}: {e}")
        traceback.print_exc()
        break
