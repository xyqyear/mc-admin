#!/usr/bin/env python3
"""
测试操作审计中间件的简单脚本
"""
import asyncio
import json
from pathlib import Path

# 添加项目路径
import sys
sys.path.append(str(Path(__file__).parent))

from app.config import settings


async def test_audit_configuration():
    """测试审计配置"""
    print("Testing audit configuration...")
    print(f"Audit enabled: {settings.audit.enabled}")
    print(f"Log file: {settings.audit.log_file}")
    print(f"Max body size: {settings.audit.max_body_size}")
    print(f"Sensitive fields: {settings.audit.sensitive_fields}")
    
    
def test_log_file_creation():
    """测试日志文件创建"""
    print("\nTesting log file creation...")
    
    from app.audit import OperationAuditMiddleware
    from fastapi import FastAPI
    
    app = FastAPI()
    middleware = OperationAuditMiddleware(app)
    
    if middleware.logger:
        print("✅ Audit logger created successfully")
        
        # 检查日志文件是否存在
        log_file = Path(settings.logs_dir) / settings.audit.log_file
        print(f"Log file path: {log_file}")
        
        if log_file.exists():
            print("✅ Log file exists")
        else:
            print("ℹ️ Log file will be created on first write")
    else:
        print("❌ Audit logger not created (audit might be disabled)")


def test_sensitive_data_masking():
    """测试敏感数据掩码"""
    print("\nTesting sensitive data masking...")
    
    from app.audit import OperationAuditMiddleware
    from fastapi import FastAPI
    
    app = FastAPI()
    middleware = OperationAuditMiddleware(app)
    
    # 测试数据
    test_data = {
        "username": "testuser",
        "password": "secret123",
        "token": "jwt_token_here",
        "config": {
            "secret": "nested_secret",
            "public": "public_value"
        },
        "normal_field": "normal_value"
    }
    
    masked_data = middleware._mask_sensitive_data(test_data)
    
    print("Original data:")
    print(json.dumps(test_data, indent=2))
    print("\nMasked data:")
    print(json.dumps(masked_data, indent=2))
    
    # 验证掩码是否正确
    assert masked_data["password"] == "***MASKED***"
    assert masked_data["token"] == "***MASKED***"
    assert masked_data["config"]["secret"] == "***MASKED***"
    assert masked_data["username"] == "testuser"
    assert masked_data["config"]["public"] == "public_value"
    
    print("✅ Sensitive data masking works correctly")


def test_audit_patterns():
    """测试审计模式匹配"""
    print("\nTesting audit patterns...")
    
    from app.audit import OperationAuditMiddleware
    from fastapi import FastAPI, Request
    from unittest.mock import MagicMock
    
    app = FastAPI()
    middleware = OperationAuditMiddleware(app)
    
    test_cases = [
        # (method, path, should_audit)
        ("POST", "/api/servers/test/operations", True),
        ("PUT", "/api/servers/test/compose", True),
        ("POST", "/api/servers/test/rcon", True),
        ("DELETE", "/api/admin/users/123", True),
        ("POST", "/api/auth/register", True),
        ("GET", "/api/servers/", False),
        ("GET", "/api/servers/test/status", False),  # GET方法不审计
        ("GET", "/api/system/info", False),
        ("POST", "/api/auth/token", False),  # 登录不需要审计
        ("PUT", "/api/servers/test/notoperation", False),  # 不匹配操作模式
    ]
    
    for method, path, expected in test_cases:
        # 创建模拟请求
        request = MagicMock(spec=Request)
        request.method = method
        request.url.path = path
        
        result = middleware._should_audit_request(request)
        status = "✅" if result == expected else "❌"
        print(f"{status} {method} {path} -> {result} (expected: {expected})")


def test_user_auth_integration():
    """测试用户认证集成"""
    print("\nTesting user authentication integration...")
    
    from fastapi import Request, FastAPI
    from app.audit import OperationAuditMiddleware
    from unittest.mock import MagicMock
    
    app = FastAPI()
    middleware = OperationAuditMiddleware(app)
    
    # 创建模拟请求 - 无Authorization头
    request_no_auth = MagicMock(spec=Request)
    request_no_auth.headers.get.return_value = None
    
    # 测试无认证情况
    result = asyncio.run(middleware._get_user_info(request_no_auth))
    print(f"No auth header: {result}")
    assert result is None
    
    # 创建模拟请求 - 无效token格式
    request_invalid = MagicMock(spec=Request)
    request_invalid.headers.get.return_value = "InvalidToken"
    
    result = asyncio.run(middleware._get_user_info(request_invalid))
    print(f"Invalid token format: {result}")
    assert result is None
    
    # 创建模拟请求 - Bearer token格式但token无效
    request_bearer = MagicMock(spec=Request)
    request_bearer.headers.get.return_value = "Bearer invalid_token"
    
    result = asyncio.run(middleware._get_user_info(request_bearer))
    print(f"Invalid bearer token: {result}")
    assert result is None
    
    print("✅ User authentication integration works correctly")


if __name__ == "__main__":
    print("=== Operation Audit Middleware Test ===")
    
    asyncio.run(test_audit_configuration())
    test_log_file_creation()
    test_sensitive_data_masking()
    test_audit_patterns()
    test_user_auth_integration()
    
    print("\n=== Test completed ===")