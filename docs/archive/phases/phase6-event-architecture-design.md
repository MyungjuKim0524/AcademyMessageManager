# Phase 6 이벤트 아키텍처 설계안

> 설계 전용 문서다. Kafka broker, cloud, 유료 서비스는 설치·생성하지 않았다.

## 목표와 도입 조건

Import 확정, 출결 변경, 과제·성적 갱신, 상담 기록 생성처럼 업무 트랜잭션 이후 후속 처리가
필요한 사건을 느슨하게 연결한다. 현재 규모에서는 PostgreSQL 동기 처리만 유지하고, 소비자가
둘 이상 생기거나 재처리 가능한 비동기 알림이 실제로 필요해질 때만 Apache Kafka를 로컬 Docker
Compose로 도입한다.

## 권장 이벤트

| 이벤트 | 생산 시점 | 예상 소비자 | 개인정보 원칙 |
|---|---|---|---|
| `import.confirmed.v1` | Import transaction commit | 운영 통계, 알림 준비 | import id와 건수만 |
| `attendance.changed.v1` | 출결 변경 commit | 결석 후속 업무 | student id, classroom id만 |
| `assignment.graded.v1` | 과제 채점 commit | 진도 집계 | 점수 원문 최소화 |
| `test-score.recorded.v1` | 성적 저장 commit | 분석 집계 | 식별자는 내부 id 사용 |
| `counseling.recorded.v1` | 상담 기록 생성 commit | 감사/후속 일정 | 상담 본문 전송 금지 |

## 전달 보장

업무 테이블과 `outbox_event`를 같은 PostgreSQL transaction에서 기록하는 Transactional Outbox를
사용한다. 로컬 publisher가 미발행 행을 짧게 잠그고 Kafka에 발행한 뒤 상태를 갱신한다. 이벤트는
`eventId`, `eventType`, `occurredAt`, `aggregateType`, `aggregateId`, `schemaVersion`, `payload`를
가진다. 소비자는 `eventId` UNIQUE inbox로 중복을 무해하게 처리한다. 순서가 필요한 이벤트는
aggregate id를 partition key로 사용한다.

## 보안·운영 원칙

- 메시지 본문, 이메일, 전화번호, 상담 원문을 event payload에 넣지 않는다.
- broker는 로컬 loopback/Docker network에만 노출하고 기본 외부 공개를 금지한다.
- 실패 이벤트는 자동 무한 재시도하지 않고 제한된 backoff 후 DLQ로 보낸다.
- schema 호환성 테스트와 lag, DLQ 수, outbox 적체량을 로컬 오픈소스 도구 또는 SQL로 확인한다.
- 실제 이메일·SMS 소비자는 Mock adapter만 구현한다.

## 단계

1. 이벤트 목록과 JSON Schema fixture 작성
2. PostgreSQL outbox/inbox Alembic migration 및 rollback 문서화
3. Kafka 없이 publisher port와 in-memory fake로 단위 테스트
4. 무료 Apache Kafka 단일 노드 로컬 Compose와 통합 테스트
5. Import Confirm 한 흐름만 연결한 뒤 장애·중복·재처리 검증

현재 단계에서는 1의 설계까지만 완료했다. Kafka 의존성과 컨테이너는 추가하지 않았다.
# 현재 분류: 보류된 설계

이 문서의 이벤트/Kafka 방향은 현재 MVP 구현 계획이 아니다. 현 개발 방향은 PostgreSQL을
트랜잭션 경계로 사용하는 FastAPI 모듈형 모놀리스이며 Phase 6A~11 완료 후 필요성을 다시
평가한다. 기존 설계 근거 보존을 위해 본문은 삭제하지 않는다.

