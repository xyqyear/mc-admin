"""Audit middleware that logs all state-changing HTTP requests."""

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
    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._setup_logger()

    def _setup_logger(self):
        if not settings.audit.enabled:
            self.logger = None
            return

        logs_dir = Path(settings.logs_dir)
        logs_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger("operation_audit")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            log_file = logs_dir / settings.audit.log_file
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file, when="midnight", encoding="utf-8"
            )
            file_handler.setLevel(logging.INFO)

            formatter = logging.Formatter("%(message)s")
            file_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)

            self.logger.propagate = False

    def _should_audit_request(self, request: Request) -> bool:
        if not settings.audit.enabled or not self.logger:
            return False

        method = request.method.upper()

        return method in self.AUDIT_METHODS

    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
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
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]

        try:
            user = get_current_user(token)
        except Exception:
            return None

        return {
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value,
        }

    async def _read_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        if not settings.audit.log_request_body:
            return None

        body_bytes = await request.body()

        if not body_bytes:
            return None

        if len(body_bytes) > settings.audit.max_body_size:
            return {"error": "Request body too large for logging"}

        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
            return self._mask_sensitive_data(body_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw_body": body_bytes.decode("utf-8", errors="replace")}


    def _get_client_ip(self, request: Request) -> Optional[str]:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

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
        path_params = (
            dict(request.path_params) if hasattr(request, "path_params") else {}
        )
        query_params = dict(request.query_params) if request.query_params else {}

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "processing_time_ms": round(processing_time * 1000, 2),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("user-agent"),
        }

        if user_info:
            log_data.update(user_info)
        else:
            log_data.update(
                {"user_id": None, "username": "anonymous", "role": "anonymous"}
            )

        if path_params:
            log_data["path_params"] = self._mask_sensitive_data(path_params)
        if query_params:
            log_data["query_params"] = self._mask_sensitive_data(query_params)
        if request_body:
            log_data["request_body"] = request_body

        log_data["success"] = 200 <= response.status_code < 400

        return json.dumps(log_data, ensure_ascii=False)

    async def dispatch(self, request: Request, call_next):
        should_audit = self._should_audit_request(request)

        if not should_audit:
            return await call_next(request)

        start_time = time.perf_counter()

        user_info = await self._get_user_info(request)

        # Reading the body consumes the stream; downstream handlers re-read via Starlette's cached body.
        request_body = await self._read_request_body(request)

        try:
            response = await call_next(request)
        except Exception as e:
            processing_time = time.perf_counter() - start_time

            error_response = JSONResponse(
                status_code=500, content={"detail": "Internal Server Error"}
            )

            log_entry = self._create_log_entry(
                request, error_response, user_info, request_body, processing_time
            )

            if self.logger:
                self.logger.info(log_entry)

            raise e

        processing_time = time.perf_counter() - start_time

        log_entry = self._create_log_entry(
            request, response, user_info, request_body, processing_time
        )

        if self.logger:
            self.logger.info(log_entry)

        return response
