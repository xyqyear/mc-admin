"""
操作日志中间件

基于FastAPI中间件的非侵入式操作日志系统，能够自动记录所有会更改服务器状态或数据的HTTP请求。
使用中间件可以在不修改业务代码的情况下记录请求和响应信息。
"""

import json
import logging
import logging.handlers
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .config import settings
from .dependencies import get_current_user


class OperationAuditMiddleware(BaseHTTPMiddleware):
    """操作审计中间件"""

    # 需要记录日志的HTTP方法
    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    # 需要记录日志的路径模式（不区分HTTP方法）
    AUDIT_PATH_PATTERNS = {
        "/api/admin/",  # 管理员操作
        "/api/auth/register",  # 用户注册
    }

    # 服务器相关操作的特定路径（需要与HTTP方法结合判断）
    SERVER_OPERATION_PATTERNS = {"/operations", "/compose", "/rcon"}

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._setup_logger()

    def _setup_logger(self):
        """设置操作日志记录器"""
        if not settings.audit.enabled:
            self.logger = None
            return

        logs_dir = Path(settings.logs_dir)
        logs_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger("operation_audit")
        self.logger.setLevel(logging.INFO)

        # 避免重复添加handler
        if not self.logger.handlers:
            log_file = logs_dir / settings.audit.log_file
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file, when="midnight", encoding="utf-8"
            )
            file_handler.setLevel(logging.INFO)

            # 使用结构化的日志格式
            formatter = logging.Formatter("%(message)s")
            file_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)

            # 不传播到根logger，避免重复记录
            self.logger.propagate = False

    def _should_audit_request(self, request: Request) -> bool:
        """判断是否应该审计此请求"""
        if not settings.audit.enabled or not self.logger:
            return False

        method = request.method.upper()
        path = request.url.path

        # 检查特定路径模式（不区分方法）
        for pattern in self.AUDIT_PATH_PATTERNS:
            if pattern in path:
                return True

        # 检查服务器相关的操作（需要结合HTTP方法）
        if "/api/servers/" in path and method in self.AUDIT_METHODS:
            # 检查是否是服务器操作路径
            for operation_pattern in self.SERVER_OPERATION_PATTERNS:
                if operation_pattern in path:
                    return True

        return False

    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """掩码敏感数据"""
        if not isinstance(data, dict):
            return data

        masked_data = {}
        for key, value in data.items():
            if key.lower() in [
                field.lower() for field in settings.audit.sensitive_fields
            ]:
                masked_data[key] = "***MASKED***"
            elif isinstance(value, dict):
                masked_data[key] = self._mask_sensitive_data(value)
            else:
                masked_data[key] = value
        return masked_data

    async def _get_user_info(self, request: Request) -> Optional[Dict[str, Any]]:
        """获取当前用户信息"""
        try:
            # 尝试从请求中获取Authorization头
            auth_header = request.headers.get("authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None

            # 提取token
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                return None

            user = get_current_user(token)

            return {
                "user_id": user.id,
                "username": user.username,
                "role": user.role.value,
            }

        except Exception:
            # 如果获取用户信息失败（包括认证失败），返回None，让日志记录继续
            return None

    async def _read_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        """读取请求体"""
        if not settings.audit.log_request_body:
            return None

        try:
            body_bytes = await request.body()

            if not body_bytes:
                return None

            if len(body_bytes) > settings.audit.max_body_size:
                return {"error": "Request body too large for logging"}

            try:
                body_json = json.loads(body_bytes.decode("utf-8"))
                return self._mask_sensitive_data(body_json)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # 如果不是JSON，记录为字符串形式
                return {"raw_body": body_bytes.decode("utf-8", errors="replace")}

        except Exception as e:
            return {"error": f"Failed to read request body: {str(e)}"}

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """获取客户端IP地址"""
        # 检查常见的代理头
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 如果没有代理头，使用客户端地址
        if hasattr(request, "client") and request.client:
            return request.client.host

        return None

    def _create_log_entry(
        self,
        request: Request,
        response: Response,
        user_info: Optional[Dict[str, Any]],
        request_body: Optional[Dict[str, Any]],
        processing_time: float,
    ) -> str:
        """创建日志条目"""

        # 获取路径参数和查询参数
        path_params = (
            dict(request.path_params) if hasattr(request, "path_params") else {}
        )
        query_params = dict(request.query_params) if request.query_params else {}

        # 构建日志数据
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "processing_time_ms": round(processing_time * 1000, 2),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
        }

        # 添加用户信息
        if user_info:
            log_data.update(user_info)
        else:
            log_data.update(
                {"user_id": None, "username": "anonymous", "role": "anonymous"}
            )

        # 添加参数信息
        if path_params:
            log_data["path_params"] = self._mask_sensitive_data(path_params)
        if query_params:
            log_data["query_params"] = self._mask_sensitive_data(query_params)
        if request_body:
            log_data["request_body"] = request_body

        # 操作是否成功
        log_data["success"] = 200 <= response.status_code < 400

        # 转换为JSON字符串
        return json.dumps(log_data, ensure_ascii=False)

    async def dispatch(self, request: Request, call_next):
        """中间件主要逻辑"""
        # 检查是否需要审计此请求
        should_audit = self._should_audit_request(request)

        if not should_audit:
            # 不需要审计，直接传递请求
            return await call_next(request)

        # 记录处理开始时间
        start_time = time.perf_counter()

        # 获取用户信息（在请求处理前）
        user_info = await self._get_user_info(request)

        # 读取请求体（注意：这会消费请求体，需要重新设置）
        request_body = await self._read_request_body(request)

        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 如果处理过程中发生异常，也要记录日志
            processing_time = time.perf_counter() - start_time

            error_response = JSONResponse(
                status_code=500, content={"detail": "Internal Server Error"}
            )

            log_entry = self._create_log_entry(
                request, error_response, user_info, request_body, processing_time
            )

            if self.logger:
                self.logger.info(log_entry)

            # 重新抛出异常
            raise e

        # 计算处理时间
        processing_time = time.perf_counter() - start_time

        # 创建并记录日志条目
        log_entry = self._create_log_entry(
            request, response, user_info, request_body, processing_time
        )

        if self.logger:
            self.logger.info(log_entry)

        return response
