from pydantic import BaseModel, ConfigDict, Field, StrictStr


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: StrictStr = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    )
    password: StrictStr = Field(min_length=1, max_length=1024)


class CurrentStaff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    email: str
    display_name: str | None = None
    role: str


class AuthResponse(BaseModel):
    user: CurrentStaff


class LogoutResponse(BaseModel):
    loggedOut: bool


class ClientAddressDiagnosis(BaseModel):
    """How the server sees the caller's own request (deployment check, admin only, off by
    default). Holds only the caller's addresses and proxy hops — never the edge secret."""

    model_config = ConfigDict(extra="forbid")
    peer: str | None
    forwarded_for: list[str]
    client_ip_header: str | None
    client_ip_header_value: str | None
    edge_secret: str  # not-configured | missing | invalid | valid
    resolved: str
    source: str  # edge | client-ip-header | trusted-proxies | peer
    limiter_bucket: str


class PasswordChange(BaseModel):
    """SEC-10-A. The length rule is checked by the service so the answer can say what is
    wrong (the generic request-validation error would not)."""

    model_config = ConfigDict(extra="forbid")
    current_password: StrictStr = Field(min_length=1, max_length=1024)
    new_password: StrictStr = Field(min_length=1, max_length=1024)


class PasswordChanged(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changed: bool
    other_sessions_revoked: int


class PasswordResetComplete(BaseModel):
    """SEC-10-B: set a new password with a one-time code issued by an administrator."""

    model_config = ConfigDict(extra="forbid")
    email: StrictStr = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    code: StrictStr = Field(min_length=1, max_length=32)
    new_password: StrictStr = Field(min_length=1, max_length=1024)


class PasswordResetDone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reset: bool
