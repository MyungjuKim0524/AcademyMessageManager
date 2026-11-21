import os

from sqlalchemy import func, select

from app.db.models.tables import StaffUser
from app.db.session import create_db_engine, create_session_factory
from app.modules.auth.service import hash_password


def main() -> int:
    if os.getenv("ACADEMY_BOOTSTRAP_ADMIN") != "1":
        raise RuntimeError("ACADEMY_BOOTSTRAP_ADMIN=1 explicit switch is required")
    email = os.getenv("ACADEMY_BOOTSTRAP_EMAIL", "").strip().lower()
    password = os.getenv("ACADEMY_BOOTSTRAP_PASSWORD", "")
    if not email or "@" not in email or len(email) > 255:
        raise RuntimeError("a valid ACADEMY_BOOTSTRAP_EMAIL is required")
    if len(password) < 12 or len(password) > 1024:
        raise RuntimeError("ACADEMY_BOOTSTRAP_PASSWORD must be 12-1024 characters")

    engine = create_db_engine()
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            existing = session.scalar(
                select(StaffUser).where(func.lower(StaffUser.email) == email)
            )
            if existing is not None:
                raise RuntimeError("staff account already exists; refusing to overwrite")
            session.add(
                StaffUser(
                    email=email,
                    password_hash=hash_password(password),
                    role="ADMIN",
                    status="ACTIVE",
                )
            )
    finally:
        engine.dispose()
        password = ""
    print("Administrator account created without exposing credentials.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from None
