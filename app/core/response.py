import json
from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute


class EnvelopeRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            response = await original_handler(request)
            if response.headers.get("content-type", "").startswith("application/json"):
                data = json.loads(response.body) # 解析 JSON 字符串为 Python 对象
                body = json.dumps( # 将 Python 对象转换为 JSON 字符串
                    {"code": 0, "data": data, "msg": "ok"}
                ).encode("utf-8")
                response.body = body
                response.headers["content-length"] = str(len(body))
            return response

        return custom_handler