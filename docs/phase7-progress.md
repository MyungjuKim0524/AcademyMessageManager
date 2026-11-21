# Phase 7 진행 상황

| 항목 | 내용 |
|---|---|
| 완료 Stage | 1~7 (자동화 검증 완료, 최종 보고서 `docs/phase7-lessons-attendance-grades.md`) |
| 마지막 주요 파일 | `backend/app/modules/academics/repository.py`(평가 목록 집계를 상관 서브쿼리로 변경), `frontend/src/features/classwork/*` |
| 마지막 테스트 | 2026-11-18: pytest 64 PASS, Ruff PASS, `alembic check` 차이 없음, Java 47 PASS/0 skip, Vitest 10 files 31 PASS, oxlint PASS, tsc+build PASS — 모두 테스트 DB(006) |
| 진행 중 | 없음 |
| 다음 작업 | 사용자 브라우저 E2E(시나리오 J, 보고서 §12-1) 결과 반영 → PASS 시 Phase 7 완료 판정 |
| 개발 DB Migration | 006 **적용 완료** (2026-11-18 승인, 백업 `pre006-20261118-004641.dump`, 데이터 지문 동일). FastAPI(새 코드)·Vite 기동 중 |
| 알려진 장애 | Git CLI 없음(diff BLOCKED). PowerShell `ErrorActionPreference=Stop` 환경에서 Alembic INFO 출력이 명령을 끊음 → `cmd /c ... 2>nul` 사용. jsdom에서 `getByRole` 매우 느림·antd 표 렌더 1초 초과 → 텍스트·라벨 조회, `asyncUtilTimeout` 10초 |

## 기존 테스트 기대값 변경 (의도된 스키마 추가에 따른 갱신)
- `tests/test_postgres_integration.py`: head revision 006, 신규 트리거 7개, 테이블 상태 허용 목록을 단계별로 명시
- `tests/test_db_safety.py`: ORM 테이블 목록에 `assessment`, `assessment_result` 추가
