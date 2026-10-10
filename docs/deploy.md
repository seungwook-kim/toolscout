# 배포: Vercel(웹) + Railway(예약 작업)

2026-10-07 사용자 결정 "vercel + railway 방향으로 진행". 웹 화면은 접속할 때만 도는 Vercel 함수, 아침 작업은 정해진 시각에만 켜졌다가 끝나는 Railway 크론. 둘은 같은 Supabase DB를 본다.

## 구조
| 어디 | 무엇 | 어떻게 |
|---|---|---|
| Vercel (Hobby, 프로젝트 `toolscout`, https://toolscout-five.vercel.app, 지역 bom1 = DB와 같은 뭄바이, framework fastapi) | `main.py` FastAPI 전체(화면·로그인·설정·피드백·질문창·/demo) | 요청이 올 때만. 함수 최대 300초 |
| Railway (Hobby, 프로젝트 `toolscout`, 서비스 `toolscout-cron`, 지역 싱가포르 `asia-southeast1-eqsg3a` = DB와 가까운 곳) | `python -m pipeline.cron` | KST 06:00~21:30 30분마다 켜져서 할 일만 하고 종료 (일정은 UTC `0,30 21-23,0-12 * * *`, 설정은 아래 "Railway 설정") |
| Supabase | DB | 둘이 같이 쓴다 |

- 웹은 하루 실행을 직접 돌리지 않는다(`JOBS_EXTERNAL=1`). "지금 만들기"는 `users.briefing_requested_at`에 요청만 남기고 크론이 30분 안에 만든다. `/api/w1` 실행·발송은 409
- 도구(MCP)는 두 곳 모두 같은 프로세스 안에서 메모리로 붙는다(`MCP_URL=inproc`). /mcp를 HTTP로 부르지 않는다
- 크론이 하는 일(시각과 DB만 보고 판단): 06:00 검증·DB 깨우기·월요일 합치기 / 07:00·07:30·08:00 브리핑 없는 사용자 실행(08:00에도 남으면 실패 알림) /
  매 차례 지난 알림 시각의 미발송 메일 발송 / 매 차례 "지금 만들기" 요청 처리. 이전 차례가 돌고 있으면 Railway가 이번 차례를 건너뛴다
- 서버는 운영 모드(`DEV_MODE=0`): 모델은 네 역할과 같은 소식 묶기 모두 첫 칸 Anthropic API `claude-haiku-5-5`(2026-10-11), 둘째 칸 OpenRouter `openai/gpt-4o-mini`(첫 칸이 429·5xx·타임아웃·키 없음이면 넘어감), 중요도는 Jev. 형식 실패를 줄이려고 Anthropic 구조화 출력을 쓴다. Haiku 5.5 가격은 입력 $0.10·출력 $0.50 per 1M(프롬프트 10만 토큰 이하, 넘으면 5배). 브리핑은 승인된 실제 사용자·관리자·데모 프로필만

## 환경변수 (값은 로컬 `.env`에서 옮기고 출력하지 않는다)
- 공통: `DATABASE_URL` `SESSION_SECRET`(메일 서명 링크를 웹이 확인하므로 둘이 같아야 한다) `ADMIN_EMAILS` `GMAIL_USER` `GMAIL_APP_PASSWORD`
  `ANTHROPIC_API_KEY`(Railway·Vercel 둘 다 필요, 운영 첫 모델) `OPENROUTER_API_KEY`(둘째 칸) `LANGFUSE_PUBLIC_KEY` `LANGFUSE_SECRET_KEY` `LANGFUSE_HOST` `MCP_SERVICE_KEY` `APP_BASE_URL`(= Vercel 주소),
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

## Railway 설정 (2026-10-09 확인)
- 이 서비스는 저장소의 `railway.json`(Config as Code)을 읽지 않았다. 10/9 첫 리허설에서 시작 명령이 안 먹고 Dockerfile 기본 명령(uvicorn 웹서버)이 떠서 바로 껐다.
  설정은 Railway의 새 방식(Infrastructure as Code, `.railway/railway.ts`)으로 `railway config apply`해서 넣는다.
  저장소에는 `.railway/` 폴더를 두지 않는다(새 최상위 폴더는 사용자 허락이 필요, CLAUDE.md 2번). 내보낸 임시 폴더에 아래 파일을 두고 적용한다
- 적용에 필요한 것: Node 22 이상(이 PC는 20이라 임시 폴더에 `npm i node@22`), 임시 폴더에 `npm i railway@3.13.1`(공식 SDK, 그냥 `railway`를 깔면 옛 2.x가 깔릴 수 있다),
  PowerShell에서 `$env:_`를 실제 `railway.exe` 경로로 두기(npm으로 깐 CLI는 .cmd라 SDK의 버전 검사가 실패한다). 먼저 `railway config plan`으로 바뀌는 것만 확인
- 리허설 때는 `start`를 `python -m pipeline.cron --rehearse 2000-01-08`로, 크론 일정 없이. 운영은 아래 내용
```ts
import { defineRailway, preserve, project, service } from "railway/iac";
export default defineRailway(() => {
  const toolscoutCron = service("toolscout-cron", {
    start: "python -m pipeline.cron",
    replicas: { "asia-southeast1-eqsg3a": 1 },   // DB(Supabase 뭄바이)와 가까운 싱가포르
    deploy: { cronSchedule: "0,30 21-23,0-12 * * *", restartPolicyType: "NEVER" },   // UTC. KST 06:00~21:30 30분마다
    env: { /* 변수는 railway config pull로 받은 preserve() 목록 그대로 둔다(값은 파일에 안 쓴다) */ },
  });
  return project("toolscout", { resources: [toolscoutCron] });
});
```
- 변수를 CLI로 새로 넣었으면(`railway variable set`) 적용 전에 `railway config pull --force`로 다시 받아 preserve 목록을 맞춘다(빠진 변수가 지워지지 않게 plan에서 destroy가 없는지 본다)
- Hobby 플랜은 바깥 SMTP(25·465·587)가 막혀 있다 → 메일은 Gmail API(`MAIL_TRANSPORT=gmail_api`, 아래 절)

## 예외용 무료 대안: GitHub Actions (2026-10-09 사용자 결정: "예외로 사용할 수 있고 무료이다", 기본은 Railway)
- 무엇: GitHub이 정해진 시각에 저장소 코드를 대신 돌려 주는 기능. 비공개 저장소도 한 달 2,000분까지 무료라, Railway를 못 쓰게 되거나(요금·장애) 비용을 0으로 해야 할 때 아침 작업을 옮길 수 있다
- 하는 일은 같다: `python -m pipeline.cron`을 예약으로 돌리고, 메일은 Gmail API로 보낸다(SMTP 막힘과 상관없음). 이 PC는 관여하지 않는다
- 단점: 예약 실행이 혼잡하면 몇 분~수십 분 늦게 시작하고 드물게 건너뛴다 / 실행 서버가 미국이라 뭄바이 DB와 멀어 느리다(Railway 싱가포르 9분 → 20~30분 예상) /
  무료 2,000분 중 대략 한 달 1,000분 안팎을 쓸 것으로 예상(여유가 크지 않다) / 비밀값을 저장소 Secrets에 따로 넣어야 한다
- 옮길 때: `.github/workflows/`에 예약 워크플로(UTC cron, 정각을 피해 몇 분 어긋나게)를 만들고, Railway 변수와 같은 값을 Secrets에 넣고, Railway 크론은 끈다(둘 다 켜면 하루 실행이 두 번 돈다)

## 이 PC 앱에서 넘어가기 (2026-10-07 사용자 결정 "서버 첫 발송 확인 뒤 끄기")
1. 서버 점검 메일이 정상으로 오는지 확인
2. 이 PC 앱의 예약을 끈다(`SCHEDULER_ENABLED=0`으로 앱을 다시 띄우거나 작업 `toolscout app` 중지). 둘 다 켜 두면 먼저 돈 쪽이 보내고
   다른 쪽은 건너뛰지만(발송은 sent_at 기준 멱등) 하루 실행이 두 번 돈다
3. 되돌리기: Railway 크론 서비스를 멈추고 이 PC 앱 예약을 다시 켠다

## 남은 일
- `railway.json`(Config as Code)은 2026-12-01까지만 받는다는 경고가 있지만, 이 서비스는 이미 IaC로 설정한다(위 "Railway 설정"). 저장소의 `railway.json`은 기록용으로만 남아 있다
- 임시 비밀번호(2026-10-08 사용자 결정 "구글 붙이기 전 기존 계정 모두 123456, 디자인·기능 다 되면 지우고 제대로"): 그때 있던 계정
  id 45·1·2·3·113·232의 password_hash를 123456으로 넣었다(로컬·Vercel 같은 DB). 끝나면 이 계정들의 password_hash를 비우고
  본인 계정은 회원가입 화면(인증번호)이나 구글로 다시 정한다. 공개 주소라 그동안은 본인 이메일을 아는 사람이 관리자로 로그인할 수 있다

## Gmail API로 메일 보내기 (2026-10-09 사용자 결정 "Gmail API로 보내기")
Railway Hobby는 바깥 SMTP(25·465·587)를 막는다. 10/9 서버 리허설이 `OSError: [Errno 101] Network is unreachable`로 실패했고 공식 정책도 같았다. 그래서 같은 Gmail 계정을 HTTPS(Gmail API)로 쓴다. 새 서비스는 필요 없다. 이 PC 앱과 Vercel은 기본 `smtp` 그대로 둔다.

### 환경변수
- Railway: `MAIL_TRANSPORT=gmail_api`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`(로컬 `.env`·Vercel과 같은 값), `GMAIL_USER`(보내는 관리자 Gmail), `SESSION_SECRET`(Vercel과 같아야 한다. 토큰 암호화 키가 여기서 나온다). `GMAIL_APP_PASSWORD`는 이 방식에선 안 쓴다
- Vercel: 연결 화면만 쓰므로 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`·`GMAIL_USER`·`SESSION_SECRET`(이미 있음). `MAIL_TRANSPORT`는 넣지 않아도 되지만, 넣으면 웹이 보내는 가입 알림·인증번호 메일도 Gmail API로 나간다
- `SESSION_SECRET`을 바꾸면 저장된 토큰이 풀리지 않아 "연결 안 됨"으로 보인다. 그때는 다시 연결한다

### 처음 한 번 하는 순서
1. 구글 클라우드 콘솔에서 이 OAuth 프로젝트에 **Gmail API 사용 설정**(API 및 서비스 > 라이브러리 > Gmail API > 사용)
2. OAuth 동의 화면의 게시 상태를 **프로덕션**으로 둔다. '테스트' 상태면 refresh_token이 7일 뒤 만료돼 아침 메일이 끊긴다. 브랜딩에는 승인된 도메인 `toolscout-five.vercel.app`, 홈페이지 `https://toolscout-five.vercel.app/demo`(또는 `/login`), 개인정보처리방침 `https://toolscout-five.vercel.app/privacy`, 서비스 약관 `https://toolscout-five.vercel.app/terms`를 넣는다(로그인 없이 열린다. 방침의 문의 메일 주소 자리는 `web/privacy.html`에서 채운다). 리디렉션 URI는 지금 등록된 `https://toolscout-five.vercel.app/auth/google/callback`을 그대로 쓴다(새로 만들지 않음)
3. 새 표 `app_secrets`를 만든다(코드 배포 전에 한 번): `uv run python -c "import db; db.init_db()"` (이미 있는 표는 건드리지 않고 없는 표만 만든다)
4. Vercel에 새 코드를 배포하고, 관리자 계정으로 로그인한 채 https://toolscout-five.vercel.app/admin/gmail/connect 를 연다(관리자 화면 상단 "Gmail 발송 연결" 줄의 [연결하기]도 같다)
5. 구글 화면에서 **보내는 계정(`GMAIL_USER`)**을 고르고 허용한다. 다른 계정을 고르면 저장하지 않고 "보내는 계정(GMAIL_USER)으로 로그인해 주세요"가 뜬다
   - '확인되지 않은 앱' 경고가 나오면 본인이 만든 앱이라 **고급 > (앱 이름)으로 이동**으로 넘어간다
   - "구글이 연결 토큰을 주지 않았어요"가 나오면 이미 허용한 적이 있는 것이다. 구글 계정 > 보안 > 서드파티 앱 및 서비스에서 toolscout를 삭제하고 다시 연결한다
6. 관리자 화면에 "연결됨 · 시각"이 보이면 끝. Railway에 `MAIL_TRANSPORT=gmail_api`를 넣고 `python -m pipeline.cron --rehearse 2000-01-08`로 다시 점검한다

### 문제가 생기면
- 발송 결과 mode가 `gmail_api`면 정상 경로. `config_missing`이면 연결이 없는 것(실패 사유 "Gmail 연결 안 됨"). 이때는 실패 알림 메일도 같은 길이라 나가지 못하고 로그(`메일을 보낼 수 없음`)에만 남는다
- 실패 사유 "Gmail 연결이 끊김"은 동의 취소·만료(invalid_grant). 4번부터 다시 한다. 그동안 미발송 메일은 sent_at이 비어 있어 연결 뒤 다음 차례에 나간다
- 토큰은 `app_secrets`(name `gmail_refresh_token`)에 AES-GCM으로 암호화돼 있다. 지우려면 그 행을 삭제하거나 구글 계정 > 서드파티 앱에서 연결을 끊는다
