# 최종 복구 검증 업데이트 (2026-11-15 KST)

- Docker Desktop 안전 복구: **PASS**
- 기존 컨테이너·볼륨·PostgreSQL 데이터 보존: **PASS**
- 개발·테스트 PostgreSQL 연결 및 health: **PASS**
- Migration 003 및 Phase 6A 실DB 검증: **NOT RUN / 별도 안전 검증 필요**

공식 Docker 릴리스 페이지에서 연결되는 `desktop.docker.com` 배포본만 사용해 4.86.0에서
4.99.0 build 245822로 per-user 인플레이스 업데이트했다. 설치 종료 코드는 0이며 Docker
Engine 29.9.3의 `running` 상태를 확인했다. 아래 상세 진단 중 BLOCKED 표기는 업데이트 전
상태이며 이 최종 업데이트 절의 실측 결과로 대체한다.

## 공식 설치 파일 검증

- URL: `https://desktop.docker.com/win/main/amd64/245822/Docker%20Desktop%20Installer.exe`
- D드라이브 저장: `.dev-data\tmp\Docker Desktop Installer 4.99.0.exe`
- 크기: 623,969,712 bytes
- SHA-256: `A5E299131C9C53D60F3F752B162078945EB5FAF6EEDCF0BE20A214C6E6CEA444`
- Authenticode: `Valid`, 서명자 `Docker Inc`, 발급자 DigiCert

## 복구 후 실제 검증

| 항목 | 개발 | 테스트 |
|---|---|---|
| PostgreSQL 컨테이너 | healthy, 127.0.0.1:55431 | healthy, 127.0.0.1:55432 |
| DB명 | `academy_learningops_dev` | `academy_learningops_test` |
| Alembic revision | `002_staff_auth_rbac` | `002_staff_auth_rbac` |
| public 테이블 수 | 18 | 18 |
| ADMIN 계정 수 | 0 | 0 |

`academy_learningops_postgres_dev_data`, `academy_learningops_postgres_test_data`와
`D:\DockerData\DockerDesktopWSL`의 기존 데이터 연결을 확인했다. 소유권이 불명확한
`academy-postgres`는 변경하지 않았다. Migration 003과 관리자 생성도 수행하지 않았다.

복구 후 C드라이브 여유는 27,673,108,480 bytes(약 25.77GiB), D드라이브 여유는
69,172,199,424 bytes(약 64.42GiB)다. 신규 대용량 파일은 D드라이브의 공식 설치 파일
623,969,712 bytes이며 설치 추출 임시 경로도 `D:\Temp\DockerDesktopInstallers\...`였다.

Factory Reset, Clean/Purge, prune, volume/container/VHDX 삭제, WSL unregister/shutdown,
PostgreSQL 초기화, 보안 설정 변경과 재부팅은 실행하지 않았다.

# Docker Desktop Windows/WSL2 안전 복구 보고서

진단 시각: 2026-11-15 KST  
우선순위: 데이터 보존 > 시스템 보안 > 복구 가능성 > 최소 변경

## 1. 결과 요약

Docker Desktop Linux Engine은 아직 복구되지 않았다. 다만 원인은 단일 Docker AI 설정이 아니라
**Docker Desktop 4.86.0이 비정상 종료 후 남은 Windows AF_UNIX reparse-point socket을 제거하지
못하는 일반적인 시작 결함**으로 좁혀졌다. Inference socket을 격리하자 backend가 그 단계를
통과하고 다음 `dockerEthernetVfkit` socket에서 동일 오류로 중단된 것이 핵심 증거다.

개별 IPC를 계속 정리하는 방식은 중단했다. Docker 공식 4.89.0 릴리스 노트에 Windows에서
“ungraceful shutdown left behind a stuck socket file” 때문에 시작하지 못하는 문제 수정이 명시되어
있다. 현재 설치된 4.86.0은 해당 수정 전 버전이다. 공식 인플레이스 업데이트는 유력한 다음 단계지만
사용자 명시 승인 전에는 설치하지 않는다.

## 2. Gate A — 읽기 전용 상태

| 항목 | 확인값 |
|---|---|
| Windows | 10.0.26300.9974, 표시 버전 26H2 |
| Docker Desktop | 4.86.0 build 236216, per-user 경로 |
| Docker CLI / Engine bundle | 29.7.2 |
| Docker Desktop CLI plugin | 0.4.3 |
| WSL | 2.6.3.0, kernel 6.6.87.2-1 |
| WSL 서비스 | `WslService` Running/Automatic |
| 가상화 서비스 | `vmcompute` Running/Manual |
| WSL distro 목록 | 현재 권한에서 `E_ACCESSDENIED`, 미확인 |
| Docker context | `desktop-linux`, named pipe endpoint |
| 설치 경로 | 사용자 프로필 아래 Docker Desktop per-user 설치 |
| Docker WSL 데이터 | `D:\DockerData\DockerDesktopWSL` |
| data VHDX | 약 12.1GB, 마지막 수정 2026-11-12 20:20 KST |
| main VHDX | 약 104MB, 마지막 수정 2026-11-12 20:21 KST |

설정 JSON은 정상 파싱되었고 `SettingsVersion=45`, `EnableDockerAI=true`,
`UseContainerdSnapshotter=true`, `CustomWslDistroDir=D:\DockerData\DockerDesktopWSL`이었다.
credential 또는 token은 출력하지 않았다.

시작 전 여유 공간은 C 약 21.51GiB, D 약 66.21GiB였다. 오류를 설명할 만큼 디스크가 가득 찼다는
증거는 없다.

## 3. 최초 오류와 로그 시간순서

Docker backend 로그의 실제 오류는 다음과 같다. 사용자 계정 부분은 보고서에서 생략한다.

1. 2026-11-15 00:24 KST: `Docker/run/dockerInference` 제거 실패
2. backend cancel 및 error dialog
3. 해당 stale IPC 정리 후 00:28 KST: `docker-secrets-engine/engine.sock` 제거 실패
4. 다음 재시작에서 `dockerInference` 제거 실패 재발
5. 본 작업에서 기존 `dockerInference`를 삭제하지 않고 격리한 후 00:54 KST:
   `Docker/run/dockerEthernetVfkit` 제거 실패

모든 오류는 0바이트 `Archive, ReparsePoint`이며 메시지는
`The file cannot be accessed by the system`이다. 마지막 오류는 AI가 아닌 vital network service에서
발생해 결함 범위가 Inference에 한정되지 않음을 입증한다.

## 4. Gate B — 원인 가설 비교

### 가설 1: Docker AI/Inference 기능

- 지지: 최초 blocker가 `dockerInference`, 설정에 `EnableDockerAI=true`.
- 반증: 이 값을 false로 바꾸어도 Inference Manager가 동일하게 시작되었고 오류가 재현됨.
- 판정: 단독 원인 아님. 해당 키는 4.86.0의 Model Runner 시작 제어 키가 아니거나 별도 의미다.

### 가설 2: Secrets Engine socket 충돌

- 지지: 실제 `engine.sock` 오류가 한 번 재현됨.
- 반증: Secrets Engine은 과거 로그에서 반복적으로 정상 ready 상태였으며, 현재 socket은 없음.
- 판정: 개별 서비스 문제가 아니라 동일 socket 정리 결함의 한 증상.

### 가설 3: WSL/열린 핸들

- 지지: 비정상 종료 뒤 stale reparse points가 남음.
- 반증: WSL/가상화 서비스는 실행 중이며 VHDX 손상 로그가 없음. 프로세스 종료 후에도 오래된
  reparse point 자체가 제거 불가 상태.
- 미확인: WSL distro 목록은 권한 부족으로 조회하지 못함. 재부팅 효과는 미검증.
- 위험: `wsl --shutdown`과 재부팅은 실행 중 환경 전체에 영향이 있어 자동 실행하지 않음.

### 가설 4: Docker Desktop 4.86.0 결함

- 지지: 서로 다른 세 socket에서 동일 제거 실패. 공식 4.89.0 Windows release note가 비정상 종료
  후 stuck socket 시작 실패 수정을 명시.
- 반증: 없음. 단, 업데이트를 아직 적용하지 않아 실제 해결은 미검증.
- 판정: 가장 강한 원인.

### 가설 5: 설정/저장 공간/권한

- JSON: 정상이며 원복 hash까지 검증.
- 저장 공간: C/D 모두 여유 있음.
- 데이터 경로: D에 정상 존재하고 VHDX timestamp 변화 없음.
- 권한: CLI의 일부 로그 쓰기는 sandbox에서 거부됐지만, 승격된 실제 Desktop도 동일 backend 오류를
  기록하므로 sandbox만의 문제는 아님.
- 판정: 주원인 증거 부족.

## 5. Gate C/D — 시도한 복구와 변경 전후

### 정상 종료/재시작

오류 dialog 상태의 Docker 소유 프로세스만 identity 확인 후 종료하고 재시작했다. 무관한 프로세스는
종료하지 않았다. 동일 오류가 재현되었다.

### 설정 변경 실험

Docker 완전 종료 후 설정을 D에 백업하고 `EnableDockerAI` 한 값만 false로 변경했다.

- 백업: `.dev-data/backups/docker-recovery-20261115/settings-store.before-disable-ai.json`
- 원본 SHA-256: `B88BD665D5A7A9CD00A1634C8CB3D8CEE6A05B6806DEF2FAF8B8FD2DE58B5B55`
- 데이터 경로 보존 확인: `D:\DockerData\DockerDesktopWSL`

변경 후에도 Inference 오류가 동일 재현되어 효과 없음으로 판정했다. 백업 hash를 검증한 뒤 설정을
원래 상태로 복원했으며 복원 후 SHA-256이 원본과 일치한다.

### IPC 격리

Docker가 완전히 종료된 상태에서 실제 로그 경로의 기존 0바이트 reparse point 하나만 삭제 대신
이름 변경했다.

```text
dockerInference
→ dockerInference.quarantine-20261115-0055
```

그 결과 Inference 단계는 통과했지만 `dockerEthernetVfkit`에서 동일 오류가 발생했다. 새로운
blocker는 0바이트 reparse point이고 2026-11-12 생성 항목이었다. 같은 방식의 반복 격리는 하지
않았다. 격리 항목은 0바이트이며 원복 가능하도록 보존했다.

Windows 재부팅, `wsl --shutdown`, 추가 IPC 격리, 설치 업데이트는 수행하지 않았다.

## 6. Gate E — 공식 해결책 검토

Docker 공식 release notes에 4.89.0 Windows 수정으로 비정상 종료 후 stuck socket 때문에 Desktop이
시작하지 못하는 문제가 명시되어 있다. 현재 4.86.0보다 최신 안정 버전으로 공식 in-place update가
가장 직접적인 수정 경로다. 현재 backend update metadata에는 4.99.0 공식 installer와 checksum이
제공되지만, 설치 전 다음 승인이 필요하다.

- 설정 백업과 D의 WSL VHDX 위치 재확인
- 공식 Docker URL과 SHA-256 검증
- 약 624MB installer 및 업데이트 중 추가 공간 확인
- per-user in-place update가 custom WSL data directory를 보존하는지 재확인
- 사용자 명시 승인

업데이트를 승인하지 않는 대안은 Windows 재부팅 후 현재 격리 상태로 한 번만 재검증하는 것이다.
재부팅 역시 사용자 작업 보존이 필요하므로 자동 실행하지 않는다.

참고:

- [Docker Desktop release notes](https://docs.docker.com/desktop/release-notes/)
- [Docker Desktop settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)
- [Docker Model Runner 설정](https://docs.docker.com/ai/model-runner/get-started/)

## 7. Gate F — Docker/PostgreSQL 검증

| 검증 | 결과 |
|---|---|
| Docker Engine API | FAIL — named pipe 없음/접근 불가 |
| `docker ps -a` / volume 목록 | BLOCKED |
| 기존 컨테이너/volume 보존 확인 | VHDX 보존은 확인, Engine 목록은 BLOCKED |
| 개발 PostgreSQL health/연결 | BLOCKED |
| 테스트 PostgreSQL health/연결 | BLOCKED |
| Alembic revision/테이블 수 | BLOCKED |
| ACTIVE ADMIN 수 | BLOCKED |
| 기존 업무 데이터 | VHDX 무변경 확인, DB 논리 조회는 BLOCKED |

Migration, DB write, TRUNCATE, PostgreSQL 테스트는 실행하지 않았다.

## 8. 데이터 보호 및 실행하지 않은 위험 작업

다음은 모두 실행하지 않았다.

- Factory Reset, Clean/Purge, prune, volume/container/image 삭제
- VHDX 삭제·압축·이동, WSL unregister/export/import/shutdown
- PostgreSQL 초기화 또는 migration
- Defender/방화벽/UAC/SmartScreen 변경
- 레지스트리 변경, 재설치, 업데이트, Windows 재부팅
- 진단 로그 업로드 또는 외부 전송

VHDX 크기와 마지막 수정 시각은 진단 전후 변하지 않았다. 설정 파일은 원상 복구됐다.

## 9. 저장 공간 변화

- 시작: C 약 21.51GiB, D 약 66.21GiB 사용 가능
- 종료: C 약 21.47GiB, D 약 66.34GiB 사용 가능

관찰 구간에 C가 약 40MB 감소했으나 Docker host 로그/프로세스와 다른 동시 시스템 활동을 분리할
수 없어 전부 본 작업 영향이라고 단정하지 않는다. D 백업은 1KB 미만이다. 대용량 다운로드나
installer 생성은 없었다.

## 10. 남은 위험과 권장 순서

1. **권장:** 공식 Docker Desktop 안정 버전으로 in-place update를 별도 승인 후 수행하고 checksum
   검증. 4.89.0 이상에는 정확한 stuck socket 수정이 포함됨.
2. 업데이트 전에 재부팅을 선호한다면 사용자가 열린 작업을 저장한 후 직접 재부팅하고, 재부팅 직후
   Docker를 한 번 시작해 동일 오류 여부 확인.
3. 복구 성공 후 즉시 `docker version/info/ps -a/volume ls`와 Academy 컨테이너 라벨·포트·mount를
   읽기 전용 검증.
4. 그 다음에만 개발·테스트 PostgreSQL health, DB identity, revision, 테이블/ADMIN 수를 읽기 전용
   확인. Migration은 자동 적용하지 않음.

현재 성공 판정은 **실패/BLOCKED**다. Docker Engine과 PostgreSQL의 실제 정상 동작은 아직 입증되지
않았다.
