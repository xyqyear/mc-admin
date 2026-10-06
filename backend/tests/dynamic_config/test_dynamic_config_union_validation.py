from typing import Annotated, Literal

import pytest
from pydantic import Field

from app.dynamic_config.configs.dns import DNSManagerConfig, DNSPod, Huawei
from app.dynamic_config.schemas import BaseConfigSchema


class ConfigA(BaseConfigSchema):
    type: Literal["a"] = "a"
    value: str = "default"


class ConfigB(BaseConfigSchema):
    type: Literal["b"] = "b"
    number: int = 0


class TestUnionFieldValidation:
    @pytest.mark.parametrize("value", [None, "authored"])
    def test_optional_primitive_union(self, value):
        class OptionalConfig(BaseConfigSchema):
            optional: str | None = None

        assert OptionalConfig.model_validate({"optional": value}).model_dump() == {"optional": value}

    @pytest.mark.parametrize("value", ["authored", 17, False])
    def test_primitive_union(self, value):
        class PrimitiveConfig(BaseConfigSchema):
            value: str | int | bool

        assert PrimitiveConfig.model_validate({"value": value}).model_dump() == {"value": value}

    @pytest.mark.parametrize("payload", [{"type": "a", "value": "edited"}, {"type": "b", "number": 37}])
    def test_all_base_union_with_discriminator(self, payload):
        class TaggedConfig(BaseConfigSchema):
            config: Annotated[ConfigA | ConfigB, Field(discriminator="type")]

        assert TaggedConfig.model_validate({"config": payload}).model_dump() == {"config": payload}
        field = TaggedConfig.model_json_schema()["properties"]["config"]
        assert field["discriminator"]["propertyName"] == "type"
        assert len(field["oneOf"]) == 2

    @pytest.mark.parametrize("value", ["literal", 19, {"type": "a", "value": "edited"}])
    def test_mixed_base_and_primitive_union(self, value):
        class MixedConfig(BaseConfigSchema):
            value: ConfigA | str | int

        assert MixedConfig.model_validate({"value": value}).model_dump() == {"value": value}
        field = MixedConfig.model_json_schema()["properties"]["value"]
        assert "anyOf" in field and "discriminator" not in field

    def test_missing_discriminator_fails_on_instance_validation(self):
        class UntaggedConfig(BaseConfigSchema):
            config: ConfigA | ConfigB

        assert "config" in UntaggedConfig.model_fields
        with pytest.raises(ValueError, match="Union field 'config'.*must have a discriminator"):
            UntaggedConfig.model_validate({"config": {"type": "a", "value": "edited"}})

    @pytest.mark.parametrize("payload", [{"backend": "postgres", "host": "database.internal"}, {"backend": "file", "path": "/owned/archive"}])
    def test_custom_discriminator(self, payload):
        class DatabaseConfig(BaseConfigSchema):
            backend: Literal["postgres"] = "postgres"
            host: str

        class FileConfig(BaseConfigSchema):
            backend: Literal["file"] = "file"
            path: str

        class StorageConfig(BaseConfigSchema):
            storage: Annotated[DatabaseConfig | FileConfig, Field(discriminator="backend")]

        assert StorageConfig.model_validate({"storage": payload}).model_dump() == {"storage": payload}
        field = StorageConfig.model_json_schema()["properties"]["storage"]
        assert field["discriminator"]["propertyName"] == "backend"
        assert len(field["oneOf"]) == 2

    def test_list_with_discriminated_union(self):
        class ListConfig(BaseConfigSchema):
            providers: list[Annotated[ConfigA | ConfigB, Field(discriminator="type")]]

        payload = {"providers": [{"type": "b", "number": 43}, {"type": "a", "value": "second"}]}
        assert ListConfig.model_validate(payload).model_dump() == payload
        field = ListConfig.model_json_schema()["properties"]["providers"]
        assert field["type"] == "array"
        assert field["items"]["discriminator"]["propertyName"] == "type"
        assert len(field["items"]["oneOf"]) == 2

    def test_non_union_field(self):
        class SingleConfig(BaseConfigSchema):
            value: str

        assert SingleConfig.model_validate({"value": "authored"}).model_dump() == {"value": "authored"}

    @pytest.mark.parametrize("optional", [None, {"type": "a", "value": "optional"}])
    def test_nested_and_multiple_union_fields(self, optional):
        class NestedConfig(BaseConfigSchema):
            config: Annotated[ConfigA | ConfigB, Field(discriminator="type")]
            value: str | int | float
            optional: ConfigA | None

        payload = {"config": {"type": "b", "number": 39}, "value": 1.25, "optional": optional}
        assert NestedConfig.model_validate(payload).model_dump() == payload
        schema = NestedConfig.model_json_schema()["properties"]
        assert "discriminator" in schema["config"]
        assert "anyOf" in schema["value"] and "discriminator" not in schema["value"]

    def test_class_definition_allows_untagged_union_until_instantiation(self):
        class MissingType(BaseConfigSchema):
            value: str

        class FailingConfig(BaseConfigSchema):
            config: ConfigA | MissingType

        assert "config" in FailingConfig.model_fields
        with pytest.raises(ValueError, match="Union field 'config'.*must have a discriminator"):
            FailingConfig.model_validate({"config": {"value": "authored"}})

    def test_valid_field_does_not_hide_later_invalid_union(self):
        class MultipleConfig(BaseConfigSchema):
            valid: Annotated[ConfigA | ConfigB, Field(discriminator="type")]
            invalid: ConfigA | ConfigB

        with pytest.raises(ValueError, match="Union field 'invalid'.*must have a discriminator"):
            MultipleConfig.model_validate({"valid": {"type": "a", "value": "first"}, "invalid": {"type": "b", "number": 17}})


@pytest.mark.parametrize("provider,provider_type", [
    ({"type": "huawei", "domain": "owned.example", "ak": "test-ak", "sk": "test-sk", "region": "cn-north-4"}, Huawei),
    ({"type": "dnspod", "domain": "owned.example", "id": "test-id", "key": "test-key"}, DNSPod),
])
def test_dns_configuration_provider_and_manual_addresses_roundtrip(provider, provider_type):
    payload = {
        "enabled": True, "dns": provider, "managed_sub_domain": "games",
        "mc_router_base_url": "http://router.internal:26666", "dns_ttl": 120,
        "addresses": [{"type": "manual", "name": "survival", "record_type": "AAAA", "value": "2001:db8::17", "port": 25567}],
    }
    config = DNSManagerConfig.model_validate(payload)
    assert isinstance(config.dns, provider_type)
    assert config.model_dump() == payload
