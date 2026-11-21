# Docker Desktop Recovery — Root Cause Analysis & Troubleshooting

작성일: 2026-11-10  
환경: Windows 11 Home build 26300, Docker Desktop 4.86.0, Docker Engine/CLI 29.7.2,
WSL2 backend

## 1. Incident Summary

Docker Desktop backend가 Inference manager용 Unix socket을 초기화하지 못해 종료됐다. 이로
인해 Docker Engine named pipe가 생성되지 않았고 PostgreSQL 개발·테스트 컨테이너를 사용할
수 없었다. 데이터 보호를 위해 Factory Reset, 재설치, WSL unregister, volume 삭제는 하지
않았다.

복구 후 Docker CLI와 Engine, WSL backend, 기존 컨테이너·볼륨, PostgreSQL schema를 실제로
검증했다.

## 2. Initial Symptoms

Docker host log에서 확인한 직접 오류는 다음과 같다.

```text
starting services: initializing Inference manager
listening on unix://.../Docker/run/dockerInference
remove .../Docker/run/dockerInference:
The file cannot be accessed by the system.
```

문제 항목의 상태는 0-byte `Archive, ReparsePoint`였고 LinkType과 Target은 유효하게 해석되지
않았다.

런타임 디렉터리 격리 후 CLI 파일은 정상 인식됐지만 Engine이 실행되지 않은 시점에는 다음
오류가 발생했다.

```text
failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine
The system cannot find the file specified.
```

이는 CLI 설치 실패가 아니라 Engine named pipe 부재를 의미했다.

## 3. Root Cause Analysis

### dockerInference의 역할

로그상 `dockerInference`는 Docker Desktop backend가 Inference manager와 로컬 통신하기 위해
생성하는 Unix-domain socket endpoint다. 이 프로젝트가 사용하는 PostgreSQL volume이나
컨테이너 데이터 파일이 아니다.

### Windows Reparse Point와 Unix Socket

Windows에서 Docker Desktop의 Unix socket 표현은 일반 데이터 파일이 아니라 reparse point로
보인다. 정상 상태에서도 현재 새로 생성된 `dockerInference`는 0-byte reparse point다. 따라서
reparse point라는 사실만으로 손상을 판정할 수 없다. 이전 항목은 Docker가 제거하려 할 때
Windows가 접근 및 이름 변경을 거부했고 경로 문법 오류까지 반환했다는 점이 비정상 증거다.

### 확인된 직접 원인

Docker backend는 시작 시 기존 socket을 제거하고 새 listener를 만들려 했다. 기존
`dockerInference`를 제거할 수 없어 Inference manager 초기화가 실패했고 backend가 취소됐다.
동일 오류가 `com.docker.backend.exe.log`와 `monitor.log`에서 반복 확인됐다.

### 최초 손상 원인 — 미확정

다음 가능성은 있으나 증거가 부족해 확정하지 않는다.

- 이전 Docker Desktop 비정상 종료
- Docker Desktop 업데이트 중 runtime 정리 실패
- Windows filesystem/reparse-point 상태 이상
- socket을 사용하던 프로세스나 보안 제품의 일시적 lock

### CLI 문제와의 연결

CLI executable과 PATH는 정상이었다. backend가 종료된 결과
`dockerDesktopLinuxEngine` named pipe가 생성되지 않았고 CLI가 Server에 연결할 수 없었다.
따라서 CLI 오류는 직접 원인이 아니라 Engine 미기동의 2차 증상이다.

## 4. Troubleshooting Timeline

| 순서 | 증상/가설 | 조치 | 결과 | 판단 |
|---:|---|---|---|---|
| 1 | Inference 초기화 오류 | Docker UI와 host log 확인 | 동일 socket 제거 오류 반복 | 직접 장애 지점 확인 |
| 2 | 일시적 process/WSL lock | Windows 재시작, `wsl --shutdown` | 동일 오류 지속 | 단순 lock 가설 약화 |
| 3 | CLI 누락 가능성 | `Get-Command`, `where.exe`, 전체 경로 실행 | CLI 29.7.2와 PATH 정상 | CLI 설치 정상 |
| 4 | Engine/context 문제 | `docker version/info/context ls` | context 정상, named pipe 없음 | Engine 미기동 확인 |
| 5 | socket 이상 | reparse point와 Docker log 조사 | 제거·rename 불가 기록 | runtime socket 이상 확인 |
| 6 | 데이터 위치 확인 | WSL registry와 VHDX metadata 조회 | D:의 VHDX 존재 | 영구 데이터 보존 확인 |
| 7 | runtime 격리 | 기존 `run`을 timestamp backup으로 격리 | 손상 socket 3개 보존 | 데이터 영역과 분리 |
| 8 | 정상 실행 | 공식 `Docker Desktop.exe` 실행 | 새 `run`, socket, named pipe 생성 | 복구 성공 |
| 9 | Engine 검증 | `docker version/info/context ls` | Client/Server 29.7.2 | CLI/Engine 정상 |
| 10 | 자원 검증 | `docker ps -a`, `volume ls`, mount 조회 | 컨테이너 3, volume 6 보존 | 데이터 자원 보존 |
| 11 | PostgreSQL 검증 | 승인된 두 컨테이너 시작, 읽기 전용 SQL | 둘 다 Healthy, 17.6 | DB 정상 |
| 12 | 저장 공간 분석 | `docker system df -v`, VHDX 크기 | cache와 미사용 자원 식별 | 정리 후보 확정 |
| 13 | 안전한 cache 정리 | `buildx prune --filter until=168h` | 59.02MB 제거 | 제한적 성공 |
| 14 | 사후 검증 | DB/schema/context/volume 재확인 | 전부 유지 | 무결성 유지 |

> Runtime 디렉터리 격리는 이 문서화 작업 전에 수행된 상태로 확인했다. 정확한 최초 rename
> 명령의 실행 주체와 원본 콘솔 출력은 Git 이력으로 검증할 수 없다.

## 5. Root Cause vs Secondary Symptoms

| 분류 | 내용 |
|---|---|
| 직접 장애 원인 | 기존 `dockerInference` socket 제거 실패로 backend 초기화 중단 |
| 미확정 근본 원인 | socket/reparse point가 최초로 비정상 상태가 된 이유 |
| 2차 증상 | Engine named pipe 부재, Docker CLI Server 연결 실패 |
| 개발 영향 | PostgreSQL 컨테이너와 DB integration test 실행 불가 |
| 관련 없는 항목 | CLI binary, PATH, Docker context는 정상 |

## 6. Recovery Solution

기존 runtime socket을 데이터 디스크와 분리해 격리한 후 공식 설치 경로에서 Docker Desktop을
정상 실행했다.

```text
%USERPROFILE%\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe
```

격리 경로:

```text
%USERPROFILE%\AppData\Local\Docker\run.backup-20261109-211726
```

Docker Desktop은 비어 있는 활성 `run`을 다시 만들고 정상 `dockerInference`와
`dockerEthernetVfkit` socket을 생성했다. Engine이 `desktop-linux` context의 named pipe를
열면서 CLI 연결이 복구됐다.

영구 데이터는 별도 VHDX와 named volume에 있었으므로 runtime socket 격리로 변경되지 않았다.

## 7. Data Integrity Validation

### Docker 자원

- 컨테이너 3개 보존
- `academy-postgres`는 정지 상태로 변경하지 않음
- volume 6개 보존
- 개발·테스트 PostgreSQL volume mount 유지

### PostgreSQL

| 항목 | 개발 | 테스트 |
|---|---|---|
| 상태 | Healthy | Healthy |
| DB | `academy_learningops_dev` | `academy_learningops_test` |
| PostgreSQL | 17.6 | 17.6 |
| public table | 14 | 14 |
| Alembic | `001_java_schema_baseline` | 동일 |
| 업무 데이터 | 0행 | 합성 데이터 7행 |

검증 쿼리는 `BEGIN READ ONLY`로 실행했다. 모든 row payload, checksum, PostgreSQL physical page
무결성까지 검사한 것은 아니다. 쓰기 통합 테스트도 이번 복구 검증에서는 실행하지 않았다.

## 8. Storage Optimization

### 정리 전후

| 항목 | 정리 전 | 정리 후 | 변화 |
|---|---:|---:|---:|
| Images | 4.877GB | 4.877GB | 0 |
| Build Cache | 6.463GB / 135개 | 6.404GB / 120개 | 약 -59MB / -15개 |
| Build Cache reclaimable(system df) | 3.063GB | 3.004GB | 약 -59MB |
| Volumes | 238.2MB / 6개 | 동일 | 0 |
| Containers | 3개 | 3개 | 0 |
| `docker_data.vhdx` | 12,937,330,688 bytes | 동일 | 0 |
| `main/ext4.vhdx` | 109,051,904 bytes | 동일 | 0 |
| D: free | 72,127,086,592 bytes | 72,110,309,376 bytes | 약 -16MB |

Windows 여유 공간 감소는 실행 중인 Docker/PostgreSQL의 background activity 영향을 포함하므로
cache 정리 효과와 직접 연결하지 않는다. VHDX는 non-sparse dynamic disk이며 내부 공간을
비워도 host 파일이 즉시 축소되지 않았다.

실행한 정리:

```powershell
docker buildx prune --filter "until=168h" --force
```

`--all`은 사용하지 않았다. Docker가 기본 정책에서 안전하게 분리 가능한 7일 초과 cache만
59.02MB 제거했다.

### 삭제하지 않은 항목

- 미사용 image 12개: PaperMentor 및 향후 재빌드 의존 가능성
- 미연결 volume 73.12MB: data/model/secret 성격, 손실 위험
- `academy-postgres`와 postgres:16 image: 소유자 불명확
- runtime backup: 0-byte로 삭제 실익 없음
- VHDX: 직접 변경 금지

## 9. Security Considerations

- 일반 조회를 우선하고 필요한 host 진단만 승인된 권한으로 실행했다.
- 비밀번호, container 전체 environment, registry credential을 출력하지 않았다.
- Factory Reset, prune-all, volume prune, WSL unregister를 사용하지 않았다.
- 인터넷 script와 외부 binary를 실행하지 않았다.
- Defender, firewall, certificate, PATH, registry를 변경하지 않았다.
- 데이터 디스크보다 수명이 짧은 runtime socket만 격리해 blast radius를 줄였다.

## 10. Lessons Learned

1. GUI 창의 존재, CLI binary 인식, Engine 연결은 각각 검증해야 한다.
2. runtime socket과 VHDX/named volume은 수명과 위험도가 전혀 다르다.
3. 직접 원인(socket 제거 실패)과 최초 손상 원인은 구분해야 한다.
4. `docker system df`의 reclaimable과 Windows drive free는 같은 수치가 아니다.
5. 안전한 기본 cache prune은 예상치보다 적은 공간만 제거할 수 있으며 이는 정상이다.
6. 복구 성공보다 데이터 보존을 우선하면 Factory Reset 없이 단계적으로 원인을 줄일 수 있다.

## 11. Prevention & Monitoring

다음은 현재 적용 완료가 아니라 **권장 사항**이다.

- 업데이트 전 Docker/WSL 정상 종료와 DB backup 확인
- 장애 시 `version → context → process → WSL → host log → storage` 순 체크리스트 사용
- 월 1회 `docker system df`, `docker buildx du` 기록
- cache는 기간 filter로만 정리하고 `--all`은 별도 승인
- PostgreSQL logical backup과 restore drill 수립
- 개발/테스트 volume 목록과 소유 프로젝트 inventory 유지
- Docker Desktop 업데이트 전 release note와 rollback 경로 확인
- VHDX 증가 추이를 기록하되 직접 compact는 별도 위험 평가 후 수행

## 증거 위치

- Docker log: `%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log`
- Compose: `compose.postgres-test.yml`
- DB 보고: `docs/phase3-postgresql-infrastructure.md`
- Phase 4 장애 기록: `docs/phase4-secure-import-migration.md`
- 현재 Git 이력: `.git` 부재로 검증 불가
