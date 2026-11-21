import ipaddress
import os

from app.config import get_settings
from app.errors import CompatibilityError


def require_local_db_api() -> None:
    """DB-backed APIs are off unless explicitly enabled. Local modes (development / test) also
    require a loopback bind. Phase 11-4-B (SEC-04): ``production`` is the deployed mode; it
    binds to the platform's interface and is instead guarded by the start-up check
    (``config.production_problems``, enforced in ``app.main``) and the production DB rules."""
    settings = get_settings()
    mode = os.getenv("ACADEMY_DB_MODE")
    if not settings.db_apis_enabled:
        raise CompatibilityError(404, "DB_API_DISABLED", "요청한 기능을 사용할 수 없습니다.")
    if mode == "production":
        return
    try:
        is_loopback = ipaddress.ip_address(settings.api_host).is_loopback
    except ValueError:
        is_loopback = settings.api_host == "localhost"
    if not is_loopback or mode not in {"development", "test"}:
        raise CompatibilityError(404, "DB_API_DISABLED", "요청한 기능을 사용할 수 없습니다.")


def authorization_boundary() -> None:
    """Phase 5 replaces this local-only gate with authenticated RBAC checks."""
    require_local_db_api()
