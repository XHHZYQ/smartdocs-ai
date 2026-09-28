"""根 conftest:在任何 app 模块被 import 之前，把 .env.test 的变量注入 os.environ。

pydantic-settings 优先级: env vars > .env file > defaults
所以这里设置的环境变量会覆盖 .env 里的同名值，确保测试用独立的数据库/配置。
"""
import os
from pathlib import Path

_env_test = Path(__file__).parent / ".env.test"
if _env_test.exists():
    for _line in _env_test.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        _key, _, _val = _line.partition("=")
        os.environ[_key.strip()] = _val.strip()
