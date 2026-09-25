"""Compare persisted schedule intent with the live scheduler definition."""

import hashlib
import json

from ..dynamic_config.schemas import BaseConfigSchema
from .bindings import RetainedCronParams


def definition_version(identifier: str, params_json: str, cron: str, second: str | None) -> str:
    payload = json.dumps([identifier, json.loads(params_json), cron, second], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def retained_params(params_json: str) -> BaseConfigSchema:
    try:
        value = json.loads(params_json)
    except (ValueError, TypeError):
        value = {}
    return RetainedCronParams.model_validate(value if isinstance(value, dict) else {})
