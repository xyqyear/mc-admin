"""YAML comparison utilities for template system."""

import yaml


def are_yaml_semantically_equal(yaml1: str, yaml2: str) -> bool:
    """Check if two YAML strings are semantically equal.

    Compares the parsed Python objects (dicts and lists) for equality.
    Dict key ordering differences are ignored, but list element ordering matters.

    Args:
        yaml1: First YAML string
        yaml2: Second YAML string

    Returns:
        True if the YAML documents are semantically equal, False otherwise.
        Returns False if either YAML fails to parse.
    """
    try:
        parsed1 = yaml.safe_load(yaml1)
        parsed2 = yaml.safe_load(yaml2)
        return parsed1 == parsed2
    except yaml.YAMLError:
        # If YAML parsing fails, assume they're different
        return False
