# Phase 9.6 — UI/UX 구조 개선 및 업무 동선 최적화: Phase 0 분석·계획

작성일: 2026-11-20 · 선행: `docs/archive/phases/phase9-5-ux-architecture-improvement.md`(같은 날 완료된 1차 UX 개선)

## 0. 작업 환경 사실
- **Git 미설치·미초기화** → 변경 전 `frontend/src` 전체를 스크래치패드(`D:\Temp\…\scratchpad\backup-src-before`)에 백업. 원격 push·배포 없음.
- 범위: **프론트엔드만**. 백엔드·API·DB·마이그레이션 변경 없음(필요 항목 발견 시 승인 대기로 분리).
- D 드라이브 정책: 테스트는 `scripts/use-d-drive-dev-env.ps1`을 dot-source 후 실행(캐시 `.dev-data`).

## 1. 현행 구조 (코드 기준)
| 영역 | 경로 / 파일 | 비고 |
|---|---|---|
| 라우팅 | `app/router.tsx` | `/notifications`, `/message-operations`는 `key={location.search}`로 검색어가 바뀌면 재마운트 |
| 사이드바 | `layout/AppLayout.tsx` | 성적 안내 탭 4개를 `?tab=` 바로가기로 중복 제공(9.5에서 의도적으로 추가) |
| 반 선택 | `ClassworkPage`, `NotificationsPage`, `LearningOpsPage`, `MessageOperationsPage` | **각 화면이 독립 state, 항상 첫 반으로 시작**. `NotificationsPage`만 `?classroom=` 읽음(쓰기 없음) |
| 출결 | `classwork/AttendanceTab.tsx` | 미입력 학생은 화면에서만 '출석' 미리 선택 → "저장된 기록"(DB) ≠ "선택값"(편집 중) |
| 평가 관리 | `classwork/GradesTab.tsx` | 등록 폼이 lg 9/24 고정 → 목록 15/24 |
| 템플릿 | `notifications/TemplatesTab.tsx` | 목록 lg 15/24 + 변수 패널 9/24 상시 노출 |
| 엑셀 업로드 | `notifications/UploadTab.tsx` | preview / confirm API 분리(서버 재검증·단일 트랜잭션), 4단계 카드 |
| 누락·예외 생성 | `notifications/ComposeTab.tsx` | 학생별 **본문 전체를 표 셀에 출력** |
| 검토·발송 | `notifications/ReviewTab.tsx` | 9.5에서 목록|상세 분할, 연속 검토 완료 |
| 처리 현황 | `message-operations/MessageOperationsPage.tsx` | 통계 카드 7개, 반별 표, 반별 목록 + 상태 Select, 행별 조치 버튼 |
| 대시보드 | `dashboard/DashboardPage.tsx` | 오늘 수업·메시지 요약·빠른 작업 |

## 2. 가설 검증 결과
| 가설 | 결과 | 근거 |
|---|---|---|
| 사이드바와 탭이 중복 기능 제공 | **예(부분)** — 성적 안내 4개 탭 = 사이드바 4개 항목. 둘 다 유용(사이드바=직접 진입·북마크, 탭=같은 반 맥락 전환)하므로 **제거하지 않음**. 단 탭 클릭 시 URL이 안 바뀌어 **사이드바 강조가 실제 탭과 어긋남**, 사이드바 클릭 시 **반이 첫 반으로 초기화** | `NotificationsPage` 탭 state만 변경, 재마운트 시 `items[0]` |
| 출결 "저장된 기록"과 선택값의 의미 차이 | **다름** — 미입력 학생은 DB 미입력인데 선택값은 '출석'. 저장된 기록 열은 중복이 아니므로 **유지** | `applyRoster` |
| 반·날짜 선택 유지 | **유지 안 됨** — 4개 화면 모두 첫 반으로 시작. 대시보드 "출결 탭으로"도 반·수업 없이 `/classes` 이동 | 각 페이지 `items[0]` |
| 생성 오류 → 수정 화면 이동 | **없음** — 사유 문구만 표시. 업로드 결과 팝업은 "학생·반 관리의 연락처 수정에서…" 문장 안내만 | `ComposeTab`, `UploadTab` |
| 템플릿 미리보기 존재 | **있음** — 편집 모달 "검증·예시 보기"(서버 가상 데이터 치환), 실제 학생 치환은 누락·예외 생성 미리보기. **신규 구현 불필요** | `validateTemplate`, `preview` |
| 반별 통계 선택 ↔ 학생 목록 필터 | 반 선택은 연결됨(행 클릭). **상태 필터는 Select뿐이고 반별 상태 건수와 연결 안 됨**, 상단 카드는 전체 합계라 목록과 범위가 다름 | `MessageOperationsPage` |
| 저장·메시지 생성 결과 내부 분리 | **API는 분리**(`saved_rows…` / `drafts[].created/skipped`), **UI는 한 문장·빨간 오류로 혼합**. 재업로드 시 "이미 메시지 있음"으로 건너뛴 학생까지 빨간 '실패' 팝업 | `UploadTab.confirm`, 서버 `notifications/service.py:342` |

### 추가 발견 (코드 추적 중)
- **반 전환 경쟁 상태(데이터 무결성 위험)**: `ClassworkPage.reloadLessons`/`NotificationsPage` 수업 목록 요청에 늦은 응답 무시 장치가 없고, 반 변경 직후 첫 렌더에서 새 탭이 **이전 반의 수업 목록**으로 기본 수업을 골라 출결을 불러옴. 이전 반 응답이 늦게 오면 반 B 선택 상태에서 반 A 명단이 표시되고 저장도 반 A 수업으로 감(서버는 권한만 검사). → 시나리오 E 직접 해당.
- `AttendanceTab.load`도 수업을 빠르게 바꾸면 늦은 응답이 덮어씀.

## 3. 개선 대상 (IMPLEMENT) — UX 효과 / 비용 / 회귀 위험
| # | 개선 | 효과 | 비용 | 위험 | 영향 파일 |
|---|---|---|---|---|---|
| P1-a | 반 전환 경쟁 상태 제거: 수업 목록을 `classroom_id`로 거르고, 늦은 응답 무시 | 상 (잘못된 반 저장 방지) | 하 | 하 | `ClassworkPage`, `AttendanceTab`, `NotificationsPage` |
| P1-b | 작업 반 유지: URL `?classroom=` 우선 → 같은 브라우저 탭에서 마지막 선택 반(sessionStorage, 서버가 준 반 목록 안에서만) → 첫 반 | 상 | 하 | 중(기본 반 변경) | 신규 `shared/workingClassroom.ts`, 4개 페이지 |
| P1-c | `/classes?classroom&tab&lesson&day` 딥링크 + 화면 상태를 URL에 반영(replace) | 중 | 중 | 중 | `ClassworkPage`, `AttendanceTab`, `ProgressTab` |
| P1-d | 성적 안내 탭·반을 URL에 반영 → 사이드바 강조 일치, 북마크·복귀 URL 정확. 페이지 내부 갱신은 재마운트하지 않음 | 중 | 중 | 중 | `NotificationsPage`, `router.tsx` |
| P1-e | 오류 → 수정 화면 직접 이동 + "원래 작업으로 돌아가기"(`?from=` 내부 경로만 허용) | 상 | 중 | 하 | 신규 `shared/ui/ReturnBanner.tsx`, `ComposeTab`, `LearningOpsPage`(`?contact=`), `ClassworkPage`, `UploadTab`, `MessageOperationsPage` |
| P2-a | 출결 선택 버튼 한 줄, 저장 필요 표시를 저장된 기록 칸으로, 미저장 행 강조, 저장 바 하단 고정 | 상 | 하 | 하 | `AttendanceTab`, `App.css` |
| P2-b | 평가 등록을 모달로(엑셀 업로드가 주 생성 경로 → 수동 등록 빈도 낮음, 수정은 이미 모달) → 목록 전체 폭 | 중 | 하 | 하 | `GradesTab` |
| P2-c | 템플릿 목록 전체 폭·열 폭 확보, 변수 설명은 접이식(목록) + 편집 모달 안 | 중 | 하 | 하 | `TemplatesTab` |
| P3 | 업로드: 완료 단계 요약 접기, 검증 결과 4분류(정상/확인 필요/오류/처리 제외) 클릭 필터, 저장 결과 ↔ 초안 생성 결과 분리, 기존 초안 존재를 실패와 구분, 후속 조치 버튼 | 상 | 중 | 중 | `UploadTab` |
| P4-a | 누락·예외 생성: 학생 목록 | 메시지 상세 분할, 사유별 해결 링크, 기존 메시지 → 검토 이동 | 상 | 중 | 중 | `ComposeTab` |
| P4-b | 처리 현황: 7개 카드 → 요약 1개(대상·완료·완료율 + 미처리·실패 강조), 상태 필터를 **선택 반 건수 표시 버튼**으로, 보호자 이메일 없음 → 연락처 수정 링크(관리자) | 중 | 중 | 중 | `MessageOperationsPage` |
| P5 | 대시보드: 오늘 수업 → 해당 반·수업 출결로 직행, 메시지 숫자 → 해당 상태 처리 현황 | 중 | 하 | 하 | `DashboardPage` |

## 4. 비대상 (변경하지 않음)과 이유
| 항목 | 이유 |
|---|---|
| 사이드바/탭 통합·메뉴 재구성 | 두 진입점 모두 쓰임새가 다름, URL·북마크 보호. 동기화만 수정 |
| 검토·발송 화면(ReviewTab) 레이아웃 | 9.5에서 분할·연속 검토 완료 |
| 템플릿 실제 치환 미리보기 신규 구현 | 이미 존재(가상 데이터 예시 + 누락·예외 생성 미리보기) |
| 업로드 미등록 학생 → 학생 관리 화면 링크 | 업로드 화면 안의 신규/복귀/제외 결정이 더 짧은 경로(이미 구현) |
| 업로드 오류 '유형별'(출결/점수 등) 세부 필터 | 4분류 필터 + 행별 사유로 충분, 세부 분류는 서버 오류 코드가 없어 문자열 추정 필요 |
| 일괄 확정·일괄 모의 발송, 업로드 이력 화면 | 신규 API 필요(9.5 DEFER 유지) |
| 상태 태그 통합, 전체 테마·라이브러리 변경 | 9.5 REJECT 유지, 새 라이브러리 금지 |
| 학습 현황(ProgressTab)·학생 기록 드로어 레이아웃 | 확인된 결함 없음 |

## 5. 승인 필요 항목
없음 — 모든 개선이 기존 API 응답 필드(`student_id`, `existing_notification_id`, `lesson_id`, `ClassroomCounts`)로 가능. 문자열 분류는 서버 상수 문구 1건("이미 이 수업·템플릿의 메시지가 있습니다", 단독 사유일 때만)과 생성 불가 사유 문구(`notifications/engine.py`)에 한정하고, 일치하지 않으면 기존 표시(일반 실패)로 처리.

## 6. 영향 테스트
`ClassworkPage.test`(Router 감싸기 필요, 평가 등록 카드 → 버튼 기대값 변경), `NotificationsPage.test`(Router 감싸기, 누락·예외 분할 표시), `MessageOperationsPage.test`(상태 필터 Select → 버튼), `LearningOpsPage.test`(Router 감싸기), `DashboardPage.test`, `AppLayout.test`. 공통 `test/setup.ts`에 sessionStorage 초기화 추가.
기존 기대값을 완화하지 않고, 의도적으로 바뀐 UI만 기대값을 갱신하며 근거를 보고서에 기록.

## 7. 검증 방법
Vitest 전체, `tsc -b`, `oxlint src`, `npm run build`. 백엔드는 변경이 없어 재실행은 선택(실행 여부를 보고서에 명시). 브라우저 E2E 도구(Playwright 등)가 프로젝트에 없고 새 도구 도입은 금지 → 업무 시나리오는 컴포넌트 통합 테스트로 검증하고 실제 브라우저 점검은 **미실행**으로 기록.
