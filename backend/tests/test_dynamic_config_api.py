"""
API endpoint tests for the dynamic configuration system.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dynamic_config import BaseConfigSchema
from app.dynamic_config.manager import ConfigManager
from app.main import app
from app.models import Base


# Test configuration schemas for API testing
class ApiTestConfig(BaseConfigSchema):
    """Simple configuration for API testing."""

    api_name: str = Field(default="api_test", description="API test configuration name")
    api_enabled: bool = Field(default=True, description="Whether API is enabled")
    api_count: int = Field(default=5, description="API count value")
    api_deprecated: str = Field(
        default="old_api_value",
        description="Deprecated API field",
        deprecated="Use api_name instead",
    )


class ApiNestedConfig(BaseConfigSchema):
    """Nested configuration for API testing."""

    nested_value: str = Field(default="api_nested", description="Nested value")
    nested_number: int = Field(default=100, description="Nested number")


class ApiComplexConfig(BaseConfigSchema):
    """Complex configuration for API testing."""

    main_field: str = Field(default="api_main", description="Main field")
    nested: ApiNestedConfig = Field(
        default_factory=ApiNestedConfig, description="Nested configuration"
    )
    tags: list[str] = Field(default=["api", "test"], description="List of tags")


@pytest.fixture(scope="function")
async def test_api_db():
    """Create a test database for API tests."""
    # Create temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    database_url = f"sqlite+aiosqlite:///{temp_db.name}"
    engine = create_async_engine(database_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Replace the database session in manager module
    import app.dynamic_config.manager as manager_module

    original_session_local = manager_module.AsyncSessionLocal

    TestSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    manager_module.AsyncSessionLocal = TestSessionLocal

    # Create and setup test configuration manager
    test_manager = ConfigManager()
    test_manager.register_config("api_test", ApiTestConfig)
    test_manager.register_config("api_complex", ApiComplexConfig)

    # Replace global config manager
    import app.dynamic_config as config_module
    import app.routers.config as router_module

    original_manager = config_module.config_manager
    original_router_manager = router_module.config_manager
    config_module.config_manager = test_manager
    router_module.config_manager = test_manager

    # Initialize configurations
    await test_manager.initialize_all_configs()

    yield test_manager

    # Cleanup
    config_module.config_manager = original_manager
    router_module.config_manager = original_router_manager
    manager_module.AsyncSessionLocal = original_session_local
    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
def api_client():
    """Create a test client for API testing."""
    # Mock settings to set up master token
    with patch("app.dependencies.settings") as mock_settings:
        mock_settings.master_token = "test_master_token"
        client = TestClient(app)
        yield client


@pytest.fixture
async def authenticated_headers():
    """Get authentication headers for API requests."""
    # Use master token for authentication in tests
    return {"Authorization": "Bearer test_master_token"}


class TestConfigAPI:
    """Test the dynamic configuration API endpoints."""

    @pytest.mark.asyncio
    async def test_list_all_modules(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/modules - List all configuration modules."""
        response = api_client.get("/api/config/modules", headers=authenticated_headers)

        assert response.status_code == 200
        data = response.json()

        assert "modules" in data
        modules = data["modules"]

        # Should have our test modules
        assert "api_test" in modules
        assert "api_complex" in modules

        # Check module structure
        api_test_module = modules["api_test"]
        assert api_test_module["module_name"] == "api_test"
        assert api_test_module["schema_class"] == "ApiTestConfig"
        assert "version" in api_test_module
        assert "json_schema" in api_test_module

        # Verify JSON Schema structure
        json_schema = api_test_module["json_schema"]
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["title"] == "ApiTestConfig"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema

        # Check that basic fields are present in JSON Schema
        properties = json_schema["properties"]
        assert "api_name" in properties
        assert "api_enabled" in properties
        assert "api_count" in properties
        assert "api_deprecated" in properties

    @pytest.mark.asyncio
    async def test_get_module_config(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/modules/{module_name} - Get configuration data."""
        response = api_client.get(
            "/api/config/modules/api_test", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["module_name"] == "api_test"
        assert "config_data" in data
        assert "schema_version" in data

        config_data = data["config_data"]
        assert config_data["api_name"] == "api_test"
        assert config_data["api_enabled"] is True
        assert config_data["api_count"] == 5
        assert config_data["api_deprecated"] == "old_api_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent_module(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/modules/{module_name} - Nonexistent module."""
        response = api_client.get(
            "/api/config/modules/nonexistent", headers=authenticated_headers
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_module_config(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test PUT /api/config/modules/{module_name} - Update configuration."""
        update_data = {
            "config_data": {
                "api_name": "updated_api_test",
                "api_enabled": False,
                "api_count": 99,
                "api_deprecated": "updated_deprecated",
            }
        }

        response = api_client.put(
            "/api/config/modules/api_test",
            json=update_data,
            headers=authenticated_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "updated successfully" in data["message"]

        updated_config = data["updated_config"]
        assert updated_config["api_name"] == "updated_api_test"
        assert updated_config["api_enabled"] is False
        assert updated_config["api_count"] == 99
        assert updated_config["api_deprecated"] == "updated_deprecated"

        # Verify the update persisted by fetching again
        get_response = api_client.get(
            "/api/config/modules/api_test", headers=authenticated_headers
        )
        assert get_response.status_code == 200
        get_data = get_response.json()["config_data"]
        assert get_data["api_name"] == "updated_api_test"
        assert get_data["api_enabled"] is False
        assert get_data["api_count"] == 99

    @pytest.mark.asyncio
    async def test_update_invalid_config(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test PUT /api/config/modules/{module_name} - Invalid configuration data."""
        invalid_data = {
            "config_data": {
                "api_name": "test",
                "api_enabled": "not_a_boolean",  # Invalid type
                "api_count": "not_a_number",  # Invalid type
            }
        }

        response = api_client.put(
            "/api/config/modules/api_test",
            json=invalid_data,
            headers=authenticated_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "Invalid configuration data" in data["detail"]

    @pytest.mark.asyncio
    async def test_get_module_schema(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/modules/{module_name}/schema - Get module schema."""
        response = api_client.get(
            "/api/config/modules/api_test/schema", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["module_name"] == "api_test"
        assert data["schema_class"] == "ApiTestConfig"
        assert "version" in data
        assert "json_schema" in data

        # Check JSON Schema structure
        json_schema = data["json_schema"]
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["title"] == "ApiTestConfig"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema

        # Check field information in JSON Schema
        properties = json_schema["properties"]
        assert "api_name" in properties
        assert properties["api_name"]["description"] == "API test configuration name"
        assert "api_deprecated" in properties  # Still a valid field in schema

    @pytest.mark.asyncio
    async def test_get_module_metadata(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/modules/{module_name}/metadata - Get detailed metadata."""
        response = api_client.get(
            "/api/config/modules/api_complex/metadata", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["module_name"] == "api_complex"
        assert "schema_version" in data
        assert "json_schema" in data

        # Check JSON Schema structure
        json_schema = data["json_schema"]
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["title"] == "ApiComplexConfig"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema
        assert "definitions" in json_schema

        # Check nested structure through JSON Schema
        properties = json_schema["properties"]
        assert "nested" in properties
        assert properties["nested"]["$ref"] == "#/definitions/ApiNestedConfig"

        definitions = json_schema["definitions"]
        assert "ApiNestedConfig" in definitions
        nested_schema = definitions["ApiNestedConfig"]
        assert "nested_value" in nested_schema["properties"]
        assert (
            nested_schema["properties"]["nested_value"]["description"] == "Nested value"
        )

    @pytest.mark.asyncio
    async def test_reset_module_config(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test POST /api/config/modules/{module_name}/reset - Reset to defaults."""
        # First update the config
        update_data = {
            "config_data": {
                "api_name": "custom_name",
                "api_enabled": False,
                "api_count": 999,
                "api_deprecated": "custom_deprecated",
            }
        }

        api_client.put(
            "/api/config/modules/api_test",
            json=update_data,
            headers=authenticated_headers,
        )

        # Now reset it
        response = api_client.post(
            "/api/config/modules/api_test/reset", headers=authenticated_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "reset to defaults" in data["message"]

        reset_config = data["updated_config"]
        assert reset_config["api_name"] == "api_test"  # back to default
        assert reset_config["api_enabled"] is True  # back to default
        assert reset_config["api_count"] == 5  # back to default
        assert reset_config["api_deprecated"] == "old_api_value"  # back to default

    @pytest.mark.asyncio
    async def test_complex_config_operations(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test operations on complex configuration with nested structures."""
        # Get initial complex config
        response = api_client.get(
            "/api/config/modules/api_complex", headers=authenticated_headers
        )
        assert response.status_code == 200

        initial_data = response.json()["config_data"]
        assert initial_data["main_field"] == "api_main"
        assert initial_data["nested"]["nested_value"] == "api_nested"
        assert initial_data["nested"]["nested_number"] == 100
        assert initial_data["tags"] == ["api", "test"]

        # Update with nested changes
        update_data = {
            "config_data": {
                "main_field": "updated_main",
                "nested": {"nested_value": "updated_nested", "nested_number": 999},
                "tags": ["updated", "tags", "list"],
            }
        }

        response = api_client.put(
            "/api/config/modules/api_complex",
            json=update_data,
            headers=authenticated_headers,
        )

        assert response.status_code == 200
        updated_config = response.json()["updated_config"]

        assert updated_config["main_field"] == "updated_main"
        assert updated_config["nested"]["nested_value"] == "updated_nested"
        assert updated_config["nested"]["nested_number"] == 999
        assert updated_config["tags"] == ["updated", "tags", "list"]

    @pytest.mark.asyncio
    async def test_config_health_check(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test GET /api/config/health - Health check endpoint."""
        response = api_client.get("/api/config/health", headers=authenticated_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "healthy" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_api_error_handling(
        self, test_api_db, api_client, authenticated_headers
    ):
        """Test API error handling for various edge cases."""
        # Test updating nonexistent module
        update_data = {"config_data": {"some": "data"}}
        response = api_client.put(
            "/api/config/modules/nonexistent",
            json=update_data,
            headers=authenticated_headers,
        )
        assert response.status_code == 400  # Should be bad request for unknown module

        # Test reset nonexistent module
        response = api_client.post(
            "/api/config/modules/nonexistent/reset", headers=authenticated_headers
        )
        assert response.status_code == 404

        # Test get schema for nonexistent module
        response = api_client.get(
            "/api/config/modules/nonexistent/schema", headers=authenticated_headers
        )
        assert response.status_code == 404

        # Test get metadata for nonexistent module
        response = api_client.get(
            "/api/config/modules/nonexistent/metadata", headers=authenticated_headers
        )
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
