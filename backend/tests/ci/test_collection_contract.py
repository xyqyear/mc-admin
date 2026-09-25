from copy import deepcopy

import pytest

from tests.support.collection import audit, matrix


def fixture():
    cases = [
        {"nodeid": "tests/test_a.py::test_a", "group": "root", "capabilities": []},
        {"nodeid": "tests/docker/test_b.py::test_b", "group": "docker", "capabilities": ["docker"]},
        {"nodeid": "tests/cloud/test_c.py::test_c", "group": "cloud", "capabilities": ["external"]},
    ]
    return {"collected": cases, "selected": [case["nodeid"] for case in cases[:2]],
            "policy": {"docker": True, "external": False, "group": None, "expression": ""}}


def shards(expected):
    result = []
    for item in matrix(expected)["include"]:
        shard = deepcopy(expected)
        shard["policy"]["group"] = item["test_group"]
        shard["selected"] = [case["nodeid"] for case in expected["collected"] if case["group"] == item["test_group"]]
        result.append(shard)
    return result


def test_discovery_preserves_explicit_external_exclusion_and_exact_capabilities():
    expected = fixture()
    assert matrix(expected) == {"include": [
        {"test_group": "docker", "capabilities": ["docker"]},
        {"test_group": "root", "capabilities": []},
    ]}
    audit(expected, shards(expected))
    default = deepcopy(expected)
    default["selected"] = [expected["selected"][0]]
    default["policy"]["docker"] = False
    assert matrix(default) == {"include": [{"test_group": "root", "capabilities": []}]}
    audit(default, shards(default))


@pytest.mark.parametrize("mutation", ["capability", "policy", "group", "selected", "duplicate_inventory"])
def test_shard_audit_rejects_changed_capability_metadata_or_selection(mutation):
    expected = fixture()
    actual = shards(expected)
    if mutation == "capability":
        actual[0]["collected"][1]["capabilities"] = []
    elif mutation == "policy":
        actual[0]["policy"]["docker"] = False
    elif mutation == "group":
        actual[0]["policy"]["group"] = "root"
    elif mutation == "selected":
        actual[0]["selected"].append("tests/cloud/test_c.py::test_c")
    else:
        actual[0]["collected"].append(actual[0]["collected"][0])
    with pytest.raises(ValueError):
        audit(expected, actual)
