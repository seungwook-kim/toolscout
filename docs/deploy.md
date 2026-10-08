# 배포: Vercel(웹) + Railway(예약 작업)

2026-10-07 사용자 결정 "vercel + railway 방향으로 진행". 웹 화면은 접속할 때만 도는 Vercel 함수, 아침 작업은 정해진 시각에만 켜졌다가 끝나는 Railway 크론. 둘은 같은 Supabase DB를 본다.

## 구조
| 어디 | 무엇 | 어떻게 |
|---|---|---|
| Vercel (Hobby, 프로젝트 `toolscout`, https://toolscout-five.vercel.app, 지역 bom1 = DB와 같은 뭄바이, framework fastapi) | `main.py` FastAPI 전체(화면·로그인·설정·피드백·질문창·/demo) | 요청이 올 때만. 함수 최대 300초 |
| Railway (크론 서비스) | `python -m pipeline.cron` | KST 06:00~21:30 30분마다 켜져서 할 일만 하고 종료 (`railway.json`, 일정은 UTC `0,30 21-23,0-12 * * *`) |
| Supabase | DB | 둘이 같이 쓴다 |

- 웹은 하루 실행을 직접 돌리지 않는다(`JOBS_EXTERNAL=1`). "지금 만들기"는 `users.briefing_requested_at`에 요청만 남기고 크론이 30분 안에 만든다. `/api/w1` 실행·발송은 409
- 도구(MCP)는 두 곳 모두 같은 프로세스 안에서 메모리로 붙는다(`MCP_URL=inproc`). /mcp를 HTTP로 부르지 않는다
- 크론이 하는 일(시각과 DB만 보고 판단): 06:00 검증·DB 깨우기·월요일 합치기 / 07:00·07:30·08:00 브리핑 없는 사용자 실행(08:00에도 남으면 실패 알림) /
  매 차례 지난 알림 시각의 미발송 메일 발송 / 매 차례 "지금 만들기" 요청 처리. 이전 차례가 돌고 있으면 Railway가 이번 차례를 건너뛴다
- 서버는 운영 모드(`DEV_MODE=0`): 모델은 OpenRouter `openai/gpt-4o-mini`(네 역할), 같은 소식 묶기도 같은 모델, 중요도는 Jev. 브리핑은 승인된 실제 사용자·관리자·데모 프로필만

## 환경변수 (값은 로컬 `.env`에서 옮기고 출력하지 않는다)
- 공통: `DATABASE_URL` `SESSION_SECRET`(메일 서명 링크를 웹이 확인하므로 둘이 같아야 한다) `ADMIN_EMAILS` `GMAIL_USER` `GMAIL_APP_PASSWORD`
  `OPENROUTER_API_KEY` `LANGFUSE_PUBLIC_KEY` `LANGFUSE_SECRET_KEY` `LANGFUSE_HOST` `MCP_SERVICE_KEY` `APP_BASE_URL`(= Vercel 주소),
  `DEV_MODE=0` `SCHEDULER_ENABLED=0` `MCP_URL=inproc`
- Vercel만: `JOBS_EXTERNAL=1` `DAILY_QUESTION_LIMIT`
- Railway만: `JEV_API_KEY` `E2B_API_KEY` `GITHUB_TOKEN` `SKILLSMP_API_KEY` `DAILY_PROBE_LIMIT`

## 올리는 방법
로컬 전용 파일(`.env`, `CLAUDE.md` 등)이 섞이지 않게 git에 올린 파일만 내보낸 폴더에서 배포한다.
```
git archive --format=tar main | tar -x -C <빈 폴더>
cd <빈 폴더>
vercel deploy --prod          # 웹 (처음 한 번 vercel link --project toolscout)
railway up --service <크론 서비스> --detach   # 크론 (처음 한 번 railway link)
```
- 첫 점검: `python -m pipeline.cron --rehearse 2000-01-08`을 한 번 돌리면 검수용 날짜로 관리자만 실행·발송한 뒤 그 날짜를 지운다
  (메일 제목이 "1월 8일 AI 브리핑"으로 온다)

## 이 PC 앱에서 넘어가기 (2026-10-07 사용자 결정 "서버 첫 발송 확인 뒤 끄기")
1. 서버 점검 메일이 정상으로 오는지 확인
2. 이 PC 앱의 예약을 끈다(`SCHEDULER_ENABLED=0`으로 앱을 다시 띄우거나 작업 `toolscout app` 중지). 둘 다 켜 두면 먼저 돈 쪽이 보내고
   다른 쪽은 건너뛰지만(발송은 sent_at 기준 멱등) 하루 실행이 두 번 돈다
3. 되돌리기: Railway 크론 서비스를 멈추고 이 PC 앱 예약을 다시 켠다

## 남은 일
- Railway가 `railway.json`(Config as Code)을 2026-12-01까지만 받는다고 알린다(2026-10-07 `railway add` 경고). 그 전에 `.railway/railway.ts`(Infrastructure as Code)로 옮긴다 (`railway config migrate`)
- 임시 비밀번호(2026-10-08 사용자 결정 "구글 붙이기 전 기존 계정 모두 123456, 디자인·기능 다 되면 지우고 제대로"): 그때 있던 계정
  id 45·1·2·3·113·232의 password_hash를 123456으로 넣었다(로컬·Vercel 같은 DB). 끝나면 이 계정들의 password_hash를 비우고
  본인 계정은 회원가입 화면(인증번호)이나 구글로 다시 정한다. 공개 주소라 그동안은 본인 이메일을 아는 사람이 관리자로 로그인할 수 있다
