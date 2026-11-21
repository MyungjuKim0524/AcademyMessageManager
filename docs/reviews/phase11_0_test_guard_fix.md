# Phase 11-0 — PostgreSQL 통합 테스트 스크립트 안전장치 수정

작업일: 2026-11-20 · 대상: `scripts/run-postgres-integration.ps1` · 발견: `phase10_5_c2_results.md` 8절

## 원인 (Windows PowerShell 5.1.26100에서 실측)
1. **인자 손상**: PS 5.1은 네이티브 프로그램 인자 안의 `"`를 이스케이프하지 않는다. 그래서 `--format '{{index .Config.Labels "academy.environment"}}…'`가 `{{index .Config.Labels academy.environment}}…`로 전달된다(인자 출력 프로그램으로 확인). docker는 `template parsing error: function "academy" not defined`, **exit 64, 출력 없음**.
2. **종료 코드 무시**: `$ErrorActionPreference = 'Stop'`은 네이티브 명령의 0이 아닌 종료 코드에서 멈추지 않는다(실측: 이후 줄 계속 실행).
3. **실패 시 통과(fail-open)**: 결과가 `$null`이면 `$null -notmatch '…'`가 참이 아닌 빈 값이 되어 `-or`로 묶인 세 부정 검사가 모두 거짓이 된다. 그래서 `throw`하지 않는다.

결과적으로 원본 스크립트는 **라벨·포트 검사를 항상 건너뛰었다**. 그 뒤의 DB 이름·사용자 검사(`psql SELECT`)와 연결 URL의 고정 포트 55432만 남아 있었다.

## 수정 (해당 블록만, 다른 줄 변경 없음)
- Go 템플릿을 넘기지 않는다. `docker inspect <컨테이너>`의 기본 JSON을 `ConvertFrom-Json`으로 읽어 따옴표 문제 자체를 없앴다(PS 5.1/7 공통).
- **양성 검사(fail closed)**: 다음을 모두 만족해야 통과한다.
  - 종료 코드 0이고 출력이 비어 있지 않다.
  - JSON이 유효하다.
  - 결과가 정확히 1개이고 이름이 `/academy-learningops-postgres-test`이다.
  - `academy.environment`가 정확히 `isolated-test`이다(대소문자 구분).
  - `academy.destructive-tests`가 정확히 `allowed`이다.
  - 5432/tcp 바인딩이 정확히 `127.0.0.1:55432` 하나이다(0.0.0.0 추가 바인딩도 거부).
- **기존 DB 검사 유지 + 강화**: 같은 `psql SELECT current_database()||'|'||current_user` 검사를 유지한다. 여기에 종료 코드 0과 빈 결과 거부를 추가했다(기존에는 빈 결과면 `.Trim()` 예외로 멈췄음 → 이제 명시적 거부 메시지). 연결 URL의 DB 이름·사용자·포트는 변경 없음.

## 검증 (Windows PowerShell 5.1에서 실제 실행)
샌드박스(D 드라이브 scratchpad) 복사본으로 실행했다. 샌드박스에는 `backend\.venv`(pytest)와 Java 프로젝트가 없다. 그래서 검사를 모두 통과하더라도 테스트·DB 초기화는 **실행될 수 없다**. "REACHED_PYTEST"는 모든 검사를 통과해 pytest를 시작하려 한 지점을 뜻한다.

| 구분 | 사례 | 결과 |
|---|---|---|
| 모킹(docker를 함수로 대체, 호출 기록) | 정상 1 + 거부 21 (개발 라벨, destructive=forbidden, 라벨 없음/누락, 대소문자·접미사 다름, 포트 55431, 0.0.0.0, 추가 공개 바인딩, 바인딩 없음, 다른 컨테이너 이름, inspect 실패 exit 1, 템플릿 오류 exit 64, exit 0 빈 출력, `[]`, 잘못된 JSON, DB 이름 다름, DB 사용자 다름, psql 실패, psql 빈 출력, psql 정상 문자열이지만 exit 1) | **22/22 기대대로**. 거부 사례에서 docker 호출은 `inspect`와 읽기 전용 `SELECT`뿐이고 pytest 단계에 도달한 사례는 0 |
| 모킹 · 원본 스크립트 | inspect 실패/템플릿 오류/빈 출력(13·14·15) | 3건 모두 **검사를 통과해 pytest 단계 도달** — 결함 재현 |
| 실제 docker · 정상 | 격리 테스트 컨테이너 | 검사 통과 → pytest 단계(호출: inspect, SELECT) |
| 실제 docker · 잘못된 라벨 | `academy-learningops-postgres-dev`(isolated-development/forbidden, 55431) | inspect 1회 후 거부, exec 없음 |
| 실제 docker · 명령 실패 | 존재하지 않는 컨테이너 이름 | 직접 실행 시 "failed (exit 1)" 거부, exit code 1 |
| 컨테이너 상태 | 테스트·개발 컨테이너 시작 시각·재시작 횟수 | 전후 동일. `academy-postgres` 접근 없음 |
| 구문 | PS 5.1 파서 | 오류 0 |

## 실행하지 않은 것
- **PowerShell 7**: 이 PC에 설치되어 있지 않아 **미검증**이다. 코드상으로는 템플릿 인자가 없고 `ConvertFrom-Json`을 `@()`로 감싸 PS 7의 배열 열거 차이와 무관하다. 사용한 연산자(`-cne`, `$LASTEXITCODE`)도 7에서 동일하다. 다만 실행으로 확인하지는 않았다.
- **실제 스크립트로 통합 테스트 전체 실행**: 이번 지시(테스트 중 DB 초기화 금지)에 따라 하지 않았다. 다음 정상 실행 시 첫 단계에서 확인된다.

## 남은 위험
- 하네스에서 `*> $null`로 리디렉션하면 PS 5.1이 docker의 stderr를 종료 오류로 바꿔 거부 메시지 전에 멈춘다(안전한 쪽). 직접 실행에서는 명시적 거부 메시지가 나온다(확인함).
- 검사와 테스트 시작 사이에 컨테이너가 바뀌는 경쟁은 막지 못한다(로컬 단일 사용자 환경에서 무시 가능).
- 라벨은 compose 파일이 붙이는 값이므로, compose 파일을 잘못 고치면 보호가 약해진다. 최종 방어선은 DB 이름·사용자 검사와 고정 포트다.
- 백업: 수정 전 원본 `scratchpad\p110\run-postgres-integration.ps1.orig-backup`(수정 전 SHA-256 `A0750F34…2C5A`와 일치 확인).
