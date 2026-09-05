import re
from dataclasses import dataclass
from typing import Any

import yaml

GAME_CONTAINER_PORT = 25565
TEMPLATE_VARIABLE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


@dataclass(frozen=True)
class GamePortMapping:
    target: int
    published: str | int | None


def _port_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 65535 else None
    if isinstance(value, float) and value.is_integer():
        return _port_number(int(value))
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,5}", value.strip()):
        return _port_number(int(value.strip()))
    return None


def _mc_service(compose_yaml: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(compose_yaml)
    except yaml.YAMLError:
        raise ValueError("无法解析 Compose YAML，请检查配置格式。") from None
    services = document.get("services") if isinstance(document, dict) else None
    service = services.get("mc") if isinstance(services, dict) else None
    if not isinstance(service, dict):
        raise ValueError("Compose 必须包含 services.mc 服务配置。")
    return service


def _game_mapping(service: dict[str, Any]) -> GamePortMapping:
    ports = service.get("ports")
    if isinstance(ports, list):
        for port in ports:
            published = None
            protocol = "tcp"
            if isinstance(port, dict):
                target = port.get("target")
                protocol = port.get("protocol", "tcp")
                published = port.get("published")
            elif isinstance(port, str):
                mapping, separator, suffix = port.rpartition("/")
                if separator:
                    protocol = suffix
                else:
                    mapping = port
                parts = mapping.rsplit(":", 2)
                target = parts[-1]
                if len(parts) > 1:
                    published = parts[-2]
            else:
                target = port
            if protocol == "tcp" and _port_number(target) == GAME_CONTAINER_PORT:
                return GamePortMapping(
                    target=GAME_CONTAINER_PORT,
                    published=published if isinstance(published, (str, int)) else None,
                )
    raise ValueError(
        "ports 必须包含容器目标端口固定为 25565 的 TCP 游戏映射；"
        "请使用 <宿主机端口>:25565，不要将容器目标端口设为变量。"
    )


def get_game_port_mapping(compose_yaml: str) -> GamePortMapping:
    return _game_mapping(_mc_service(compose_yaml))


def get_properties_game_port(content: str) -> int:
    values = re.findall(r"(?m)^[ \t]*server-port[ \t]*=([^\r\n]*)", content)
    port = _port_number(values[-1]) if values else None
    if port is None:
        raise ValueError("server.properties 缺少有效的 server-port，必须为 1–65535 的整数。")
    return port


def validate_game_port_initialization(
    compose_yaml: str, *, template: bool = False
) -> None:
    if template:
        # Scalar markers preserve template structure without inventing variable defaults.
        compose_yaml = TEMPLATE_VARIABLE.sub("__mc_template_variable__", compose_yaml)
    service = _mc_service(compose_yaml)
    mapping = _game_mapping(service)
    environment = service.get("environment")
    if isinstance(environment, list):
        values = {}
        for entry in environment:
            if isinstance(entry, str):
                key, _, value = entry.partition("=")
                values[key] = value
        environment = values
    if not isinstance(environment, dict):
        environment = {}
    if _port_number(environment.get("SERVER_PORT")) != mapping.target:
        raise ValueError(
            "请在 services.mc.environment 中显式设置固定的 SERVER_PORT=25565，"
            "与 ports 的容器目标端口一致；不要使用变量或填写宿主机端口。"
        )
    for name, expected in (
        ("OVERRIDE_SERVER_PROPERTIES", True),
        ("SKIP_SERVER_PROPERTIES", False),
    ):
        if name not in environment:
            continue
        value = environment[name]
        if isinstance(value, str) and value.lower() in ("true", "false"):
            value = value.lower() == "true"
        if not isinstance(value, bool) or value != expected:
            required = str(expected).lower()
            raise ValueError(
                f"{name} 必须省略或设置为固定的 {required}，"
                "以便启动时更新上传的 server.properties。"
            )
