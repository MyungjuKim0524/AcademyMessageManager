# Phase 9.5 — 업무 중심 UI/UX 개선 + 아키텍처 품질 점검 최종 보고서

작성일: 2026-11-20 · 진단: `docs/archive/phases/phase9-5-assessment.md` · 진행: `docs/archive/phases/phase9-5-progress.md` · 수동 점검: `docs/archive/phases/phase9-5-manual-ui-checklist.md`

## 1. 목표 및 범위
기존 기능을 보존하면서 업무 흐름을 연결하고(엑셀 반영 → 메시지 검토 → 처리 현황), 화면 일관성을 맞추고, 아키텍처를 근거 기반으로 점검했습니다. **백엔드 코드·API·DB 변경 없음**(프론트엔드만 변경).

## 2. 개선 전 진단 (요약)
진단 문서 표의 16개 후보 중 IMPLEMENT 7(#1 여백, #2 제목, #3 메뉴, #4 탭 주소, #5 대시보드, #7 업로드 단계형, #9 검토 분할), SIMPLIFY 2(#12 관리 화면은 제목 통일로 충분, #15 날짜 유틸), DEFER 2(#6 업로드 이력 API, #10 일괄 확정), REJECT 5(#8 구 CSV 화면 개편, #11 신규 메시지 상태, #13 출결·성적 추가 변경, #14 데이터 출처 배지, #16 상태 태그 통합). 근거는 진단 문서 2절.

## 3. 개선 후 메뉴 구조 (`layout/AppLayout.tsx`)
| 그룹 | 메뉴 → 경로 | 권한 |
|---|---|---|
| 홈 | 대시보드 → `/` | 전 직원 |
| 학사 운영 | 학생·반 관리(선생님·조교: 담당 반 학생) → `/students` · 수업·출결·성적 → `/classes` | 전 직원(서버가 담당 반으로 제한) |
| 성적 안내 | 엑셀 업로드 → `/notifications?tab=upload` · 메시지 검토·발송 → `?tab=review` · 누락·예외 생성 → `?tab=compose` · 메시지 처리 현황 → `/message-operations` · 템플릿 관리 → `?tab=templates` | 전 직원 |
| 데이터·시스템 관리 | 가져오기 이력 → `/imports/history` · 직원·담당 반 배정 → `/staff` | 관리자 |
- 미구현 "발송 이력 · 준비 중" 메뉴 제거(라우트는 유지).
- 수업·출결·성적을 메뉴 4개로 쪼개지 않은 이유: 한 화면의 탭이 **같은 반 선택을 공유**하는 구조라 분리하면 반을 다시 골라야 함(지시서 "서로 다른 목적의 화면을 무리하게 합치지 말 것"의 반대 방향 위험).
- 로그인 직후·404 이동 경로: `/notifications` → **`/`(대시보드)**.
- 성적 안내 주소 연결 결함 수정: 라우트가 검색어(`?tab=…`)별로 화면을 새로 열도록 `key` 지정(`app/router.tsx`) — 이전에는 처음 열 때만 주소를 읽어 메뉴 바로가기가 무시됨.

## 4. 공통 디자인 시스템
- `shared/ui/PageHeader.tsx`: 제목(h3, 22px)·한 줄 설명·액션 위치 통일 — 9개 화면 적용(구 화면 3개의 영문 eyebrow·최대 3.25rem 제목 제거).
- `App.css`: 콘텐츠 여백(24/28px, 모바일 16/12px)·최대 폭 1440px, 밝은 회색 바탕(`#f4f6fa`, antd `colorBgLayout`), 카드 테두리·그림자 축소, 모서리 8px. 사이드바 232px, 좁은 화면(lg 미만)에서 접힘(antd 기본 동작 유지).
- 상태 표시: 기존 태그가 모두 아이콘/문구를 함께 표시함을 확인 — 의미가 다른 상태 맵(메시지·운영·출결·수강·직원)을 억지로 합치지 않음. 백엔드 상태 머신 변경 없음.
- `shared/date.ts`: `todayLocal`/`shiftDay` 단일화(3곳·2곳 중복 제거).
- 새 라이브러리 없음(antd·React Query 기존 그대로).

## 5. 대시보드 (`features/dashboard/DashboardPage.tsx`, 신규 API 없음)
| 영역 | 데이터 출처 | 정의 |
|---|---|---|
| 오늘 수업 | `GET /api/classrooms`(담당 반) + 반마다 `GET /classrooms/{id}/progress?date_from=오늘&date_to=오늘` | 오늘 날짜 수업, 출결 = **수업일 기준 수강 학생 중 기록 수**(휴원·기간 밖 제외). 기록 < 대상이면 '출결 입력 필요', 취소 수업 제외. 수업 없는 반 표시 |
| 성적 안내 처리 | `GET /api/message-operations/summary`(최근 14일) | 미생성·검토 대기·발송 대기·실패, 대상·완료·완료율(대상 0건이면 "대상 없음") — 모의 발송 기준 명시 |
| 최근 가져오기(관리자) | `GET /api/imports?page=0&size=5` | CSV/XLSX 가져오기 5건. **주간 엑셀 업로드 기록은 조회 API가 없어 표시하지 않음**(문구로 명시) |
| 빠른 작업 | — | 출결 입력, 엑셀 업로드, 메시지 검토·발송, 발송 실패 확인(`?status=FAILED`로 필터 선택) |
각 영역은 따로 불러오고, 실패하면 0이 아니라 오류와 "다시 시도"를 표시. 반 개수만큼 `progress` 요청이 생김(담당 반 규모에서 허용 — 반이 매우 많아지면 전용 집계 API 검토: 21절).

## 6. Excel Import 업무 흐름 (`features/notifications/UploadTab.tsx`)
API(`/api/lesson-uploads/preview|confirm`)·서버 검증·트랜잭션 **변경 없음**. 4단계 표시(Steps) + 단계별 카드를 한 화면에 순서대로 유지(이전 단계 정보가 사라지지 않음):
1. **파일 선택**: 수업일·.xlsx, 파일명·크기·수업일 표시, "미리보기는 저장하지 않음"
2. **데이터 검증**: 학생 행·정상·미등록·오류·출결 다름·건너뜀 수(서버 미리보기 결과로 계산), 차단 오류 목록, **행 오류 목록 "[시트] 반 · N행 이름: 사유"**, 반 블록별 행 표·미등록 학생 결정(기존)
3. **변경 확인**: 저장할 학생 행·신규 등록·복귀·제외 수(결정에 따라 즉시 갱신), 대상 반·수업일 1교시, 저장 범위 설명, **한 트랜잭션(전부 또는 전무)** 안내, 명시적 확정(확인 창) — 진행 중 중복 클릭 차단
4. **처리 완료**: 결과·초안 미생성 빨간 팝업(기존), 검토·발송 / 메시지 처리 현황 / 다른 파일 올리기
- 저장 실패: 서버가 답한 오류면 "하나도 반영되지 않음", **응답을 못 받았으면 "저장 여부를 알 수 없음 → 같은 파일로 다시 미리보기(재업로드는 중복 없이 갱신)"** 안내.
- 구 CSV/XLSX 가져오기 화면은 제목 통일만(REJECT #8).

## 7. 메시지 생성·검토 UX (`features/notifications/ReviewTab.tsx`)
- **분할 화면**: 왼쪽 목록(필터·상태), 오른쪽 패널 = **생성 근거**(반·수업·주제·템플릿·출결·예습/주간·시험 점수) | **메시지**(상태·수신 주소·확정자·원본 변경 경고·본문·조치). 좁은 화면에서는 세로 배치.
- 근거 데이터: 기존 `GET /classrooms/{id}/progress`를 수업일당 1회 불러와 캐시(목록 새로고침 시 비움), 요청 번호로 늦게 온 응답이 다른 학생 화면에 표시되지 않게 함. "현재 저장된 값"임을 명시하고, 생성 후 변경은 기존 `source_changed` 경고로 표시.
- **연속 검토**: "n / 전체", 이전·다음, **"확정 후 다음 학생"**(확정 성공 시 다음 메시지를 바로 엶).
- 최종 확인: 모의 발송 확인 창에 "학생 · 수신 주소 · 1건" + 모의 발송 문구.
- 상태 머신·API 변경 없음. 일괄 확정은 DEFER(#10). 메시지 처리 현황 → 검토 화면 직접 연결(Phase 9) 유지.

## 8. 학생·반·직원 관리
Phase 8.1에서 목록 우선·검색·탭·이름 검색 선택·연락처 수정이 이미 정비되어 있어 **제목·설명 통일만** 적용(#12). 등록 폼을 일괄 모달화하지 않음(지시서 9.1).

## 9. 출결·성적 입력 UX
Phase 8.1의 출결 기본 탭·"저장 안 됨" 표시·미입력≠결석·행별 오류·학습 현황 칸 수정·변경 확인 팝업으로 지시서 9.2 항목이 이미 충족됨 → 추가 변경 없음(#13, 회귀 위험만 증가). 데이터 출처 표시는 DB에 출처 컬럼이 없어 추정 금지(#14).

## 10. 아키텍처 진단 결과
| 항목 | 확인 내용(근거) | 판정 |
|---|---|---|
| 책임 분리 | 라우터는 의존성·입력 파싱·응답 조립만, 업무 규칙은 서비스, 저장소는 조회·잠금만. 메시지 상태 변경은 `NotificationService` 한 곳(업로드도 이 서비스를 호출) | 문제 없음 |
| 권한 검증 | 반 접근 규칙은 `LearningOpsRepository.can_access_classroom` **단일 구현**. 서비스 4곳(`academics`, `notifications`, `message_operations`, `lesson_upload`)에 얇은 래퍼(`_require_classroom`)가 있어 404/403 문구가 반복. 배정 해제·비활성 차단은 각 모듈 테스트로 확인됨 | 중복은 있으나 규칙 단일 → **DEFER** |
| 트랜잭션 | 출결·성적·칸 수정·메시지 전이·모의 발송·재시도: 상태+감사(+원장) 한 커밋, 실패 시 롤백. 엑셀 확정: 데이터+감사 한 트랜잭션, **초안 생성은 커밋 후 별도**(의도: 초안 실패가 저장을 되돌리지 않음, 결과·팝업으로 사유 표시) | 문제 없음(설계 문서화) |
| 상태 전이 | 행 잠금+버전 비교, 확정 본문은 `EDITABLE`(초안·검토 대기)에서만 수정, 모의 발송 멱등 키 UNIQUE + 성공 부분 UNIQUE | 문제 없음 |
| 테스트 가능성 | `MockSender`를 서비스 생성자가 직접 만듦(주입 아님) — 결정적 규칙(`mock-fail`/`mock-retry` 도메인)으로 통합 테스트 가능, 실제 발송 구현이 생길 때 주입 구조 필요 | Phase 10 이후 과제로 기록 |
| 프론트 | 날짜 유틸 중복, 페이지 헤더 방식 혼재, 성적 안내 주소 1회 판독 결함 | 수정(4·3절) |

## 11. 실제 수행한 리팩터링
프론트엔드만: `shared/date.ts`(중복 제거), `shared/ui/PageHeader.tsx`(헤더 통일), 라우트 `key` 재마운트(주소 연결 결함). **백엔드 리팩터링 없음** — 위 점검에서 실제 결함이 확인되지 않았고, 권한 래퍼 통합은 4개 모듈 동시 수정 위험이 이익보다 큼.

## 12. AI Secretary Pro 비교 (소스 확인: `D:\AI-Secretary-Pro-…\AI-Secretary-Pro`, Streamlit+LangChain 단일 앱 22개 파일, 실행하지 않고 읽기만 함)
| 패턴 | 현재 문제 | 도입 효과 | 변경 위험 | 채택 |
|---|---|---|---|---|
| `pydantic-settings` 타입 설정 | `app/config.py`는 `os.getenv` 수동 파싱이나 결함 없음 | 설정 형식 검증 | 의존성 추가·전 설정 경로 변경 | 아니오 |
| import 시점 전역 싱글턴(`settings`, `assistant`, `memory`) | 해당 없음 | — | 테스트 격리 악화 | 아니오 |
| 도구 레지스트리(`tools/get_tools`) | 해당 없음 | — | — | 아니오 |
| 오류 처리 계층 | AI Secretary Pro에는 없음, 우리는 `CompatibilityError` 공통 형식 | — | — | 해당 없음 |
결론: 이식할 패턴 없음(코드 복사 없음).

## 13. 변경된 API·컴포넌트 목록
- API: **변경·추가 없음**.
- 신규: `shared/ui/PageHeader.tsx`, `shared/date.ts`, `features/dashboard/DashboardPage.tsx`(+test), `layout/AppLayout.test.tsx`.
- 변경: `App.css`, `index.css`, `app/AppProviders.tsx`(테마 토큰), `app/router.tsx`(대시보드·재마운트), `layout/AppLayout.tsx`(메뉴 그룹), `features/auth/LoginPage.tsx`·`pages/NotFoundPage.tsx`(홈 이동), `features/notifications/{UploadTab,ReviewTab,NotificationsPage}.tsx`, `features/message-operations/MessageOperationsPage.tsx`(헤더·`?status`), `features/{staff/StaffManagementPage,learningops/LearningOpsPage,classwork/ClassworkPage,classwork/common,classwork/ProgressTab,import-history/ImportHistoryPage,import-preview/ImportPreviewPage,message-preview/MessagePreviewPage}.tsx`(헤더·날짜 유틸), 테스트 `NotificationsPage.test.tsx`·`MessageOperationsPage.test.tsx`.

## 14. DB 변경 여부
없음. Migration 없음, head `009_phase81_lesson_upload`, `alembic check` 차이 없음. 개발 DB 쓰기 없음.

## 15. 테스트 명령과 실제 결과 (2026-11-20, 테스트 DB)
| 항목 | 명령 | 결과 |
|---|---|---|
| Ruff | `ruff check --no-cache app tests alembic scripts` | PASS |
| Alembic | `alembic current` / `alembic check` | 009 (head) / 차이 없음 |
| pytest(PostgreSQL 통합 포함) | `pytest -q` | **109 PASS / 0 fail / 0 skip** |
| Java | `mvn -q -DrunPostgresIntegration=true test` | **48 PASS / 0 fail / 0 skip** |
| React 변경 영역 | `vitest run src/layout src/features/dashboard src/features/notifications` | 16 PASS (신규: 메뉴 3, 대시보드 3, 근거 패널·연속 검토 1, 발송 확인 1, 업로드 미응답 1 + 업로드 단계 기대값 추가) |
| React 전체 | `npm test -- --run` | **64 PASS** (14 files; Phase 9 대비 +10: 메뉴 3, 대시보드 3, 처리 현황 필터 1, 검토 2, 업로드 1) |
| TypeScript | `tsc -b` | PASS |
| Lint | `npx oxlint src` (프로젝트 lint 도구, ESLint 미설치 — 신규 도입 안 함) | PASS |
| Build | `npm run build` (`tsc -b && vite build`) | PASS (기존과 같은 500kB 초과 청크 경고만) |

## 16. 회귀 테스트 결과
기존 테스트 삭제·기대값 완화 없음. 기존 업로드 테스트에는 단계 요약 기대값을 **추가**만 함. pytest·Java·Vitest 전체 통과(15절).

## 17. 브라우저 E2E 상태
**NOT RUN** — 이 환경에 브라우저 자동화 도구가 없음. 절차는 `docs/archive/phases/phase9-5-manual-ui-checklist.md`(18항목, 결과 칸 NOT RUN).

## 18. 보류·제외한 개선사항
| 항목 | 이유 | 권장 단계 |
|---|---|---|
| 주간 엑셀 업로드 이력 화면 | 조회 API 없음(감사 로그만), 새 API 필요 | Phase 10(업로드 이력 조회 API) |
| 일괄 확정·일괄 모의 발송 | 일괄 API 없음, 메시지별 원본 변경 검사·부분 실패 정책 미정 | Phase 10 이후 정책 정의 후 |
| 권한 래퍼(`_require_classroom`) 통합 | 규칙은 단일, 4개 모듈 동시 수정 위험 | 실제 규칙 변경이 생길 때 |
| 데이터 출처(엑셀/수동) 배지 | DB에 출처 컬럼 없음, 추정 금지 | 필요 시 스키마 설계부터 |
| 대시보드 전용 집계 API | 현재 반 수만큼 `progress` 요청 — 담당 반 규모에서 허용 | 반이 많아질 때 |
| 구 CSV/XLSX 화면 단계형 개편 | 업무 흐름 밖(Java 호환용) | 사용 재개 시 |
| 처리 기한(지연) 정책 | 학원 정책 미정(Phase 9 이월) | 정책 확정 시 |

## 19. 남아 있는 기술 부채
`MockSender` 직접 생성(실제 발송 도입 시 주입 구조 필요) · 서비스별 권한 래퍼 반복 · 성적 안내 화면이 주소를 `window.location`으로 읽음(라우터 상태로 옮기면 테스트에 Router 필요) · 번들 500kB 경고(라우트 lazy 분할은 되어 있으나 antd 공통 청크가 큼) · 구 화면(메시지 미리보기·CSV 가져오기)의 Java 호환 유지 부담.

## 20. Phase 10 착수 가능 여부
**착수 가능(조건부)** — 자동 검증(Python·PostgreSQL·Java·React·Build) 통과, DB·API 변경 없음. 조건: 수동 UI 체크리스트(브라우저) 미실행 상태이므로 Phase 10 시작 전 또는 초기에 체크리스트 1~18 확인 권장.
