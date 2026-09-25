from datetime import UTC, datetime

import pytest
from joserfc import jwt

from app.auth.models import User, UserRole
from app.auth.service import TokenValidationError, user_to_public
from app.db.metadata import Base
from app.runtime import Runtime


async def test_identity_service_keeps_own_database_and_signing_key_across_contexts(tmp_path, isolated_runtime):
    runtimes = []
    services = []
    tokens = []
    for index in range(2):
        settings = isolated_runtime.settings.model_copy(deep=True)
        settings.database_url = f"sqlite+aiosqlite:///{tmp_path / f'identity-{index}.sqlite3'}"
        settings.master_token = f"synthetic-master-{index}"
        settings.jwt.secret_key = f"synthetic-signing-key-for-runtime-{index}-at-least-32-bytes"
        runtime = Runtime(settings)
        runtimes.append(runtime)
    try:
        for index, runtime in enumerate(runtimes):
            async with runtime.database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            service = runtime.resource("identity_service")
            services.append(service)
            async with runtime.database.session_factory() as session:
                user = User(
                    id=1, username=f"owner-{index}", hashed_password="unused",
                    role=UserRole.OWNER, created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
                session.add(user)
                await session.commit()
                tokens.append(service.create_session_token(user_to_public(user))[0])

        with runtimes[1].bind():
            first = await services[0].get_user_from_auth_values(tokens[0], None)
            assert first.username == "owner-0"
            assert services[0].is_master_authorization("Bearer synthetic-master-0")
            assert not services[0].is_master_authorization("Bearer synthetic-master-1")
            with pytest.raises(TokenValidationError):
                services[1].decode_session_claims(tokens[0])
            async with runtimes[0].database.session_factory() as session:
                user = await session.get(User, 1)
                assert user is not None
                user.role = UserRole.ADMIN
                await session.commit()
            assert (await services[0].get_user_from_auth_values(tokens[0], None)).role == UserRole.ADMIN
            assert (await services[1].get_user_from_auth_values(tokens[1], None)).role == UserRole.OWNER
    finally:
        for runtime in runtimes:
            await runtime.close()


def test_invalid_signed_claims_do_not_disclose_claim_values(isolated_runtime):
    secret = "synthetic-secret-in-invalid-session-claim"
    service = isolated_runtime.resource("identity_service")
    token = jwt.encode({"alg": "HS256"}, {"user_id": secret}, service.signing_key)
    with pytest.raises(TokenValidationError) as caught:
        service.decode_session_claims(token)
    assert secret not in str(caught.value)
    assert str(caught.value) == "登录会话内容无效"
