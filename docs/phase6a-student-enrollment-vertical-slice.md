# Phase 6A 학생·반·수강 Vertical Slice

## 구현 결과

FastAPI `learningops` 모듈을 Router → Service → Repository → SQLAlchemy 구조로 추가했다.
React `/students` 화면은 ADMIN에게 반·학생·수강·직원 배정 폼을 제공하고, 모든 인증 직원에게
반 ID 기반 담당 학생 목록을 제공한다. UI 권한 표시는 편의 기능일 뿐 서버 인가를 대체하지 않는다.

| API | 권한 | 결과 |
|---|---|---|
| `POST /api/classrooms` | ACTIVE ADMIN + CSRF | 반 생성, 중복 409 |
| `POST /api/students` | ACTIVE ADMIN + CSRF | 학생 생성, 업무 키 충돌 409 |
| `POST /api/classrooms/{id}/enrollments` | ACTIVE ADMIN + CSRF | ACTIVE 수강 생성 |
| `POST /api/classrooms/{id}/assignments` | ACTIVE ADMIN + CSRF | 동일 역할의 ACTIVE 직원 배정 |
| `GET /api/classrooms/{id}/students` | 인증 직원 | ADMIN 전체, 그 외 유효 담당 반만 |

목록 응답은 학생 ID, 이름, 학교, 수강 상태/등록일만 반환한다. 보호자 이름·이메일은 교직원
목록에서 제외했다. 다른 반 ID 직접 대입(IDOR/BOLA)은 DB의 직원 ID·역할·유효 기간 배정으로
403 처리한다. 비활성 반은 404, 비활성 직원 배정은 400이다.

## DB와 호환성

기존 13개 업무 테이블과 `002_staff_auth_rbac`를 유지하고 additive migration
`003_phase6a_enrollment_integrity`를 추가했다. 기존 `uq_enrollment(student_id,
classroom_id,enrolled_at)`만으로는 날짜가 다른 동시 중복을 막지 못하므로
`uq_enrollment_student_classroom(student_id,classroom_id)`를 추가한다. 기존 중복이 있으면
migration은 데이터를 변경하지 않고 실패한다. 적용 전 다음 읽기 전용 쿼리 결과가 0건이어야 한다.

```sql
SELECT student_id, classroom_id, COUNT(*)
FROM enrollment GROUP BY student_id, classroom_id HAVING COUNT(*) > 1;
```

Java와 Python Import Confirm은 이미 학생·반의 최신 수강을 조회해 상태를 갱신하므로 이 제약과
의도상 일치한다. 다만 과거 재등록을 별도 행으로 보존해야 한다는 제품 결정이 생기면 현재 제약을
적용하지 말고 enrollment period 식별자와 활성 기간 중첩 방지 제약을 별도 설계해야 한다.
동명이인 업무 키는 현재 `(name, coalesce(school_name,''))`이며 임의 변경하지 않았다. 같은 이름과
학교인 실제 동명이인은 충돌하므로 향후 비노출 내부 학생번호 도입과 Import 매핑 migration이 필요하다.

## 메시지 처리 상태 설계

- 입력 누락: 종료된 수업이 처리 대상이고 업무 기한이 지났지만 필수 출결/성적이 없는 경우만 판정
- 검토 대기: 초안 생성 후 직원 확정 전
- 처리 대기: 직원 확정 후 Mock Sender 처리 전
- 완료/부분 실패/실패: 모의 처리 대상 건의 결과 집계
- 제외: 퇴원, 연락처 없음 등 명시된 정책으로 처리 대상이 아닌 건

단순히 발송 기록이 없다는 이유로 누락 처리하지 않는다. 모의 완료는 실제 이메일 수신 완료가
아니며 UI는 색상과 함께 상태명과 건수를 표시한다. 이 상태들은 Phase 8~9 설계이며 Phase 6A DB에
미리 enum/컬럼을 추가하지 않았다.

## 실제 검증 (2026-11-15 KST)

| 항목 | 결과 | 증거 |
|---|---|---|
| Ruff | PASS | `ruff check --no-cache backend`: all checks passed |
| Python 비DB pytest | PASS | 35 passed, 16 PostgreSQL tests deselected |
| React Vitest | PASS | 7 files, 20 tests passed |
| React lint | PASS | `oxlint src`, 오류 없음 |
| React production build | PASS | TypeScript + Vite, 3,286 modules transformed |
| Docker/DB 상태 | BLOCKED | Docker Desktop Linux Engine pipe 없음 |
| PostgreSQL 통합/동시성/FK/rollback | BLOCKED | 테스트 DB 비밀번호 미설정, Docker 중지 |
| Java 전체/DB 회귀 | BLOCKED | `JAVA_HOME` 미설정; DB 환경 없음 |
| 개발 DB revision/ACTIVE ADMIN/preflight | BLOCKED | 개발 DB에 안전하게 연결할 환경 없음 |
| 미인증 `/api/auth/me` 401 | BLOCKED | 실행 DB 없음(기존 통합 테스트 계약은 존재) |
| 브라우저 E2E | BLOCKED | 실행 DB와 로그인 가능한 계정 없음 |

BLOCKED 항목을 PASS로 추정하지 않았다. 기존 `academy-postgres`를 포함해 컨테이너·볼륨을
수정/삭제하지 않았고 개발 DB에 migration이나 테스트를 실행하지 않았다. Docker가 시작되고 로컬
비밀 환경변수와 JDK가 준비되면 `scripts/run-postgres-integration.ps1`의 컨테이너 라벨·DB identity
guard를 통과한 전용 테스트 DB에서 먼저 migration과 신규 동시성/인가 테스트를 실행해야 한다.

## 남은 위험과 다음 단계

PostgreSQL 실증 전에는 003 적용성과 경쟁 조건, FK/rollback, API 전체 보안 흐름을 완료로 간주할
수 없다. 다음 작업은 전용 테스트 DB에 003을 적용한 Phase 6A 통합 테스트 추가·실행, OpenAPI
정적 문서 동기화, ADMIN 직원 검색/배정 해제 UX를 Phase 6B에서 구현하는 것이다. 실제 개인정보,
외부 전송, 유료 서비스는 사용하지 않는다. Codex 사용량 과금은 프로젝트가 통제할 수 없다.

## 저장 공간 관리 결과

2026-11-15 KST에 읽기 전용으로 확인했다. `fsutil`/WMI는 권한상 C 값을 주지 않았으나 Node의
읽기 전용 filesystem 통계로 교차 확인했다. C드라이브는 총 약 219.2GB 중 **약 21.5GB 사용
가능**, D드라이브는 총 238.4GB 중 **66.3GB 사용 가능**이었다.

| 항목 | 확인 결과 |
|---|---|
| 프로젝트 | `D:\refactor\backend-architecture`, 약 343MB |
| Python 가상환경 | `D:\refactor\backend-architecture\backend\.venv`, 약 127MB; 재생성 안 함 |
| Node 의존성 | `D:\refactor\backend-architecture\frontend\node_modules`, 약 212MB; 재설치 안 함 |
| React dist | `D:\refactor\backend-architecture\frontend\dist`, 약 1.3MB |
| 기존 pip 캐시 | `%USERPROFILE%\AppData\Local\pip\cache`, 약 74MB |
| 기존 npm 캐시 | `%USERPROFILE%\AppData\Local\npm-cache`, 약 684MB |
| Docker 설정/메타데이터 | C 사용자 프로필 아래의 소규모 설정·로그 경로 |
| Docker WSL 데이터 | `D:\DockerData\DockerDesktopWSL`, 약 12.2GB |
| Docker 가상 디스크 | `disk\docker_data.vhdx` 약 12.1GB, `main\ext4.vhdx` 약 104MB, 모두 D드라이브 |

Docker Desktop 설정의 `CustomWslDistroDir`가 위 D 경로를 명시한다. Engine이 중지되어
`docker info`의 `DockerRootDir`와 컨테이너별 실제 사용량은 확인하지 못했다. WSL 조회도 현재
권한에서 `E_ACCESSDENIED`였으므로 배포판 설정은 변경하지 않았다.

이번 구현의 신규 대용량 파일은 없다. 가장 큰 신규 산출물은 기존 `node_modules`를 재사용한
React build이며 `dist` 전체가 약 1.3MB다. 이전 검증에서 C의 Orca 작업 임시 경로를 약 2.6MB
사용한 것은 실행 환경상 불가피했지만 프로젝트 산출물은 아니다. 해당 사용자 파일을 임의 삭제하지
않았다.

향후 명령은 `scripts/use-d-drive-dev-env.ps1`을 현재 세션에 dot-source하여 `.dev-data` 아래로
TEMP/TMP, pip/npm/Ruff/pytest cache와 coverage를 보낸다. `scripts/verify-all.ps1`도 이를 자동
적용한다. 기존 C의 pip/npm 캐시는 사용자 승인 없이 삭제·이동하지 않았다. 필요하면 새 다운로드만
D 캐시에 저장하고, C의 기존 캐시는 다른 프로세스 사용 여부를 확인한 뒤 별도 승인 작업으로 정리할
수 있다. Docker 데이터는 이미 D에 있으므로 이전 대상이 아니다.

환경 스크립트를 실제 실행해 모든 경로가 D 프로젝트 내부를 가리키는 것과 해당 설정에서 Ruff가
PASS하는 것을 확인했다.
