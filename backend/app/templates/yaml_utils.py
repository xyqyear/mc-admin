"""YAML comparison utilities for template system."""

import yaml


def are_yaml_semantically_equal(yaml1: str, yaml2: str) -> bool:
    """Compare parsed YAML structures (key order ignored, list order significant).

    Returns ``False`` when either side fails to parse.
    """
    try:
        parsed1 = yaml.safe_load(yaml1)
        parsed2 = yaml.safe_load(yaml2)
        return parsed1 == parsed2
    except yaml.YAMLError:
        return False
