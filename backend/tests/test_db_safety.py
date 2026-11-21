import pytest

from app.db.base import Base
from app.db.models import tables  # noqa: F401
from app.db.safety import UnsafeDatabaseError, validate_test_database_url

URL = "postgresql+psycopg://academy_test:secret@127.0.0.1:55432/academy_learningops_test"


def test_database_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACADEMY_DB_MODE", raising=False)
    monkeypatch.delenv("ACADEMY_DB_TEST_MODE", raising=False)
    with pytest.raises(UnsafeDatabaseError, match="DB_MODE"):
        validate_test_database_url(URL)


def test_test_database_requires_second_explicit_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.delenv("ACADEMY_DB_TEST_MODE", raising=False)
    with pytest.raises(UnsafeDatabaseError, match="DB_TEST_MODE"):
        validate_test_database_url(URL)


def test_development_database_has_a_separate_fixed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACADEMY_DB_MODE", "development")
    url = validate_test_database_url(
        "postgresql+psycopg://academy_dev:secret@127.0.0.1:55431/academy_learningops_dev"
    )
    assert url.database == "academy_learningops_dev"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://academy_test:secret@localhost:55432/academy_learningops_test",
        "postgresql+psycopg://postgres:secret@127.0.0.1:55432/academy_learningops_test",
        "postgresql+psycopg://academy_test:secret@127.0.0.1:55432/academy_learningops",
        "postgresql+psycopg://academy_test:secret@127.0.0.1:5432/academy_learningops_test",
    ],
)
def test_database_target_must_match_every_allowlisted_value(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("ACADEMY_DB_MODE", "test")
    monkeypatch.setenv("ACADEMY_DB_TEST_MODE", "1")
    with pytest.raises(UnsafeDatabaseError, match="허용 목록"):
        validate_test_database_url(url)


def test_metadata_preserves_legacy_tables_and_adds_auth_tables() -> None:
    assert {
        "student",
        "classroom",
        "enrollment",
        "lesson",
        "lesson_result",
        "makeup_request",
        "message_template",
        "message_draft",
        "delivery_job",
        "delivery_attempt",
    }.issubset(Base.metadata.tables)
    # The legacy import tables were dropped by migration 010.
    assert not {"import_job", "import_row", "import_error"} & set(Base.metadata.tables)
    assert set(Base.metadata.tables) - {
        "student", "classroom", "enrollment", "lesson", "lesson_result", "makeup_request",
        "message_template", "message_draft", "delivery_job", "delivery_attempt",
    } == {
        "staff_user",
        "classroom_staff_assignment",
        "auth_session",
        "audit_log",
        "assessment",  # Phase 7
        "assessment_result",  # Phase 7
        "enrollment_pause",  # Phase 7.1
        "notification_template",  # Phase 8
        "parent_notification",  # Phase 8
        "notification_send_attempt",  # Phase 8
    }
