# Import Confirm

`POST /api/imports/confirm`은 Preview 응답을 받지 않고 원본 CSV/XLSX와 UUID `Idempotency-Key`만 받습니다. Preview와 동일한 Parser/Validator를 다시 실행한 뒤 하나의 JDBC Connection에서 데이터 변경, 행별 결정 Audit, 성공 Summary를 함께 commit합니다.

- 학생 업무 키: 기존 Swing 로직과 같은 `name + school_name`
- 분반 업무 키: `name + class_type`
- 수업 업무 키: `classroom_id + lesson_date + exam_round`
- 결과 업무 키: `lesson_id + enrollment_id`
- 정책: 한 행이라도 검증/제약조건을 통과하지 못하면 전체 rollback
- 멱등성: `import_job.idempotency_key` UUID UNIQUE; 성공 요청의 재전송은 기존 Summary 반환
- 개인정보 최소화: 원본 파일명은 고정 문자열로 대체하고 파일/행 원문과 학생 식별 정보는 Audit/로그에 저장하지 않음

실패 Audit은 성공 데이터와 별도 transaction을 만들지 않기 위해 DB에 남기지 않습니다. 실패는 개인정보 없는 request ID와 error code 기반 HTTP 로그로만 관찰합니다. 향후 쿠키/세션 인증을 도입하면 상태 변경 endpoint에 CSRF 보호가 필요합니다.

기존 DB에는 `sql/migrations/002_import_confirm.sql`을 적용합니다. 스크립트는 학생 업무 키 중복이 있으면 중단하므로 운영자가 중복을 먼저 검토해야 합니다. rollback은 적용 전 DB 백업을 복원하거나, 애플리케이션 배포를 되돌린 후 새 컬럼/인덱스가 사용되지 않는 상태에서 별도 검토를 거쳐 수행합니다.
