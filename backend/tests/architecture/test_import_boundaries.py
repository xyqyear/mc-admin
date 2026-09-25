import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
RETIRED = {
    "app.models", "app.servers.configuration", "app.servers.rebuild",
    "app.players.tracking", "app.self_check.runner", "app.routers.servers.utils.server_list",
}


def import_violations(module: str, source: str, *, package: bool = False) -> list[str]:
    tree = ast.parse(source)
    violations = []
    parts = module.split(".") if package else module.split(".")[:-1]
    feature = module.split(".")[1] if "." in module else ""
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        imports = []
        if isinstance(node, ast.Import):
            imports = [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                target = ".".join(parts[:len(parts) - node.level + 1] + ([target] if target else []))
            imports = [(target, alias.name) for alias in node.names]
        for target, name in imports:
            if target in RETIRED or name and f"{target}.{name}" in RETIRED:
                violations.append(f"{line}: retired module {target}")
            if (target == "app.routers" or target.startswith("app.routers.")) and feature not in {"routers", "main"}:
                violations.append(f"{line}: domain imports HTTP transport {target}")
            if target.startswith("app.") and target.split(".")[1] != feature and (
                name and name.startswith("_") or any(part.startswith("_") for part in target.split(".")[2:])
            ):
                violations.append(f"{line}: cross-feature private import {target}.{name or ''}")
            if target == "app.db.metadata" and feature != "db":
                violations.append(f"{line}: feature imports eager application metadata")
            if name in {"runtime_proxy", "resource_factory", "_RuntimeProxy"}:
                violations.append(f"{line}: implicit runtime construction {name}")
        if isinstance(node, ast.ClassDef) and node.name == "_RuntimeProxy":
            violations.append(f"{node.lineno}: transparent runtime proxy")
        if isinstance(node, ast.FunctionDef) and node.name in {"runtime_proxy", "resource_factory"}:
            violations.append(f"{node.lineno}: import-time factory registration")
    return violations


def test_production_imports_respect_feature_and_transport_boundaries():
    violations = []
    for path in sorted(APP.rglob("*.py")):
        module = "app." + ".".join(path.relative_to(APP).with_suffix("").parts)
        module = module.removesuffix(".__init__")
        violations.extend(f"{path.relative_to(APP)}:{message}" for message in import_violations(
            module, path.read_text(), package=path.name == "__init__.py",
        ))
    assert violations == []


def test_import_rules_reject_actual_boundary_regressions():
    invalid = [
        "from ..routers.servers.world_restore import mark_running_restorations_interrupted",
        "from app.servers.rebuild import rebuild_server_task",
        "from app.servers import rebuild",
        "from app import models",
        "import app.players._internal",
        "from ..ftb_claims.extract import _run_extract",
        "from ..runtime_resources import runtime_proxy",
        "from ..db.metadata import Base",
    ]
    assert all(import_violations("app.operations.execution", source) for source in invalid)
    assert import_violations("app.operations.execution", "from ..world.recovery import mark_running_restorations_interrupted") == []
    assert import_violations("app.main", "from .routers import cron") == []


def test_runtime_accessors_are_named_and_typed_and_retired_files_are_absent():
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef):
                continue
            reads_runtime_resource = any(
                isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "resource"
                and isinstance(child.func.value, ast.Call) and isinstance(child.func.value.func, ast.Name)
                and child.func.value.func.id == "current_runtime"
                for child in ast.walk(node)
            )
            if reads_runtime_resource:
                assert node.name.startswith("get_"), (path, node.name)
                assert node.returns is not None, (path, node.name)
    for module in RETIRED:
        assert not APP.parent.joinpath(*module.split(".")).with_suffix(".py").exists()
