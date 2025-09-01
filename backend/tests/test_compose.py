# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
from typing import Any

import pytest

from app.minecraft.compose import MCComposeFile
from app.minecraft.docker.compose_file import ComposeFile


def test_mc_compose_file_basic():
    """测试MCComposeFile的基本功能"""
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {
                    "EULA": "true",
                    "VERSION": "1.20.4",
                    "ENABLE_RCON": "true",
                },
                "ports": ["25565:25565", "25575:25575"],
                "volumes": ["./data:/data"],
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    mc_compose = MCComposeFile(compose_obj)

    assert mc_compose.get_server_name() == "testserver"
    assert mc_compose.get_game_version() == "1.20.4"
    assert mc_compose.get_game_port() == 25565
    assert mc_compose.get_rcon_port() == 25575


def test_mc_compose_file_custom_ports():
    """测试自定义端口"""
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-customserver",
                "environment": {"VERSION": "1.19.4"},
                "ports": ["9999:25565", "9998:25575"],
                "stdin_open": True,
                "tty": True,
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    mc_compose = MCComposeFile(compose_obj)

    assert mc_compose.get_server_name() == "customserver"
    assert mc_compose.get_game_version() == "1.19.4"
    assert mc_compose.get_game_port() == 9999
    assert mc_compose.get_rcon_port() == 9998


def test_mc_compose_file_validation_errors():
    """测试验证错误"""
    # 没有services
    with pytest.raises(ValueError, match="Could not find services in compose file"):
        compose_obj = ComposeFile.from_dict({})
        MCComposeFile(compose_obj)

    # 没有mc服务
    with pytest.raises(ValueError, match="Could not find service mc in compose file"):
        compose_obj = ComposeFile.from_dict({"services": {"web": {}}})
        MCComposeFile(compose_obj)

    # 容器名不符合规范
    with pytest.raises(ValueError, match="Container name must start with 'mc-'"):
        test_data: dict[str, Any] = {
            "services": {
                "mc": {
                    "container_name": "wrong-name",
                    "image": "itzg/minecraft-server",
                    "environment": {"VERSION": "1.20.4"},
                    "ports": ["25565:25565", "25575:25575"],
                }
            }
        }
        compose_obj = ComposeFile.from_dict(test_data)
        MCComposeFile(compose_obj)

    # 没有VERSION环境变量
    with pytest.raises(ValueError, match="Could not find VERSION in environment"):
        test_data: dict[str, Any] = {
            "services": {
                "mc": {
                    "container_name": "mc-test",
                    "image": "itzg/minecraft-server",
                    "environment": {},
                    "ports": ["25565:25565", "25575:25575"],
                }
            }
        }
        compose_obj = ComposeFile.from_dict(test_data)
        MCComposeFile(compose_obj)


def test_mc_compose_file_get_server_name():
    """测试get_server_name方法"""
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25565:25565", "25575:25575"],
                "stdin_open": True,
                "tty": True,
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    mc_compose = MCComposeFile(compose_obj)

    assert mc_compose.get_server_name() == "testserver"

    # 测试不同的服务器名称
    test_data["services"]["mc"]["container_name"] = "mc-myserver123"
    compose_obj2 = ComposeFile.from_dict(test_data)
    mc_compose2 = MCComposeFile(compose_obj2)
    assert mc_compose2.get_server_name() == "myserver123"


def test_mc_compose_file_validation_edge_cases():
    """测试更多验证失败的边缘情况"""
    # 测试容器名不是字符串
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": None,  # 不是字符串
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25565:25565", "25575:25575"],
                "volumes": ["./data:/data"],
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(ValueError, match="Invalid container name in compose file"):
        MCComposeFile(compose_obj)

    # 测试容器名不以mc-开头
    test_data["services"]["mc"]["container_name"] = "wrong-name"
    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(ValueError, match="Container name must start with 'mc-'"):
        MCComposeFile(compose_obj)

    # 测试镜像为None
    test_data["services"]["mc"]["container_name"] = "mc-test"
    test_data["services"]["mc"]["image"] = None
    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(
        ValueError, match="Service must use itzg/minecraft-server image"
    ):
        MCComposeFile(compose_obj)

    # 测试镜像不包含itzg/minecraft-server
    test_data["services"]["mc"]["image"] = "wrong/image:latest"
    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(
        ValueError, match="Service must use itzg/minecraft-server image"
    ):
        MCComposeFile(compose_obj)

    # 测试缺少游戏端口
    test_data["services"]["mc"]["image"] = "itzg/minecraft-server:java21-alpine"
    test_data["services"]["mc"]["ports"] = ["25575:25575"]  # 只有rcon端口
    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(
        ValueError, match="Could not find game port \\(25565\\) in compose file"
    ):
        MCComposeFile(compose_obj)

    # 测试缺少rcon端口
    test_data["services"]["mc"]["ports"] = ["25565:25565"]  # 只有游戏端口
    compose_obj = ComposeFile.from_dict(test_data)
    with pytest.raises(
        ValueError, match="Could not find rcon port \\(25575\\) in compose file"
    ):
        MCComposeFile(compose_obj)


def test_mc_compose_file_volumes_none():
    """测试volumes为None的情况"""
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25565:25565", "25575:25575"],
                "volumes": None,  # volumes为None
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    mc_compose = MCComposeFile(compose_obj)

    # 应该成功创建，volumes应该是空列表
    assert mc_compose.mc_service.volumes == []


def test_mc_compose_file_port_errors():
    """测试端口访问时的错误情况"""
    # 创建一个缺少游戏端口的配置来测试错误情况
    no_game_port_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25575:25575"],  # 只有RCON端口，没有游戏端口
                "volumes": ["./data:/data"],
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    # 测试缺少游戏端口的情况
    with pytest.raises(
        ValueError, match="Could not find game port \\(25565\\) in compose file"
    ):
        compose_obj = ComposeFile.from_dict(no_game_port_data)
        MCComposeFile(compose_obj)

    # 创建一个缺少RCON端口的配置来测试错误情况
    no_rcon_port_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25565:25565"],  # 只有游戏端口，没有RCON端口
                "volumes": ["./data:/data"],
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    # 测试缺少RCON端口的情况
    with pytest.raises(
        ValueError, match="Could not find rcon port \\(25575\\) in compose file"
    ):
        compose_obj = ComposeFile.from_dict(no_rcon_port_data)
        MCComposeFile(compose_obj)


def test_mc_compose_file_default_ports():
    """测试默认端口（published为None）的情况"""
    test_data: dict[str, Any] = {
        "services": {
            "mc": {
                "image": "itzg/minecraft-server:java21-alpine",
                "container_name": "mc-testserver",
                "environment": {"VERSION": "1.20.4"},
                "ports": ["25565:25565", "25575:25575"],
                "volumes": ["./data:/data"],
                "stdin_open": True,
                "tty": True,
                "restart": "unless-stopped",
            }
        }
    }

    compose_obj = ComposeFile.from_dict(test_data)
    mc_compose = MCComposeFile(compose_obj)

    # 手动设置published为None来测试默认端口
    for port in mc_compose.mc_service.ports:
        if str(port.target) == "25565":
            port.published = None
        elif str(port.target) == "25575":
            port.published = None

    assert mc_compose.get_game_port() == 25565  # 默认端口
    assert mc_compose.get_rcon_port() == 25575  # 默认端口


if __name__ == "__main__":
    pytest.main()
