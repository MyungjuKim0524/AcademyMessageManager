# Phase 6 학습 분석 설계안

> 설계 전용 문서다. 외부 BI SaaS, cloud warehouse, 유료 모니터링은 사용하지 않는다.

## 원칙

초기 대시보드는 기존 PostgreSQL의 인덱스가 적용된 집계 query와 FastAPI 읽기 API로 구현한다.
데이터 규모와 응답 시간을 측정하기 전에 별도 분석 DB, Redis, Elasticsearch를 도입하지 않는다.
학생 로그인과 학생용 dashboard는 범위가 아니다.

## 역할별 지표

| 역할 | 지표 | 접근 범위 |
|---|---|---|
| ADMIN | 재원·휴원·퇴원 수, 반별 출결률, Import 성공률, 미채점/상담 후속 건수 | 전체 학원 |
| TEACHER | 담당 반 출결, 과제 제출·채점률, 시험 추이, 진도 지연 | 유효 배정 반 |
| ASSISTANT | 담당 반 출결 누락, 과제 미제출, 운영 후속 목록 | 유효 배정 반 |

## 필요한 데이터

기존 `classroom`, `student`, `enrollment`, `lesson`, `lesson_result`, `import_job`을 보존한다.
후속 단계에서 과제, 학습 진도, 상담 기록 테이블을 additive migration으로 추가하고 모든 row에
업무 시각과 내부 식별자를 둔다. 집계 API는 이름·이메일 대신 id와 건수를 기본 반환하며 상세
drill-down에서만 권한을 다시 검사한다.

## 성능 및 정확성

- 먼저 `EXPLAIN (ANALYZE, BUFFERS)`로 실제 test fixture query를 측정한다.
- 날짜·classroom·status 조건의 복합 index는 측정 근거가 있을 때만 추가한다.
- 일별 집계가 느려질 때 PostgreSQL materialized view를 검토하고 갱신 시각을 응답에 표시한다.
- 지표 정의, 분모 0, 휴원/퇴원 포함 여부, timezone(Asia/Seoul)을 계약 테스트로 고정한다.
- 대시보드 API도 동일한 서버 세션과 담당 반 RBAC를 사용한다.

## 구현 순서

1. 지표 사전과 합성 fixture 확정
2. 관리자 Import/운영 집계 한 화면을 가장 작은 vertical slice로 구현
3. 교사 담당 반 출결 집계 추가
4. 과제·진도·상담 domain이 구현된 뒤 해당 지표 추가
5. 응답 시간 측정 후에만 materialized view 또는 batch 집계 검토

현재 단계에서는 설계만 완료했으며 분석 API나 dashboard를 구현 완료로 간주하지 않는다.
# 현재 분류: Phase 10 보류 설계

학습 분석은 Phase 10에서 PostgreSQL 집계와 React 차트로 검토한다. Phase 6A에는 구현하거나
분석용 인프라를 추가하지 않으며 아래 내용은 설계 이력으로 보존한다.

