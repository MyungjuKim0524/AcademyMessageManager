"""In-process mock sender. Nothing leaves this process: no network, no SMS, no e-mail.

Deterministic failure rules (for tests and demos, not exposed as a UI control), using reserved
RFC 2606 domains:

* ``mock-fail.invalid``  — always rejected (a recipient problem: retrying cannot help).
* ``mock-retry.invalid`` — Phase 9: only the message's *first* attempt fails as a temporary
  sender failure; a later manual retry succeeds. Lets the failure → retry → success flow be
  exercised without any real delivery.
"""

from dataclasses import dataclass

FAIL_DOMAIN = "mock-fail.invalid"
RETRY_DOMAIN = "mock-retry.invalid"


@dataclass(frozen=True)
class MockResult:
    success: bool
    error_code: str | None = None
    error_message: str | None = None


class MockSender:
    channel = "MOCK"

    def send(self, recipient_email: str, body: str, attempt_no: int = 1) -> MockResult:
        """``attempt_no`` is 1 for the first send of a message, 2 for the first retry, …"""
        if not body.strip():
            return MockResult(False, "MOCK_EMPTY_BODY", "모의 발송 실패: 본문이 비어 있습니다.")
        domain = recipient_email.rsplit("@", 1)[-1].lower()
        if domain == FAIL_DOMAIN:
            return MockResult(
                False, "MOCK_RECIPIENT_REJECTED", "모의 발송 실패: 수신 주소가 거부되었습니다."
            )
        if domain == RETRY_DOMAIN and attempt_no == 1:
            return MockResult(
                False,
                "MOCK_TEMPORARY_FAILURE",
                "모의 발송 실패: 일시적인 발송 오류입니다. 잠시 후 재시도하세요.",
            )
        return MockResult(True)
