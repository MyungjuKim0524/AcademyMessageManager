# Phase 9.5 개선 전 진단 (Stage 1)

작성일: 2026-11-20 · 진행: `docs/phase9-5-progress.md` · 최종: `docs/phase9-5-ux-architecture-improvement.md`

## 0. 출발점 확인
- Phase 9 구현 확인: `app/modules/message_operations/*`, `POST /api/notifications/{id}/retry-mock-send`, `features/message-operations/*` 존재. 직전 자동 테스트: pytest 109, Java 48, Vitest 54 PASS(2026-11-20, `docs/phase9-message-operations.md` 15절). DB head `009_phase81_lesson_upload`(개발·테스트).
- 실제 업무 흐름의 엑셀 반영은 **성적 안내 > 엑셀 업로드**(`UploadTab.tsx`, `/api/lesson-uploads/preview|confirm`)입니다. 구 CSV/XLSX 가져오기(`/imports/preview`, `ImportPreviewPage.tsx`)는 Phase 8.1에서 메뉴에서 숨겼고 Java 호환을 위해 라우트·API만 유지 중입니다.
- AI Secretary Pro: `D:\AI-Secretary-Pro-20260708T100428Z-3-001\AI-Secretary-Pro`에 실제 존재(Streamlit + LangChain 단일 앱, 파이썬 22개 파일). 비교는 §3.

## 1. 업무 흐름 평가 (코드 기준, 실사용 측정 아님)

| 흐름 | 현재 동작(근거) | 문제 |
|---|---|---|
| A 엑셀 반영 | `UploadTab.tsx`: 수업일·파일 → 미리보기(반 블록 표, 행 색상·상태) → 미등록 학생 질문 → 확정 Popconfirm → 결과 카드·빨간 팝업 | 단계 구분 없이 한 화면에 누적. 검증 결과 **요약(정상/미등록/오류/건너뜀/불일치 수)이 없어** 블록마다 표를 훑어야 함. 확정 전에 "저장될 범위"(저장 행·신규 등록·복귀·제외·초안 대상 반) 요약 없음. 파일명·크기 표시 없음. 서버 오류 시 반영 여부 안내 없음 |
| B 학사 기록 | `ClassworkPage.tsx`: 반 선택 → 출결(기본)/학습 현황/수업/평가 관리 탭, "오늘 수업 시작" | Phase 8.1에서 정비됨. 큰 문제 없음 |
| C 메시지 | `ReviewTab.tsx`: 목록 → **Drawer(620px)** 에 본문·시도·이력 | 생성 근거(출결·과제·점수·주제)가 화면에 없어 본문이 맞는지 **다른 화면(학습 현황)과 대조해야 함**. 다음 학생으로 가려면 Drawer를 닫고 목록에서 다시 클릭. 모의 발송 확인 창에 학생·수신 주소 없음 |
| D 운영 문제 해결 | `MessageOperationsPage.tsx` → 성적 안내로 `?classroom&tab&lesson&notification` 이동 | 작동. 단 성적 안내는 주소 파라미터를 **처음 열 때 한 번만** 읽어(`linkParams`), 같은 화면에 있는 상태에서 메뉴로 다른 탭 주소로 가면 반영되지 않음 |

## 2. 개선 후보와 결정

| # | 영역 | 실제 문제 | 근거 파일 | 개선안 | 예상 영향 | 우선 | 결정 |
|---|---|---|---|---|---|---|---|
| 1 | 레이아웃 | 콘텐츠 영역에 여백이 없어 본문이 사이드바 경계에 붙음 | `App.css` `.app-content { min-width:0 }`(padding 없음) | 콘텐츠 패딩·최대 폭 지정 | 전 화면 | P0 | IMPLEMENT |
| 2 | 제목 | 화면마다 제목 방식이 다름: 구 화면 3개는 `hero`+영문 eyebrow+h1(최대 3.25rem), 나머지 `Title level 2`, 설명·액션 위치 제각각 | `ImportHistoryPage`, `ImportPreviewPage`, `MessagePreviewPage`, 각 Page의 `Typography.Title level={2}` | 공통 `PageHeader`(제목·설명·액션) 1개로 통일, 제목 축소 | 9개 화면 | P0 | IMPLEMENT |
| 3 | 메뉴 | 기능 나열식 평면 메뉴, 미구현 "발송 이력 · 준비 중" 노출, 성적 안내 하위 작업(업로드·검토·템플릿)이 메뉴에서 안 보임 | `layout/AppLayout.tsx` | 업무 그룹(홈/학사 운영/성적 안내/데이터·시스템 관리) + 성적 안내 탭 바로가기, 미구현 메뉴 제거 | 내비게이션 | P0 | IMPLEMENT |
| 4 | 탭 주소 | 성적 안내 주소 파라미터를 최초 1회만 읽음 → 메뉴 바로가기와 충돌 | `NotificationsPage.tsx` `useState(linkParams)` | 라우트에서 검색어가 바뀌면 화면을 다시 마운트(`key`) | 성적 안내 | P0 | IMPLEMENT |
| 5 | 대시보드 | 홈 화면 없음(`/` → `/notifications` 리다이렉트) | `app/router.tsx` | 기존 API만으로 계산 가능한 항목: 오늘 수업·출결 미입력 학생 수(`/progress`), 메시지 처리 현황(`/message-operations/summary`), 관리자: 최근 CSV 가져오기(`/api/imports`). 빠른 작업 링크 | 신규 화면 1 | P0 | IMPLEMENT |
| 6 | 대시보드 | 엑셀 업로드(수업 기록) 이력 API 없음(감사 로그에만 기록) | `lesson_upload/service.py` `_audit` | 새 API·전역 활동 로그 필요 | — | — | DEFER (새 API 필요, 지시서 6.4 "새 전역 활동 로그 금지") |
| 7 | 엑셀 업로드 | §1-A 문제 | `notifications/UploadTab.tsx` | 4단계(파일→검증→변경 확인→완료) UI, 검증 요약·오류 목록, 저장 범위 요약, 파일 정보, 실패 시 반영 여부 안내. **API·트랜잭션 변경 없음** | 업로드 화면 | P0 | IMPLEMENT |
| 8 | 구 CSV/XLSX 가져오기 | 메뉴에서 숨겨진 Java 호환 화면 | `import-preview/*` | 단계형 개편 | 낮음 | — | REJECT (업무 흐름 밖, 계약 보존 우선. 제목 통일(#2)만 적용) |
| 9 | 메시지 검토 | §1-C 문제 | `notifications/ReviewTab.tsx` | 좌: 목록 / 우: **생성 근거(출결·과제·점수·주제) + 본문** 분할 패널, "다음 학생", 최종 확인 창에 학생·수신 주소·모의 발송 표시. 근거는 기존 `GET /classrooms/{id}/progress`(그날 1회) 재사용, 요청 순번으로 다른 학생 데이터 표시 방지 | 검토 화면 | P0 | IMPLEMENT |
| 10 | 일괄 확정·발송 | 일괄 API 없음, 메시지별 원본 변경 검사·부분 실패 정책 미정 | `notifications/service.py` `approve` | 일괄 승인 | — | — | DEFER (지시서 8.4 조건 미충족) |
| 11 | 신규 메시지 상태 | REVIEWED 등 | — | — | — | — | REJECT (상태 머신 보존) |
| 12 | 학생·반·직원 | 8.1에서 전체 학생 목록·검색·탭, 이름 검색 선택, 직원 탭 구성 완료 | `LearningOpsPage.tsx`, `StaffManagementPage.tsx` | 제목 통일(#2)만 | — | P1 | SIMPLIFY(#2로 충분) |
| 13 | 출결·성적 | 8.1에서 출결 기본값·저장 안 됨 표시·행별 오류·학습 현황 칸 수정·확인 팝업 완료 | `classwork/*` | 추가 변경 없음 | — | P1 | REJECT (이미 충족, 변경 위험만 증가) |
| 14 | 데이터 출처 표시 | 출결·성적이 엑셀/수동 중 어디서 왔는지 컬럼 없음(감사 로그 이벤트만 다름) | `tables.py` `LessonResult` | 출처 배지 | — | — | REJECT (추정 표시 금지, 새 컬럼 필요) |
| 15 | 날짜 유틸 중복 | `todayLocal`/`today`가 3곳, `shiftDay` 2곳에 중복 | `classwork/common.tsx`, `staff/StaffManagementPage.tsx`, `learningops/LearningOpsPage.tsx`, `classwork/ProgressTab.tsx`, `message-operations/MessageOperationsPage.tsx` | `shared/date.ts` 1곳 | 작음 | P1 | SIMPLIFY |
| 16 | 상태 표시 | 상태 태그가 영역별 맵(알림·운영·출결·수강·직원)에 있으나 **모두 문구 포함**(색상 단독 아님), 의미가 서로 달라 하나로 합칠 대상 아님 | 각 `common.tsx`/`status.ts` | 변경 없음 | — | — | REJECT (이미 충족) |

## 3. 아키텍처 진단 (요약 — 상세는 최종 보고서 10절)

| 항목 | 확인 결과 | 결정 |
|---|---|---|
| Router 책임 | 라우터는 의존성(권한·CSRF)·입력 파싱·응답 조립만. 업무 규칙은 서비스에 있음(`lesson_upload/router.py`의 결정 JSON 파싱도 입력 검증 수준) | 변경 없음 |
| 권한 검증 | 반 접근 규칙의 실체는 `LearningOpsRepository.can_access_classroom` **한 곳**. 각 서비스(`academics`, `notifications`, `message_operations`, `lesson_upload`)는 이를 감싸는 `_require_classroom`을 각각 두어 404/403 문구가 반복됨 | DEFER (규칙은 단일, 중복은 얇은 래퍼. 통합 시 4개 모듈 동시 수정 위험 > 이익) |
| 트랜잭션 | 출결·성적·칸 수정·메시지 전이·모의 발송·재시도: 상태+감사(+원장)를 한 커밋. 엑셀 업로드 확정: 데이터+감사 한 트랜잭션, **초안 생성은 커밋 후 별도 트랜잭션**(의도된 설계: 초안 실패가 데이터 저장을 되돌리지 않음, 결과에 사유 표시) | 변경 없음(문서화) |
| 상태 전이 | 메시지 상태 변경은 `NotificationService`에만 존재(행 잠금+버전), 업로드도 이 서비스를 호출. 확정 본문은 `EDITABLE` 외 수정 불가 | 변경 없음 |
| 테스트 가능성 | `MockSender`가 서비스 생성자에서 직접 생성(주입 아님) — 다만 결정적 도메인 규칙(`mock-fail`/`mock-retry`)으로 테스트 가능 | 변경 없음 |
| 프론트 중복 | 날짜 함수 중복(#15) | SIMPLIFY |

AI Secretary Pro 비교:

| 패턴 | 현재 문제 | 도입 효과 | 변경 위험 | 채택 |
|---|---|---|---|---|
| `pydantic-settings` 타입 설정(`config/settings.py`) | 우리 `app/config.py`는 `os.getenv` 수동 파싱 dataclass — 동작 문제 없음, 테스트가 환경변수로 제어 | 형식 검증 자동화 | 의존성 추가·전 설정 경로 변경 | 아니오 (실제 결함 없음) |
| 모듈 import 시점 싱글턴(`assistant = Assistant()`, `settings = Settings()`) | 해당 없음 | — | 테스트 격리 악화 | 아니오 (우리는 요청 단위 서비스 생성이 더 나음) |
| 도구 목록 레지스트리(`tools/__init__.py`) | 해당 없음 | — | — | 아니오 |
| 오류 처리 | AI Secretary Pro에는 오류 처리 계층 없음; 우리는 `CompatibilityError` 공통 형식 | — | — | 해당 없음 |
결론: 채택할 패턴 없음.

## 4. 확정 범위
P0: #1 #2 #3 #4 #5 #7 #9 · P1: #15 · 나머지 DEFER/REJECT(근거 위 표). **DB·API 계약 변경 없음** 예정(신규 백엔드 API 없음).
