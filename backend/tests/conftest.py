from collections.abc import Generator

import pytest

from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import (
    Principal,
    require_admin,
    require_admin_csrf,
    require_authenticated,
)


class NoDatabaseSession:
    pass


def _admin() -> Principal:
    return Principal(1, "contract-admin@example.invalid", "ADMIN", None, None)  # type: ignore[arg-type]


def _no_database() -> Generator[NoDatabaseSession]:
    yield NoDatabaseSession()


@pytest.fixture(autouse=True)
def preserve_pre_auth_contracts(request: pytest.FixtureRequest):
    if request.node.get_closest_marker("postgres"):
        yield
        return
    app.dependency_overrides[require_authenticated] = _admin
    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[require_admin_csrf] = _admin
    app.dependency_overrides[get_db] = _no_database
    try:
        yield
    finally:
        app.dependency_overrides.clear()
