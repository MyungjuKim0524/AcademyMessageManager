# Academy LearningOps — Phase 8.1 인계 프롬프트 (엑셀 업로드 기반 학부모 안내)

> 이 문서를 새 작업 공간의 첫 프롬프트로 사용한다. 2026-11-19 기준 상태.

## 0. 역할과 원칙

당신은 FastAPI·PostgreSQL·React/TypeScript 기반 학원 업무 시스템을 이어받는 시니어 풀스택 엔지니어다.
프로젝트: `D:\refactor\backend-architecture` (Windows, PowerShell 5.1, Git 없음 — Git 설치·초기화·업로드 금지).

반드시 지킬 것:
- 설명을 믿지 말고 코드·DB·테스트로 상태를 먼저 확인한다.
- 개발 DB(`academy_learningops_dev`, 127.0.0.1:55431) Migration·데이터 변경은 **백업 + 사용자 승인 후에만**. 검증은 테스트 DB(`academy_learningops_test`, 127.0.0.1:55432)에서.
- Docker 볼륨·컨테이너 삭제 금지, `academy-postgres` 컨테이너 건드리지 않기, 실제 발송·외부 API·유료 서비스 금지.
- 비밀번호·학생 개인정보를 로그·보고서·테스트 데이터에 넣지 않는다. **`D:\학원 엑셀 예시.xlsx`는 실제 근무 파일일 수 있다 — 학생 이름 칸을 출력·복사하지 말 것**(구조 분석은 끝났다, §3).
- 기존 테스트를 삭제하거나 기대값을 느슨하게 바꿔 통과시키지 않는다. 실행하지 않은 테스트를 PASS로 쓰지 않는다.
- 사용자와 한국어로 소통한다. 사용자가 다른 Node 프로젝트(`D:\cozy-mountain-library`)를 동시에 띄워 둘 수 있으니 그 프로세스는 건드리지 않는다.

## 1. 지금까지 완료된 것 (요약)

- Phase 6B~8 완료. 문서: `docs/phase7-lessons-attendance-grades.md`, `docs/phase7-1-stabilization.md`, `docs/phase8-parent-notification-workflow.md`, `docs/phase8-progress.md`.
- 개발 DB는 **Migration 008**까지 적용됨. 테스트 DB는 **009**까지 적용됨.
- Phase 8 정책(사용자 결정): 조교(ASSISTANT)가 내용 확정(=승인, API `approve`)·모의 발송까지 직접 한다. 화면 용어 "승인" → "내용 확정". 보호자 이메일: 관리자 학생 목록에 표시, 메시지 상세는 전체 주소, 목록은 마스킹, 선생님·조교 학생 목록 응답에는 키 자체 없음.

## 2. Phase 8.1에서 이번에 구현한 것 (코드 작성 완료)

사용자 요구: 조교가 학원 엑셀을 올리면 반별 출결·과제·성적이 저장되고, 수업유형별 기본 템플릿으로 학부모 안내 초안이 자동 생성된다. 메시지 생성 경로를 하나로 통일한다.

| 영역 | 파일 | 내용 |
|---|---|---|
| Migration | `backend/alembic/versions/009_phase81_lesson_upload.py` | `notification_template.default_for_class_type`(REGULAR/EXAM_PREP, 부분 UNIQUE) + 기본 템플릿 2개 삽입, `assessment (lesson_id, title)` 부분 UNIQUE |
| 모델 | `backend/app/db/models/tables.py` | 위 컬럼·인덱스 반영 |
| 엑셀 해석 | `backend/app/modules/lesson_upload/workbook.py` | 반 블록 파서(순수 함수) |
| 업로드 서비스 | `backend/app/modules/lesson_upload/{service,schemas,router}.py` | `POST /api/lesson-uploads/preview`(쓰기 없음), `POST /api/lesson-uploads/confirm`(CSRF, 한 트랜잭션 저장 후 초안 생성) — `app/main.py`에 등록 |
| 템플릿 기본 지정 | `backend/app/modules/notifications/{schemas,service}.py` | `PATCH /api/notification-templates/{id}`에 `default_for_class_type`(REGULAR/EXAM_PREP/"NONE"), 이전 기본 자동 해제, 비활성 템플릿은 기본 불가 |
| 성적 문구 | `backend/app/modules/notifications/engine.py` | `{성적요약}` → "어휘 8/10" (점 제거) |
| 가져오기 결함 수정 | `backend/app/modules/imports/confirm.py` | 기존 CSV/XLSX 가져오기 수업 조회에 `session_no=1` 추가(Java와 동일 규칙) |
| 출결 기본값 | `frontend/src/features/classwork/AttendanceTab.tsx` | 미입력 학생을 화면에서만 "출석"으로 미리 선택 + "저장 안 됨" 표시, 저장 전 DB 무변경. "미입력 학생 모두 출석" 버튼 제거 |
| 업로드 화면 | `frontend/src/features/notifications/{uploadApi.ts,UploadTab.tsx}` | 수업일·파일 → 미리보기(행 색상+상태 태그) → 미등록 학생 질문 → 확정 → 결과 |
| 화면 정리 | `NotificationsPage.tsx`, `ComposeTab.tsx`, `TemplatesTab.tsx`, `api.ts`, `layout/AppLayout.tsx`, `app/router.tsx` | 탭: 엑셀 업로드(기본)·검토·발송·누락·예외 생성·템플릿. 템플릿 탭에 "엑셀 업로드 기본" 선택. 메뉴에서 "메시지 미리보기", "CSV/XLSX 미리보기" 숨김(라우트·API는 Java 호환 위해 유지). 첫 화면 `/notifications` |
| 테스트 | `backend/tests/test_phase81_workbook_parser.py`(3), `test_phase81_lesson_upload_integration.py`(4), `test_secure_import_integration.py`(+1), `test_postgres_integration.py`·`test_phase7_schema_integrity.py`(head 009), `test_phase8_*`(문구 "N/M") / `frontend/.../classwork/ClassworkPage.test.tsx`(출결 기본값 기대값), `.../notifications/NotificationsPage.test.tsx`(업로드 흐름 테스트 추가, 수동 생성은 '누락·예외 생성' 탭 클릭) |

## 3. 확정된 업무 규칙 (사용자 결정)

엑셀 형식(`D:\학원 엑셀 예시.xlsx`, 시트=시간대, 학생 행은 예시에 없음):
```
중3 토10 | 출결 | 예습 과제 | 주간 과제 | 문법, 문학, 독서 (15) | 어휘 (10)   <- 반 블록 머리글(2번째 칸이 "출결")
김아무개 | 출석 | A        | A        | 15                     | 10         <- 학생 행
```
- 반 유형: "중3 토10", "고1 토10A" = 정규 / "00고2 토10", "**고2 토6" = 내신 대비 / 그 외("002 토2" 오타 등) = 오류.
- 시험 칸 = 맞은 개수(또는 "12/15"), 전체 문항 수 = 머리글 괄호. 분야 이름의 쉼표 공백은 통일.
- 과제 등급 **A/B/C만** (D는 오류). 빈 칸 = 미입력.
- 이름 칸만 있는 행(예: 2시 시트 A2 메모) = 건너뜀.
- 수업일은 업로드 화면에서 지정(파일 1개 = 하루). 수업은 (반, 날짜, 1교시)로 찾거나 생성(COMPLETED).
- 출결: 앱 기록 없으면 엑셀 값 저장 / 같으면 통과 / **다르면 앱 값 유지 + 노란 "출결 불일치" + 그 학생 초안 미생성**.
- 과제 등급·시험 점수: 반·학생별 저장·갱신. 분야 = 수업에 연결된 평가(assessment). 결석·인정결석 학생의 빈 점수 = NOT_TAKEN(미응시), 출석 학생의 빈 점수 = 저장 안 함.
- 미등록 학생(빨간 표시): "신규 수강생인가요?" 예 → 그 반에 등록 / 아니요 → "복귀 학생인가요?" 예 → 휴원→재원(복귀일=수업일) / 아니요 → "오류로 간주해 해당 행은 성적 안내 메시지를 생성하지 않겠습니다." 후 제외. 담당 반 조교·선생님도 가능, 이력 기록.
- 확정 권한: 파일의 모든 반이 본인 담당일 때만(관리자는 전체). 프로그램에 없는 반은 오류(관리자가 먼저 반 등록).
- 확정 후 수업유형별 기본 템플릿으로 초안 자동 생성. 보호자 이메일 없는 학생은 건너뜀 사유 표시.

## 4. 남은 작업 (순서대로)

1. **프론트 테스트 실행** — 코드 수정 후 아직 실행 못 함(당시 PC 메모리 부족으로 Vitest 작업자 시작 시간 초과). 먼저 부하 확인 후:
   - `npx vitest run src/features/classwork src/features/notifications --maxWorkers=1 --testTimeout=60000` (frontend 폴더)
   - 실패 시 원인 분석. 주의: 이 화면들에서 jsdom `getByRole`은 수 분 걸린다 → 텍스트·라벨 조회 사용, 테스트 파일에 `configure({ asyncUtilTimeout: 10000 })` 패턴 사용 중.
   - 그다음 전체: `npm test -- --run`, `npx oxlint src`, `npm run build` (전체 Vitest는 약 5~7분 — 백그라운드 실행 권장). `tsc -b`와 oxlint는 마지막 수정 후 PASS 확인됨.
2. **백엔드 전체 회귀 재실행** — 템플릿 기본 지정 기능 추가 후 전체 실행은 아직(업로드·알림 테스트만 PASS). 테스트 DB 환경변수로:
   ```powershell
   cd D:\refactor\backend-architecture; . .\scripts\use-d-drive-dev-env.ps1
   $ErrorActionPreference='Continue'
   $pw=((docker inspect academy-learningops-postgres-test --format '{{range .Config.Env}}{{println .}}{{end}}') | ? {$_ -like 'POSTGRES_PASSWORD=*'}).Substring(18)
   $env:ACADEMY_DATABASE_URL="postgresql+psycopg://academy_test:$([uri]::EscapeDataString($pw))@127.0.0.1:55432/academy_learningops_test"; Remove-Variable pw
   $env:ACADEMY_DB_MODE='test'; $env:ACADEMY_DB_TEST_MODE='1'; $env:ACADEMY_RUN_POSTGRES_INTEGRATION='1'; $env:ACADEMY_ENABLE_DB_APIS='1'; $env:ACADEMY_COOKIE_SECURE='0'
   cd backend; .\.venv\Scripts\ruff.exe check --no-cache app tests alembic scripts
   cmd /d /c ".\.venv\Scripts\alembic.exe upgrade head 2>nul & .\.venv\Scripts\alembic.exe check 2>nul"
   .\.venv\Scripts\pytest.exe -q -p no:cacheprovider
   ```
   마지막 전체 실행(기본 지정 기능 전): **97 PASS**. 이후 +1(기본 지정 테스트) 예상.
3. **Java 회귀** (테스트 DB 009): `$env:JAVA_HOME="$env:USERPROFILE\.jdks\openjdk-26.0.2"`(cmd에서는 `%USERPROFILE%\.jdks\openjdk-26.0.2`), `DB_URL=jdbc:postgresql://127.0.0.1:55432/academy_learningops_test`, `DB_USER=academy_test`, `DB_PASSWORD`(위와 같은 방식) 설정 후 `mvn -q -DrunPostgresIntegration=true test`, 결과는 `target\surefire-reports\TEST-*.xml` 합산. 마지막 결과 48 PASS(008 기준).
4. **보고서 작성**: `docs/phase8-1-excel-upload.md`(구현·규칙·API·DB·테스트 실제 결과·남은 제약) + `docs/phase8-progress.md` 갱신. 화면 용어·정책 변경 근거 포함.
5. **개발 DB Migration 009 승인 요청** → 승인 시: 컨테이너 식별(라벨 `isolated-development`), `alembic upgrade 008:009 --sql`로 SQL 검사, `pg_dump -Fc`로 `.dev-data\backups\` 백업 + `pg_restore --list` 검증, `cmd /c`로 `alembic upgrade`(PowerShell은 Alembic INFO를 오류로 처리해 명령이 끊김), 읽기 전용 사후 검증(행 수·md5 지문 비교).
6. **서버 재기동 후 사용자 브라우저 확인**: `scripts\start-fastapi.ps1`(시작 시 DB가 Alembic head인지 검사), `scripts\start-frontend.ps1`. 에이전트 백그라운드 실행은 2시간 제한이 있어 사용자가 직접 터미널에서 띄우는 것을 권장. 확인 순서: 반 등록·학생 보호자 이메일 → 엑셀 업로드(가상 학생으로 만든 파일) → 미등록 학생 질문 흐름 → 확정 → 검토·발송에서 내용 확정·모의 발송.

## 5. 알려진 제약·주의

- 학생 매칭은 반 안에서 **이름 정확히 일치**. 같은 반 동명이인은 오류로 막음.
- 신규 등록 학생은 보호자 이메일이 없어 초안이 건너뛰어짐 → 관리자가 "연락처 수정" 후 '누락·예외 생성'으로 초안 생성.
- 출결 불일치 학생도 위와 같이 출결 확인 후 수동 생성.
- 업로드 이력은 별도 화면 없이 `audit_log`(LESSON_UPLOAD_APPLIED, UPLOAD_ROW_APPLIED, ENROLLMENT_CREATED_FROM_UPLOAD, ENROLLMENT_RESUMED)에 남음.
- Docker Desktop이 꺼져 있으면 테스트가 멈춘 것처럼 보인다 → `docker desktop status` 먼저 확인, `docker start academy-learningops-postgres-test academy-learningops-postgres-dev`.
- 공용 테스트 픽스처(Phase 7 `world`)가 `staff_user`를 CASCADE로 비우므로 템플릿도 지워진다 → 템플릿이 필요한 테스트는 직접 생성.

## 6. 최종 보고 형식

1) 진행 상태(완료/조건부 완료/미완료) 2) 구현 기능 3) 테스트 실제 결과(Python·PostgreSQL·Java·React·Browser) 4) DB(Revision, 테스트/개발 적용 여부, 백업) 5) 남은 작업·승인 필요 사항. 한국어로 간결하게.
