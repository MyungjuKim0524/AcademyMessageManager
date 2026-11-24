# API 명세

> **자동 생성 문서**: `backend/scripts/generate_openapi.py`가 FastAPI 앱에서 만든다. 직접 고치지 말고, API를 바꾼 뒤 스크립트를 다시 실행한다.

- 전체 명세: [openapi.json](openapi.json) (OpenAPI 3.1.0, API 버전 2.0.0, 엔드포인트 82개)
- 보기: [Swagger Editor](https://editor.swagger.io/)에 `openapi.json`을 불러오거나, 로컬에서 `scripts/start-fastapi.ps1`로 실행한 뒤 http://127.0.0.1:8000/docs 를 연다.
- 배포 서버는 `/docs`·`/openapi.json`을 공개하지 않는다(`ACADEMY_API_DOCS` 기본값 0).
- 인증: 로그인하면 서버 세션 쿠키가 발급된다. 근거와 보안 점검은 [ADR 0001 세션 인증](../decisions/0001-local-session-authentication.md), [Phase 11-2 보안 감사](../reviews/phase11_2_security_audit.md)에 있다.
- 오류 응답 형식: `{"code": "...", "message": "...", "fields": [...]}`

**권한 열**: `공개`는 로그인 불필요, `직원`은 관리자·선생님·조교, `관리자`는 관리자만. 반 데이터를 다루는 `직원` 엔드포인트에서 선생님·조교는 **배정된 반만** 다룰 수 있다(서비스 계층에서 판정). **CSRF 열**: `필요`이면 `X-CSRF-Token` 헤더를 보내야 한다.

**용도 열**: 비어 있으면 웹 화면이 쓰는 API다. `레거시`는 Java 시절 기능으로 정리 대상이다(OpenAPI `deprecated`, Swagger UI에 취소선). `운영 점검`은 상태 확인·배포 점검용이다. `화면 미사용`은 현재 API지만 웹 화면이 호출하지 않는다.

화면이 쓰지 않는 API:

- `GET /api/auth/client-address`: 운영 점검
- `GET /api/message-operations/classrooms/{classroom_id}`: 화면 미사용
- `GET /api/message-operations/obligations/{lesson_id}/{enrollment_id}`: 화면 미사용
- `GET /api/health`: 운영 점검
- `POST /api/messages/preview`: 레거시

## 인증·계정

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `POST` | `/api/auth/login` | 공개 |  |  | 로그인 |
| `POST` | `/api/auth/password` | 직원 | 필요 |  | 내 비밀번호 변경 |
| `POST` | `/api/auth/password-reset` | 공개 |  |  | 재설정 코드로 비밀번호 재설정 |
| `POST` | `/api/auth/logout` | 직원 | 필요 |  | 로그아웃 |
| `GET` | `/api/auth/client-address` | 관리자 |  | **운영 점검** | 로그인 제한 기준 주소 진단(배포 점검용, 기본 꺼짐) |
| `GET` | `/api/auth/me` | 직원 |  |  | 현재 로그인한 직원 정보 |

## 학생·반·직원 관리

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/classrooms` | 직원 |  |  | 반 목록(선생님·조교는 담당 반만) |
| `GET` | `/api/staff` | 관리자 |  |  | 직원 목록 |
| `POST` | `/api/staff` | 관리자 | 필요 |  | 직원 계정 생성 |
| `GET` | `/api/staff/{staff_id}` | 관리자 |  |  | 직원 상세 |
| `PATCH` | `/api/staff/{staff_id}` | 관리자 | 필요 |  | 직원 정보 수정 |
| `PATCH` | `/api/staff/{staff_id}/status` | 관리자 | 필요 |  | 직원 활성·비활성 전환 |
| `POST` | `/api/staff/{staff_id}/password-reset-code` | 관리자 | 필요 |  | 비밀번호 재설정 코드 발급 |
| `DELETE` | `/api/staff/{staff_id}` | 관리자 | 필요 |  | 직원 삭제(기록이 있으면 삭제 상태로 표시) |
| `GET` | `/api/staff/{staff_id}/assignments` | 직원 |  |  | 직원의 담당 반 목록 |
| `GET` | `/api/classrooms/{classroom_id}/staff` | 관리자 |  |  | 반의 담당 직원 목록 |
| `DELETE` | `/api/classrooms/{classroom_id}/assignments/{assignment_id}` | 관리자 | 필요 |  | 담당 반 배정 해제 |
| `POST` | `/api/classrooms` | 관리자 | 필요 |  | 반 등록 |
| `PATCH` | `/api/classrooms/{classroom_id}` | 관리자 | 필요 |  | 반 이름 변경·종료·재개 |
| `DELETE` | `/api/classrooms/{classroom_id}` | 관리자 | 필요 |  | 반 삭제(기록 없는 반만) |
| `GET` | `/api/students` | 관리자 |  |  | 전체 학생 목록 |
| `GET` | `/api/students/{student_id}/contact` | 관리자 |  |  | 보호자 연락처 조회 |
| `PATCH` | `/api/students/{student_id}/contact` | 관리자 | 필요 |  | 보호자 연락처 수정 |
| `POST` | `/api/students` | 관리자 | 필요 |  | 학생 등록 |
| `POST` | `/api/classrooms/{classroom_id}/enrollments` | 관리자 | 필요 |  | 수강 등록 |
| `POST` | `/api/classrooms/{classroom_id}/assignments` | 관리자 | 필요 |  | 담당 반 배정 |
| `GET` | `/api/classrooms/{classroom_id}/students` | 직원 |  |  | 반별 학생 목록 |

## 수업·출결·성적

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/classrooms/{classroom_id}/lessons` | 직원 |  |  | 수업 회차 목록 |
| `POST` | `/api/classrooms/{classroom_id}/lessons` | 직원 | 필요 |  | 수업 회차 생성 |
| `POST` | `/api/classrooms/{classroom_id}/lessons/today` | 직원 | 필요 |  | 오늘 수업 시작(없으면 생성) |
| `GET` | `/api/lessons/{lesson_id}` | 직원 |  |  | 수업 회차 상세 |
| `PATCH` | `/api/lessons/{lesson_id}` | 직원 | 필요 |  | 수업 회차 수정 |
| `GET` | `/api/lessons/{lesson_id}/attendance` | 직원 |  |  | 출결 조회 |
| `PUT` | `/api/lessons/{lesson_id}/attendance` | 직원 | 필요 |  | 출결 저장 |
| `GET` | `/api/classrooms/{classroom_id}/assessments` | 직원 |  |  | 평가 목록 |
| `POST` | `/api/classrooms/{classroom_id}/assessments` | 직원 | 필요 |  | 평가 생성 |
| `GET` | `/api/assessments/{assessment_id}` | 직원 |  |  | 평가 상세 |
| `PATCH` | `/api/assessments/{assessment_id}` | 직원 | 필요 |  | 평가 수정 |
| `GET` | `/api/assessments/{assessment_id}/grades` | 직원 |  |  | 점수 조회 |
| `PUT` | `/api/assessments/{assessment_id}/grades` | 직원 | 필요 |  | 점수 저장 |
| `GET` | `/api/classrooms/{classroom_id}/progress` | 직원 |  |  | 진도표(기간별 출결·과제·점수) |
| `PUT` | `/api/lessons/{lesson_id}/records/{enrollment_id}` | 직원 | 필요 |  | 학생 한 명의 수업 기록 수정 |
| `GET` | `/api/classrooms/{classroom_id}/students/{student_id}/records` | 직원 |  |  | 학생별 수업·평가 기록 |
| `GET` | `/api/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses` | 직원 |  |  | 휴원 이력 |
| `POST` | `/api/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses` | 직원 | 필요 |  | 휴원 처리 |
| `POST` | `/api/classrooms/{classroom_id}/enrollments/{enrollment_id}/pauses/{pause_id}/resume` | 직원 | 필요 |  | 휴원 학생 복귀 |

## 성적 안내 메시지

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/notification-templates` | 직원 |  |  | 메시지 템플릿 목록 |
| `GET` | `/api/notification-templates/variables` | 직원 |  |  | 템플릿에 쓸 수 있는 변수 목록 |
| `POST` | `/api/notification-templates/validate` | 직원 |  |  | 템플릿 문법 검사 |
| `POST` | `/api/notification-templates` | 직원 | 필요 |  | 메시지 템플릿 생성 |
| `PATCH` | `/api/notification-templates/{template_id}` | 직원 | 필요 |  | 메시지 템플릿 수정 |
| `POST` | `/api/lessons/{lesson_id}/notifications/preview` | 직원 |  |  | 수업 메시지 초안 미리보기(저장 안 함) |
| `POST` | `/api/lessons/{lesson_id}/notifications` | 직원 | 필요 |  | 수업 메시지 초안 생성 |
| `GET` | `/api/notifications` | 직원 |  |  | 메시지 목록 |
| `GET` | `/api/notifications/{notification_id}` | 직원 |  |  | 메시지 상세 |
| `PATCH` | `/api/notifications/{notification_id}` | 직원 | 필요 |  | 메시지 내용 수정 |
| `POST` | `/api/notifications/{notification_id}/submit` | 직원 | 필요 |  | 검토 요청(초안 → 검토 대기) |
| `POST` | `/api/notifications/{notification_id}/approve` | 직원 | 필요 |  | 메시지 확정 |
| `POST` | `/api/notifications/{notification_id}/revoke` | 직원 | 필요 |  | 확정 취소(확정 → 초안) |
| `POST` | `/api/notifications/{notification_id}/cancel` | 직원 | 필요 |  | 메시지 취소(발송 안 함) |
| `GET` | `/api/lessons/{lesson_id}/notifications/batch` | 직원 |  |  | 반 단위 일괄 검토 화면 데이터 |
| `POST` | `/api/lessons/{lesson_id}/notifications/batch-approve` | 직원 | 필요 |  | 반 단위 일괄 확정 |
| `POST` | `/api/lessons/{lesson_id}/notifications/batch-mock-send` | 직원 | 필요 |  | 반 단위 일괄 모의 발송 |
| `POST` | `/api/notifications/{notification_id}/mock-send` | 직원 | 필요 |  | 모의 발송 |
| `POST` | `/api/notifications/{notification_id}/retry-mock-send` | 직원 | 필요 |  | 실패한 모의 발송 재시도 |

## 주간 엑셀 업로드

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `POST` | `/api/lesson-uploads/sheets` | 직원 |  |  | 엑셀 파일의 시트(시간대) 목록 |
| `POST` | `/api/lesson-uploads/preview` | 직원 |  |  | 업로드 미리보기(저장 안 함) |
| `POST` | `/api/lesson-uploads/confirm` | 직원 | 필요 |  | 업로드 확정·저장 |

## 메시지 처리 현황·일괄 처리

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/message-operations/summary` | 직원 |  |  | 메시지 처리 현황 합계·반별 건수 |
| `GET` | `/api/message-operations/todo` | 직원 |  |  | 대시보드 성적 안내 할 일(최근 3개월) |
| `GET` | `/api/message-operations/classrooms/{classroom_id}` | 직원 |  | **화면 미사용** | 반별 처리 현황 |
| `GET` | `/api/message-operations/obligations` | 직원 |  |  | 안내 대상 목록(학생·수업별 처리 상태) |
| `GET` | `/api/message-operations/obligations/{lesson_id}/{enrollment_id}` | 직원 |  | **화면 미사용** | 안내 대상 상세 |

## 출결·성적 분석

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/analytics/attendance` | 직원 |  |  | 출결 분석(입력 완료율·출석률) |
| `GET` | `/api/analytics/attendance/students/{student_id}` | 직원 |  |  | 학생별 출결 이력 |
| `GET` | `/api/analytics/grades` | 직원 |  |  | 성적 분석 |
| `GET` | `/api/analytics/grades/assessments/{assessment_id}` | 직원 |  |  | 평가별 성적 상세 |
| `GET` | `/api/analytics/grades/students/{student_id}` | 직원 |  |  | 학생별 성적 추이 |
| `GET` | `/api/analytics/watchlist` | 직원 |  |  | 관심 필요 학생 |
| `GET` | `/api/analytics/students/{student_id}/report` | 직원 |  |  | 학생 학습 리포트 |

## 상태 확인·이전 미리보기(레거시)

| 메서드 | 경로 | 권한 | CSRF | 용도 | 설명 |
|---|---|---|---|---|---|
| `GET` | `/api/health` | 공개 |  | **운영 점검** | 서버 상태 확인 |
| `POST` | `/api/messages/preview` | 직원 |  | **레거시** | 메시지 문구 미리보기(Java 시절 계약 호환) |

## 이전 기록

Java v1.x 로컬 HTTP 어댑터 시절의 문서다. 현재 API가 아니다.

- [openapi-java-v1-legacy.yaml](openapi-java-v1-legacy.yaml): API 계약
- [HTTP_API_SECURITY.md](HTTP_API_SECURITY.md): 보안 모델
