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
uv run --with minify-html --with rjsmin --with rcssmin python <빈 폴더>/minify_web.py <빈 폴더>   # 화면 코드 경량화(2026-10-09)
cd <빈 폴더>
vercel deploy --prod          # 웹 (처음 한 번 vercel link --project toolscout)
railway up --service <크론 서비스> --detach   # 크론 (처음 한 번 railway link)
```
- 경량화는 임시 폴더의 `web/`만 줄인다(주석 제거·공백 축소, `/*!` 고지는 남김, 이름 바꾸기는 안 함). 저장소 원본은 그대로.
  배포 전에 `uv run python -m tests.web.check_minify`가 줄인 결과의 `node --check`와 Edge 화면 열기를 확인한다
- 보호 장치 1차(2026-10-09): 운영(`DEV_MODE=0`)은 `/docs`·`/redoc`·`/openapi.json`이 닫히고, `/static`은 허용 목록 파일만 열린다. 자세한 것은 `routes/protect.py`
- 첫 점검: `python -m pipeline.cron --rehearse 2000-01-08`을 한 번 돌리면 검수용 날짜로 관리자만 실행·발송한 뒤 그 날짜를 지운다
  (메일 제목이 "1월 8일 AI 브리핑"으로 온다)

## 보호 장치 2차: 워터마크 · 함정 링크 · 요청 수 제한 (2026-10-09 사용자 결정, JS 난독화는 안 함)
세 장치 모두 환경변수 없이 켜진다. 기준을 바꿀 때만 Vercel 환경변수를 쓴다: `RATE_LIMIT_USER`(로그인 사용자 분당, 기본 120) `RATE_LIMIT_ANON`(비로그인 분당, 기본 30) `RATE_LIMIT_OFF=1`(끄기, 검수 전용. 운영에는 넣지 않는다).
`SESSION_SECRET`이 바뀌면 이미 나간 글의 워터마크를 풀 수 없고 차단 기록도 맞지 않게 되니 바꾸지 않는다.

| 장치 | 막는 것 | 못 막는 것 |
|---|---|---|
| 워터마크 (`routes/watermark.py`) | 카드 글·메일이 통째로 복사돼 퍼졌을 때 어느 계정에서 나왔는지 추적 | 손으로·AI로 다시 쓴 글, 0폭 문자를 지우는 도구를 거친 글, 짧은 구절만 베낀 글 |
| 함정 링크 (`routes/guard.py`) | robots.txt를 무시하고 모든 링크를 따라가는 봇 24시간 차단 | 링크를 가려 보는 봇, IP·UA를 바꿔 가는 봇, 로그인한 채 긁는 사람 |
| 요청 수 제한 (`routes/guard.py`) | 짧은 시간에 API를 대량 호출하는 긁어 가기 | 분당 기준 아래로 천천히 긁는 것, 계정을 여러 개 만들어 나눠 긁는 것 |

- 워터마크: 로그인 사용자에게 가는 브리핑 카드 글(요약·나한테는·이유·장점·단점, 제목·링크 제외)과 검색 결과 요약, 그 사용자 메일 본문 끝에 0폭 문자 20개. 데모는 "데모" 고정 표식. DB 원문에는 넣지 않는다.
  의심 글 해독(관리자, 로컬 `.env`로): `uv run python -m routes.watermark "<글>"` 또는 `--file 글.txt`. 표식이 없거나 일부만 남으면 그렇게 알려 준다
- 함정: 숨김 링크 `/archive/full-index`는 login·signup·demo·index·history·settings에만 있고 메일에는 없다. robots.txt가 막은 경로라 정상 검색엔진은 오지 않는다.
  부르면 IP+User-Agent의 HMAC을 `blocked_clients`에 24시간 적고 그 클라이언트는 robots.txt 말고 403이다. 로그인 세션 쿠키가 있으면 막지 않는다(같은 회사 공유기 뒤 사용자 보호).
  **같은 IP와 같은 브라우저 종류를 쓰는 로그인 안 한 사람도 같이 막힐 수 있다**(공유 IP + 같은 UA). 풀어 주려면 아래 SQL
- 제한: 브리핑·검색·지난 브리핑·데모 API(`/api/briefings*` `/api/search` `/api/demo/briefing`)를 `rate_counters`에 1분 창으로 센다. 로그인·가입은 자체 제한이 있어 대상 아님.
  기준은 화면 한 번이 부르는 요청(오늘 화면 1~2개, 지난 브리핑 2~3개, 검색은 입력할 때마다 1개)의 수십 배라 정상 사용은 걸리지 않는다. DB가 느리거나 실패하면 막지 않고 통과(로그 `요청 수 세기 실패`·`차단 확인 실패`)

### 개인정보 메모
- IP와 User-Agent 원문은 저장하지 않는다. `blocked_clients.client_hash`는 SESSION_SECRET HMAC 앞 32자뿐이라 값에서 IP를 되찾을 수 없다. 함께 적는 것은 부른 경로·횟수·시각뿐
- 차단은 24시간 뒤 풀린다(`expires_at`). 만료된 행은 다음 함정 기록 때와 요청 수 제한의 가끔(약 1/100) 정리 때 지운다. `rate_counters`는 키(사용자 번호 또는 클라이언트 HMAC)·창 번호·횟수뿐이고 한 시간 지나면 지운다
- 워터마크 표식은 사용자 id를 HMAC한 값이라 글만 봐서는 누구인지 알 수 없고, 서버 비밀값을 가진 관리자만 계정과 맞춰 볼 수 있다

### 운영 확인 방법
1. 숨김 링크: 브라우저에서 `/login` 소스 보기로 `/archive/full-index` 링크가 있는지, Tab 키로 포커스가 가지 않는지 본다. `/robots.txt`에 `Disallow: /archive/full-index`가 있는지 본다
2. 함정 동작(내 IP가 24시간 막히니 휴대폰 데이터 등 다른 망에서, 확인 뒤 아래 SQL로 해제): `curl -i https://<주소>/archive/full-index`가 403, 곧바로 `curl -i https://<주소>/login`도 403, `/robots.txt`는 200
3. 차단 목록·해제 (Supabase SQL): `select client_hash, hits, blocked_at, expires_at from blocked_clients order by blocked_at desc;` 해제는 `delete from blocked_clients where client_hash = '<값>';`(서버가 차단 여부를 잠깐 기억해서 최대 1분 늦게 풀린다)
4. 요청 수 제한: 로그인 없이 `/api/demo/briefing`을 1분에 31번 부르면 31번째가 429(`Retry-After` 헤더, "요청이 너무 많아요" 안내). 같은 IP에서 로그인 사용자는 따로 센다
5. 워터마크: 본인 계정의 오늘 브리핑 카드 글을 복사해 `uv run python -m routes.watermark "<글>"`에 넣으면 본인 이메일이 나온다. 같은 글을 공백만 고쳐 붙여도 나오고, 다시 쓴 글은 "표식이 없어요"가 나온다
6. 앱이 DB 때문에 느릴 때는 Vercel 로그에서 위 경고 문구를 찾는다. 기본값 120·30은 `RATE_LIMIT_USER`·`RATE_LIMIT_ANON`으로 바꾼다

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
