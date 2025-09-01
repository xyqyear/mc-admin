import pytest

from app.minecraft.docker.compose_file import (
    ComposeFile,
    Ports,
    Volumes,
    convert_str_port_to_obj,
    convert_str_volume_to_obj,
)


def test_convert_str_port_to_obj():
    # Test cases for convert_str_port_to_obj
    assert convert_str_port_to_obj("3000") == Ports(target="3000")
    assert convert_str_port_to_obj("3000-3005") == Ports(target="3000-3005")
    assert convert_str_port_to_obj("8000:8000") == Ports(
        published="8000", target="8000"
    )
    assert convert_str_port_to_obj("9090-9091:8080-8081") == Ports(
        published="9090-9091", target="8080-8081"
    )
    assert convert_str_port_to_obj("49100:22") == Ports(published="49100", target="22")
    assert convert_str_port_to_obj("8000-9000:80") == Ports(
        published="8000-9000", target="80"
    )
    assert convert_str_port_to_obj("127.0.0.1:8001:8001") == Ports(
        host_ip="127.0.0.1", published="8001", target="8001"
    )
    assert convert_str_port_to_obj("127.0.0.1:5000-5010:5000-5010") == Ports(
        host_ip="127.0.0.1", published="5000-5010", target="5000-5010"
    )
    assert convert_str_port_to_obj("6060:6060/udp") == Ports(
        published="6060", target="6060", protocol="udp"
    )


def test_convert_str_port_to_obj_errors():
    """测试端口转换的错误情况"""
    # 测试浮点数输入
    result = convert_str_port_to_obj(3000.5)
    assert result == Ports(target="3000")  # 应该转换为整数再转字符串

    # 测试无效格式
    with pytest.raises(ValueError, match="Invalid port format"):
        convert_str_port_to_obj("invalid-port-format")


def test_convert_str_volume_to_obj_errors():
    """测试卷转换的错误情况"""
    # 测试无效格式
    with pytest.raises(ValueError, match="Invalid volume format"):
        convert_str_volume_to_obj("invalid-volume-format")


def test_convert_str_volume_to_obj():
    # Test cases for convert_str_volume_to_obj
    assert convert_str_volume_to_obj("/home:/home:ro") == Volumes(
        type="bind", source="/home", target="/home", read_only=True
    )
    assert convert_str_volume_to_obj(
        "/var/run/postgres/postgres.sock:/var/run/postgres/postgres.sock"
    ) == Volumes(
        type="bind",
        source="/var/run/postgres/postgres.sock",
        target="/var/run/postgres/postgres.sock",
    )
    assert convert_str_volume_to_obj("/data:/data") == Volumes(
        type="bind", source="/data", target="/data"
    )


def test_expand_services():
    # Test case for expand_services method in ComposeFile class
    compose_dict = {
        "services": {
            "web": {
                "ports": ["3000", "127.0.0.1:8001:8001", "6060:6060/udp"],
                "volumes": ["/home:/home:ro", "/data:/data"],
                "environment": ["KEY1=value1", "KEY2=value2"],
            }
        }
    }

    compose_file = ComposeFile.from_dict(compose_dict)

    assert compose_file.services["web"].ports == [  # type: ignore
        Ports(target="3000"),
        Ports(host_ip="127.0.0.1", published="8001", target="8001"),
        Ports(published="6060", target="6060", protocol="udp"),
    ]

    assert compose_file.services["web"].volumes == [  # type: ignore
        Volumes(type="bind", source="/home", target="/home", read_only=True),
        Volumes(type="bind", source="/data", target="/data"),
    ]

    assert compose_file.services["web"].environment == {  # type: ignore
        "KEY1": "value1",
        "KEY2": "value2",
    }


def test_expand_services_with_dicts():
    # Test case for expand_services method when ports, environment, and volumes are already dicts
    compose_dict = {  # type: ignore
        "services": {
            "web": {
                "ports": [
                    Ports(target="3000"),
                    Ports(host_ip="127.0.0.1", published="8001", target="8001"),
                    Ports(published="6060", target="6060", protocol="udp"),
                ],
                "volumes": [
                    Volumes(
                        type="bind", source="/home", target="/home", read_only=True
                    ),
                    Volumes(type="bind", source="/data", target="/data"),
                ],
                "environment": {"KEY1": "value1", "KEY2": "value2"},
            }
        }
    }

    compose_file = ComposeFile.from_dict(compose_dict)  # type:ignore

    assert compose_file.services["web"].ports == [  # type:ignore
        Ports(target="3000"),
        Ports(host_ip="127.0.0.1", published="8001", target="8001"),
        Ports(published="6060", target="6060", protocol="udp"),
    ]

    assert compose_file.services["web"].volumes == [  # type:ignore
        Volumes(type="bind", source="/home", target="/home", read_only=True),
        Volumes(type="bind", source="/data", target="/data"),
    ]

    assert compose_file.services["web"].environment == {  # type:ignore
        "KEY1": "value1",
        "KEY2": "value2",
    }


def test_compose_file_file_operations():
    """测试ComposeFile的文件操作方法"""
    import os
    import tempfile
    from typing import Any

    # 创建测试数据
    test_data: dict[str, Any] = {
        "version": "3.8",
        "services": {"web": {"image": "nginx", "ports": ["80:80"]}},
    }

    # 测试to_dict方法
    compose_file = ComposeFile.from_dict(test_data)
    result_dict = compose_file.to_dict()
    assert "version" in result_dict
    assert "services" in result_dict

    # 测试文件写入和读取
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp_file:
        temp_path = tmp_file.name

    try:
        # 测试to_file方法
        compose_file.to_file(temp_path)

        # 测试from_file方法
        loaded_compose = ComposeFile.from_file(temp_path)
        assert loaded_compose.version == "3.8"
        assert loaded_compose.services is not None
        assert "web" in loaded_compose.services

    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.unlink(temp_path)


async def test_compose_file_async_file_operations():
    """测试ComposeFile的异步文件操作方法"""
    import os
    import tempfile
    from typing import Any

    # 创建测试数据
    test_data: dict[str, Any] = {
        "version": "3.8",
        "services": {"web": {"image": "nginx", "ports": ["80:80"]}},
    }

    compose_file = ComposeFile.from_dict(test_data)

    # 测试异步文件写入和读取
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp_file:
        temp_path = tmp_file.name

    try:
        # 测试async_to_file方法
        await compose_file.async_to_file(temp_path)

        # 测试async_from_file方法
        loaded_compose = await ComposeFile.async_from_file(temp_path)
        assert loaded_compose.version == "3.8"
        assert loaded_compose.services is not None
        assert "web" in loaded_compose.services

    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main()
