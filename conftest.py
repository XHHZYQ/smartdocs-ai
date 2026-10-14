"""根 conftest:在任何 app 模块被 import 之前，把 .env.test 的变量注入 os.environ。

pydantic-settings 优先级: env vars > env file > defaults
用 setdefault 注入:文件只当"兜底默认值"，真实环境变量(CI 注入)优先。
这样本地跑 pytest 用 .env.test，CI 里显式传的 DATABASE_URL 不会被文件盖掉。
"""

import os
from pathlib import Path

# 强制测试走 .env.test，避免误读到 .env.local 的开发库/密钥
os.environ.setdefault("APP_ENV", "test")

_env_test = Path(__file__).parent / ".env.test"
if _env_test.exists():
    for _line in _env_test.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        _key, _, _val = _line.partition("=")
        os.environ.setdefault(_key.strip(), _val.strip())
