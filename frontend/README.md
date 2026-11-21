# Academy LearningOps Frontend

학원 직원(관리자·선생님·조교)이 쓰는 React 웹 화면입니다. FastAPI 백엔드(`../backend`)의 `/api`를 호출합니다.

구성: React 19, TypeScript, Vite, Ant Design, Axios, TanStack Query, React Router(`createBrowserRouter`, 지연 로딩)

## 화면(라우트)

| 경로 | 화면 | 비고 |
|---|---|---|
| `/login` | 로그인, 재설정 코드로 비밀번호 설정 | 세션 만료 안내 표시 |
| `/` | 대시보드 | |
| `/students` | 학생·반 관리(관리자) / 담당 반 학생 | 탭: 전체 학생·반별 학생. 보호자 이메일은 "메일 주소 변경"에서 수정(관리자) |
| `/classes` | 수업·출결·성적 | |
| `/analytics` | 출결·성적 분석 | 출결 입력 완료율·출석률 등 |
| `/notifications` | 엑셀 기반 성적 안내 메시지 생성 | 탭: 엑셀 업로드·검토·발송·누락·예외 생성·메시지 처리 현황·템플릿. 발송은 **모의 발송**(실제 전송 없음) |
| `/staff` | 직원·담당 반 배정 | 관리자 전용 |
| `/messages/preview` | 메시지 미리보기(초기 Java 계약 유지 화면) | 메뉴 없음 |
| `/message-operations` | `/notifications?tab=operations`로 이동 | 이전 주소 호환 |
| `/deliveries` | 발송 이력 | 준비 중 화면 |

화면의 메뉴 숨김·역할 분기는 편의 기능입니다. 권한은 서버가 판정합니다(`backend/README.md` "직원 인증과 DB API 제한").

## 실행

FastAPI 백엔드를 먼저 `127.0.0.1:8000`에서 실행합니다(저장소 루트의 `scripts/start-fastapi.ps1`). 그다음 다음 명령을 사용합니다.

```powershell
npm ci
npm run dev
```

- 개발 서버는 `http://127.0.0.1:5173`이고, `/api` 요청을 FastAPI(`127.0.0.1:8000`)로 프록시합니다(`vite.config.ts`).
- `VITE_API_BASE_URL`은 비워 둡니다. 같은 출처의 `/api`로 호출해야 세션 쿠키(SameSite=Lax)가 동작합니다.
- 배포 구성은 `../docs/deployment/phase11_5_security_deployment_guide.md`를 따릅니다(Vercel Rewrite로 `/api`를 백엔드에 연결).
- 비밀값은 Vite 환경변수에 넣지 않습니다.

## 검증

```powershell
npm run lint
npm test        # Vitest 전체(수 분 소요)
npm run build   # tsc -b + vite build
```

브라우저 저장소에는 학생 정보나 생성 메시지를 저장하지 않습니다. 마지막으로 선택한 작업 반만 sessionStorage에 둡니다.
