from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .errors import log_safe_error

type ValidationIssue = Mapping[str, Any]

_VALIDATION_MESSAGES = {
    "missing": "必填字段缺失",
    "int_parsing": "请输入整数", "int_type": "请输入整数",
    "float_parsing": "请输入数字", "float_type": "请输入数字",
    "string_type": "请输入字符串",
    "bool_parsing": "请输入布尔值", "bool_type": "请输入布尔值",
    "list_type": "请输入列表", "literal_error": "请选择有效选项",
    "extra_forbidden": "存在不支持的字段",
    "union_tag_invalid": "类型无效", "union_tag_not_found": "缺少类型",
    "greater_than": "数值过小", "greater_than_equal": "数值过小",
    "less_than": "数值过大", "less_than_equal": "数值过大",
}


class ValidationRoute(APIRoute):
    validation_prefix = "请求参数无效"
    validation_log_context: str | None = None

    def validation_location(self, error: ValidationIssue) -> str:
        location = error["loc"]
        if len(location) > 1 and location[0] == "body" and self.body_field is not None:
            fields = getattr(self.body_field.field_info.annotation, "model_fields", {})
        else:
            fields = {field.alias for field in self.dependant.query_params + self.dependant.path_params}
        # Only declared fields are safe to display; dynamic keys may contain credentials.
        return str(location[1]) if len(location) > 1 and location[1] in fields else "参数"

    def validation_message(self, error: ValidationIssue) -> str:
        return _VALIDATION_MESSAGES.get(error["type"], "字段值无效")

    def validation_detail(self, exc: RequestValidationError) -> str:
        diagnostics = [f"{self.validation_location(error)}: {self.validation_message(error)}" for error in exc.errors()]
        return self.validation_prefix + ": " + "; ".join(diagnostics)

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                if self.validation_log_context is not None:
                    log_safe_error(exc, self.validation_log_context)
                raise HTTPException(status_code=422, detail=self.validation_detail(exc)) from None

        return handler


async def default_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        message = error["msg"]
        messages.append(f"{location}: {message}" if location else message)
    detail = "; ".join(messages) if messages else "请求参数验证失败"
    return JSONResponse(status_code=422, content={"detail": detail})
