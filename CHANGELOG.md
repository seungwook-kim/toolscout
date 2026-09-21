# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 10 · 2026-09-21 · 최신 뉴스 누락 원인(뉴스 창 24시간)과 프로필 제외 규칙
  - 사용자 제보: 메일 뉴스와 지난 브리핑 화면이 다르다 / 요즘 화제인 Jev가 브리핑에 한 번도 안 나온다 / Java 소식은 빼고 싶다
  - 확인: 메일·화면 차이는 개발 모드 묶음 메일이 프로필 4개를 한 통에 담고 화면은 본인 것만 보여서다(코드 정상, 9월 20일 본인 카드 7장 일치).
    뉴스 출처는 실재(techcrunch·aitimes 원문 제목 대조 일치). 하루 뉴스는 5~9건이고 후보 140건의 대부분은 MCP다
  - 원인: 하루 1회 07:00 실행에 뉴스 창이 24시간이라 기사가 후보에 오를 기회가 한 번뿐이었다.
    9월 17일 17시 36분 Jev 공개 기사가 9월 18일 실행에서 밀린 뒤 19일·20일 창 밖으로 나가 다시 후보가 되지 못했다
  - 끝난 것: NEWS_WINDOW 48시간, 큐레이터 PICK_PROMPT 제외 규칙 한 줄, 개발자 프로필 자유 한 줄에 JVM 생태계 제외
  - 검수: check_news_window 10항목(신규)·check_fallbacks·check_scheduler·check_deliver·check_folder_docs 통과
  - 실측(로컬 gemma3:12b): 오늘 후보에 Jev 기사 9건 수집 → 선별 8건 통과 → 후보 풀 7건 → 개발자 프로필 최종 1건 선택
  - 미완·주의: run_daily --fake의 관련 카드 3항목이 이번 변경 전부터 실패한다(월요일 F3-b, main에서도 동일). 오늘 07:00이 첫 월요일 실행이다.
    48시간 창이라 선별 묶음이 약 2배(뉴스 112건 → 200건 안팎)가 된다. 개발 모드는 로컬 모델이라 한도 영향 없음
  - 배포 논의(결정 아님, 기록만): 배포처는 Railway(Hobby $5/월, 자동 도메인·HTTPS 포함). Vercel은 컨테이너도 함수로 돌아
    상주 스케줄러와 28분 실행을 못 담아 제외. 전시 링크는 /demo, 실사용자를 안 받는 동안 DEV_MODE=1 유지
  - OpenRouter gpt-oss-20b 실측(유료 키): 선별 20건 5.0초(로컬 18.2초의 3.6배)·JSON 규격 맞음·도구 호출 지원·한국어 자연스러움,
    3회 $0.00016. reasoning은 low 필수(none은 400, 미지정이면 출력 약 3배). 모델표에는 넣지 않고 models.py 주석으로만 남김
  - 다음 시작점: 오늘 07:00 실행에서 Jev 카드 실제 확인 → 관련 카드 3항목 고치기 → 묶음 메일 본인 구역 순서(사용자 결정 대기)
    → 11월 배포 전 해설가 반려율(백엔드 7건 중 6건) 낮추기

- 세션 9 · 2026-09-16 · 개발 모드 메일 묶기, 검증관·되돌림 main 머지, OpenRouter meta 제공자, 초대제 가입과 공개 데모 /demo
  - 결정(사용자): 개발 모드 메일은 프로필마다 한 통이 아니라 전부 묶어 한 통 / 가입은 초대제(코드 입력 전에는 초대 화면만) / 로그인 없이 보는 읽기 전용 데모 /demo
  - 끝난 것: briefing_mail.combine과 deliver 묶음 발송(실패하면 그날 전부 미발송, 운영 모드는 사용자별 한 통 그대로),
    feat/verifier·feat/mail-single main 머지와 앱 재시작(내일 06:00 W1-a부터), providers의 meta 공급자(OpenRouter 경유 Muse Spark)와 학습 티어 정책(allow_user_text),
    invite_codes 표·users.status·is_demo·invite_code_used, routes/invite.py·demo.py, 화면 invite·admin·demo, cards.js readonly, robots.txt·noindex
  - 검수: check_access 30항목(신규)·check_deliver 27·check_tables·check_auth·check_rules·check_design·check_ask·check_settings·check_briefings·check_feedback·
    check_main·check_scheduler·tests.pipeline.run_daily --fake·check_models·check_folder_docs·check_readme 통과
  - 실제 확인: 오늘(9/16) 브리핑 4통을 묶음 한 통으로 재발송(프로필 4개·카드 15장, 실패 0), 데모 프로필(user 113) 하루 실행 1명분으로 카드 7장 생성
  - 막힌 것: OpenRouter가 Muse Spark 계열에 403 "requires 18+ age confirmation"(계정 설정). 확인 뒤 tests/models/try_muse.py를 다시 돌리면 된다.
    OpenCode Zen 직결은 무료 등급이 앱 밖 호출을 막아(400 MissingSessionID) feat/opencode 브랜치에 둔 채 접었다
  - 바로잡음: gate.py 주석의 모델명(모델표 밖 하드코딩 금지 규칙) 제거로 check_models 통과
  - 미완·주의: 데모는 "가장 최근 발송 브리핑" 대신 "가장 최근 브리핑"을 보여 준다(데모 프로필은 가짜 주소라 메일을 안 보낸다).
    계정 삭제만 승인 전에도 열어 뒀다. 공개 MCP 키 발급 API는 아직 없어 초대 검문을 붙일 자리도 없다
  - 다음 시작점: 9/17 06:00 W1-a·07:00 실행·08:00 묶음 메일 확인 → OpenRouter 18+ 확인 뒤 Muse Spark 시험 → 배포 주소(APP_BASE_URL)와 초대 코드 첫 발급

- 세션 8 · 2026-09-16 · 검증관(E2B 4단계·SKILL.md 판독)과 되돌림 두 개, 06:00 검증 예약 W1-a (feat/verifier, 9/16 08:00 뼈대 확인 뒤 머지)
  - 결정(사용자): 검증 코드는 agent/ 아래(probe.py·skill_check.py·verifier.py), 요청은 새 표 verify_requests, 브랜치에서 진행하고 머지는 확인 뒤
  - 끝난 것: tests/e2b/smoke·mcp/sandbox_probe(샌드박스 안 stdio·HTTP MCP 클라이언트), probe_mcp(설치 90초·실행 30초·차단 뒤 도구 목록·인증, curl류 거부, 하루 30건, probes), read_skill(GitHub·SkillsMP 10,000자·<data>·정규식 5종 인용), 검증관(레지스트리 설치 정보는 모델 없이, 없을 때만 README 판단, 스킬은 모델·정규식 다르면 확인 필요, 공식은 생략), 카드·메일 고정 문구 두 개, 되돌림 1(실패 도구 → 큐레이터 대체·비움)·2(근거 없는 도구 카드 → 재검증 → 다시 해설 → 확인 필요), 06:00 W1-a(따로 도는 작업)
  - 검수: check_probe 10(실제 E2B)·check_skill_read 13·check_verifier 21·check_rollback 16·check_scheduler(검증 5 추가)·run_daily --fake·check_deliver·check_design·check_tables 통과
  - 실제 검증 5건(도구 목록 8건에서 큐레이터 선택): 처음 평균 124초·최대 236초 → 판단 단계가 항목당 약 200초(모델이 설치 정보가 있어도 README 두 번, 30초 제한 반복)라 registry_plan으로 바꾼 뒤 5건 합계 129초·평균 26초
    - MCP 단계(고친 뒤 서로 다른 6건): 설치 2/2(npm·pypi), 실행 2/2, 도구 목록 2/4(원격 2건은 토큰 필요로 401), 인증 필요 2·불필요 2, 실측 불가 2(자리표시자 주소·nuget). aihawk 37초 도구 16개, desktop-commander 73초 도구 26개
    - desktop-commander는 샌드박스 Node 20.9에서 require(esm)로 실행 실패 → npm 설치 전 Node 22 준비(약 6초)로 4단계 성공
    - 스킬 1건(anthropics 공식): 위험 신호 생략, 충실도 높음 27초. 도구 목록에 커뮤니티 스킬이 없어 정상·주의 분포는 실제로 못 봄(3단계 실제 스킬 6개 정규식 오탐 0)
    - 되돌림: 실제 하루 실행(--users 1 --limit 40, 검수 날짜 2000-01-11, 끝나고 삭제) 403초·호출 11(ollama 4·groq 7)·429 1회·형식 실패 0에서 되돌림 1 0회·2 0회. 실패 검증이 없었고 도구 카드 2장이 근거 확인 전에 반려됨. 발동 경로는 check_rollback으로만 확인
  - 바로잡음: save_requests 저장 수가 rowcount -1로 -5 보고 → returning으로 셈
  - 미완·주의: 해설가 반려가 여전히 많음(백엔드 프로필 7건 중 6건), 같은 저장소 링크의 레지스트리 항목 두 개(Agent-Native Plan·Slides)가 한 사용자 계획에 같이 들어감, 원격 MCP는 토큰 없이 도구 목록을 못 봄(인증 필요로 표시)
  - 다음 시작점: 9/16 08:00 메일 확인 → feat/verifier 머지·앱 재시작(다음 날 06:00 W1-a부터) → OpenCode Zen 제공자 → 초대제 가입·/demo

- 세션 7 (디자인) · 2026-09-15 · 웹앱 화면을 docs/design-reference.html 기준으로, 화면용 읽기 전용 데이터, PWA (main 머지 완료)
  - 끝난 것: app.css는 참고 파일 style 그대로 + 토큰만 쓴 보충, 오늘 브리핑 마스트헤드·파이프라인 3칸·.item/.tool·질문 스레드·고정 입력바, 지난 브리핑(날짜별 접힘)·설정·로그인·피드백 같은 마스트헤드, briefings.run_stats·items.published_at·API item_meta(사용자 승인), manifest·아이콘 192/512
  - 검수: tests/web 7종(check_design 신규), check_main·check_tables·check_deliver·부록 C 통과, 폰 390·PC 1280 가로 넘침 0, Page.getAppManifest·설치 가능 여부 오류 0, CI success
  - 방식: 서브에이전트(소넷5)가 다른 화면 4개·PWA·검수 스크립트, 메인(오푸스5)이 검증과 수정(검수 스크립트 CSS 검사 범위 오류, 설정 label·hidden·슬라이더 열)
  - 미완·주의: 실제 폰 홈 화면 추가는 외부 주소 배포 뒤 확인(127.0.0.1이라 폰 접속 불가), run_stats·공개 시각은 9/16 실행부터 채워짐
  - 다음 시작점: 9/16 07:00·08:00 뼈대 완성 확인 → 검증관·되돌림(세션 8, 브랜치에서 먼저 진행)

- 세션 7 (W4) · 2026-09-15 · 예약 작업 W4: 재실행·실패 알림·DB 깨우기, 도구 목록, 주간 합치기, 월요일 관련 카드 (main 머지 완료)
  - 결정(사용자): 관련 카드(F3-b) 후보는 선별 통과 도구를 매일 items에 쌓은 목록, 월요일 브리핑 최대 3장, 주간 합치기는 30일 무반응 주제를 직군 프리셋 값(설정에서 고쳤으면 그 값)으로
  - 끝난 것: 하루 실행 실패·빠진 사용자 30분 뒤 그 사용자만 2번 더 → 그래도 실패면 ADMIN_EMAILS 실패 알림(발송 끝내 실패도), 06:55 DB 깨우기 / items.description과 도구 목록 쌓기(질문창 검색에도 사용) / 월요일 실행 전 합치기(피드백 weight_delta만큼 되돌림) / related_pool·pick_related·"이번 주 관련 MCP·스킬" 칸
  - 검수: check_scheduler 23항목, check_deliver(실패 알림·관련 칸), check_merge 10항목, run_daily --fake(도구 목록 4·관련 카드 5), 부록 C 7항목(기준 2를 실제 F3-b 후보로), check_tables·check_ask·웹 회귀, CI success
  - 사고: 18:49 원인 모를 Ctrl+C로 앱 종료(재현 안 됨) → 로그온 작업 런처를 `start_app.ps1`(uvicorn 꺼지면 10초 뒤 다시, Ctrl+C 무시)로 바꾸고 강제 종료 12초 복구 확인
  - 바로잡음: 질문 때 "items에는 카드로 나간 항목만"이라고 했으나 별 수 캐시가 도구 2,046건(주제·설명 없음)을 이미 저장하고 있었음. 결정 내용은 그대로 유효
  - 미완·주의: 주제 판정된 도구는 9/15 기준 8건이라 첫 월요일(9/21) 실제 관련 카드에서 다시 확인, 미완료 검증 재실행은 검증관 뒤, 마감 리마인드(F9 선택) 남음
  - 다음 시작점: 9/16 07:00 자동 실행 → 08:00 메일 도착(A·B·C·본인, 카드마다 trace_id) 확인 = 뼈대 완성 → 검증관(E2B 4단계)

- 세션 7 (이어서) · 2026-09-15 · 웹앱 본체, 피드백 W3, 질문창 W2 (main 머지 완료)
  - 끝난 것: 매직링크 로그인(15분·1회용, 세션 30일, 개발 모드는 ADMIN_EMAILS만), 설정(직군 5·주제 프리셋·도구·자유 한 줄·알림 채널과 시간·기억 지우기·계정 삭제·지금 만들기), 오늘 브리핑(N건 중 M건·기준 한 줄·뉴스/도구 카드·관리자만 트레이스 링크), 피드백 W3(웹 세션과 메일 서명 링크 24시간 1회용, 재클릭 취소, -5~+5, 사유 3택·메모, 큐레이터가 가중치로 정렬), 질문창 W2(`gate.py`, `/api/ask`, 키워드 검색 → 해설가 답 도구 3회·600자·확인한 곳, 최근 3턴 맥락, 한도, 연속 out 예시), 지난 브리핑(날짜·검색)
  - 검수: tests/web check_auth 15·check_settings 10·check_briefings 12·check_feedback 14·check_ask 20·check_rules 11, 부록 C 6항목, check_ask --live-gate 로컬 gemma3 부록 E 예시 5/5, run_loop·run_explainer --fake·run_daily --fake·check_main·폴더 문서 회귀 통과
  - 실제 확인: 본인 계정 로그인(첫 로그인 → 설정) → 프로필 C 문구 저장 → 지금 만들기 549초(카드 6·반려 1·호출 18·형식 실패 0) → 질문 1개 39초(게이트 in·답 311자·확인한 곳 1) → 스크린샷 `docs/img/` 3장, 폰 412폭 가로 넘침 0
  - 가정(보고함): 알림 시간 08·09·12·18, 메일 버튼은 뉴스 2개·도구 3개, 써봤음은 주제 +1, 질문 한도는 in·unclear만 셈, out 턴은 맥락에서 뺌, 모델 장애 질문은 기록·차감 안 함
  - 미완·주의: 관련 카드(F3-b) 없음(부록 C 기준 2는 도구 후보 정렬로 대신 확인), lookup_registry 골격이라 질문 답은 fetch_article만, 메일 링크가 APP_BASE_URL(이 PC)이라 이 PC에서만 열림, 개발 모드 질문 답은 도구 호출이 필요해 Groq 무료로 감(테스트 계정만 허용), 본인 계정 오늘 브리핑은 앱 재시작 직후나 18:00에 [개발 모드] 메일로 나갈 수 있음
  - 결정 필요: 앞 항목의 선별 형식 실패 묶음 누락·해설가 엄격도, 예외 처리 공백(DB·MCP 연결 실패 시 그날 재시도 없음, 실패 알림 없음), 배포 주소(APP_BASE_URL)
  - 다음 시작점: 9/16 08:00 메일 확인(A·B·C·본인) → 메일 버튼과 웹 피드백을 실제로 눌러 다음 날 정렬 확인 → 검증관(E2B 4단계)

- 세션 7 · 2026-09-15 · 세션 6 문제 정리 결정 1~9 반영 (main 머지 완료)
  - 끝난 것: 검증 노드 두 단계(요약 문장 끝 자르기, 빈 값·남은 문제 1회 자가 수정 후 제외), 해설가 relevance(1~5)·3 미만 반려·프롬프트(두 문장·120자·빈 값 금지), 06:55 예열·로컬 첫 호출 90초·이후 30초, 429는 60초 뒤 같은 제공자 1회 재시도·해설가 대체 groq → gemma3 → gemini → openrouter, MCP 레지스트리 60초·2번 더·마지막 성공 결과 재사용("수집 실패, 전날 기준"), 긱뉴스 외부 링크(없으면 요약만), app.log UTF-8, 계획안 부록 B·9.2("개발 중 앱 내 스케줄러, 배포 시 n8n 크론이 /api/w1/run 호출"), run_daily --date
  - 검수: check_models, check_scheduler 12항목, check_fallbacks 7항목, run_daily --fake(긴 요약·빈 요약·관련도 2 포함), run_explainer --fake, check_folder_docs·check_readme 통과
  - 검증 실행(--users 1 --limit 40, 검수 날짜 2000-01-05, 끝나고 삭제): 586.6초, 호출 8(ollama 5·groq 3), 429 0회, 전환 0회, 형식 실패 2회(선별 1묶음 gemma3가 reason 칸 누락, 재시도도 누락 → 20건 묶음 1개 빠짐), 백엔드 카드 0(해설가가 뉴스 3건 모두 reject), 트레이스 https://us.cloud.langfuse.com/project/cmu0jv4a1000iad0doj6r99it/traces/f94a15ec3416b08f3c7863adc9facf59
  - 확인: 긱뉴스 RSS에는 외부 출처 링크가 없어 지금은 전부 요약만. 이번 검증 실행에서는 카드가 검증 노드까지 오지 않아 두 단계 경로는 가짜 모델로만 확인
  - 결정 필요: 큐레이터 선별 형식 실패(gemma3 reason 누락)로 묶음이 통째로 빠지는 문제, 해설가가 더 엄격해져 빈 브리핑이 늘 수 있음(내일 A·B·C 메일로 확인)
  - 다음 시작점: 사용자가 9/16 08:00 메일 3통 확인 → 피드백 버튼(W3): 메일 카드 서명 링크 3종, /api/feedback, weights·seen 쓰기, 다음 날 정렬 반영 → 검증관

- 세션 6 · 2026-09-15 · n8n 제거, 앱 안 예약과 Gmail 직접 발송 (main 머지 완료)
  - 결정(사용자): n8n 구조 제외, 07:00 실행·08:00 발송은 FastAPI 앱 안에서 예약, 개발 모드도 ADMIN_EMAILS(본인)에게만 실제 발송 허용
  - 끝난 것: `pipeline/scheduler.py`(07:00·08:00, 놓친 실행 22:00 전 따라잡기, 실행 끝난 뒤 발송, 발송 실패 10분 간격 2번 더), `pipeline/deliver.py` Gmail SMTP 발송(보낸 사용자만 sent_at), `routes/w1.py` 수동 실행·발송·상태, n8n 폴더·compose 서비스·CI 단계·문서 제거
  - 검수: check_scheduler 11항목, check_deliver 24항목(가짜 SMTP), check_main·check_readme·check_folder_docs·check_env_example 통과, CI 4단계 success(b1e72f1)
  - 실제 메일: 9/15 브리핑(사용자 1·카드 5·반려 1·호출 11·416초)을 개발 모드로 ADMIN_EMAILS에 Gmail SMTP 발송, 받은편지함 도착 확인(카드마다 trace_id). 트레이스 https://us.cloud.langfuse.com/project/cmu0jv4a1000iad0doj6r99it/traces/74fd811dfd31cc41164570abf9b27ed9
  - 관찰: gemma3 첫 로드 30초 초과로 선별 1묶음 groq 전환, groq 429 2회·gemini 429 1회로 카드 1장 openrouter. MCP 레지스트리는 이번엔 성공
  - 앱 상시 실행: Windows 로그온 작업 `toolscout app` 등록(창 없이 uvicorn, 로그 %LOCALAPPDATA%\toolscout\app.log), 상태 API로 예약 켜짐·다음 예정 07:00 확인
  - 프로필: 메일이 가짜 프로필 A 기준이라 개발자 본인 프로필 C(AI 에이전트를 공부하는 개발자·Python·Claude Code·MCP) 추가, 매일 A·B·C 세 통 (사용자 결정)
  - 버그: 앱 따라잡기 실행에서 B·C 카드 0건 메일 발송. 후보 단계 입력(약 7.7K토큰)이 로컬 문맥 8192를 채워 답이 잘렸고, 잘린 답이 빈 후보로 규격을 통과했다 → 형식 실패 처리와 후보 단계 상한(뉴스 60·도구 20)으로 수정 후 B·C 다시 실행: 카드 9(C 7·B 2)·반려 5·호출 31·14분, 13:20 자동 발송(형식 실패 4회 중 1건 미복구로 카드 1장 빠짐)
  - 미완: 다음 날 07:00·08:00 자동 실행 확인
  - 결정 필요: gemma3 첫 로드 타임아웃, groq 429. 계획안 위험 목록의 "강사 기준: n8n 필수/가산점" 확인
  - 다음 시작점: 앱을 켜 두고 다음 날 07:00 실행·08:00 메일 자동 도착 확인 (뼈대 완성)

- 세션 5 · 2026-09-15 · 전량 하루 실행, 08:00 발송 준비·기록, n8n W1 (main 머지 완료)
  - 끝난 것: 전량 실행(사용자 2명·카드 7·반려 5·호출 23·토큰 입력 56,604·출력 10,610·650초·전환 없음), 메일 본문(`pipeline/briefing_mail.py`, 카드 전체·카드마다 trace_id), 발송함·sent_at 기록(`pipeline/deliver.py`), n8n용 API(`routes/w1.py`), W1 워크플로우(`n8n/workflows/W1_daily.json`), CI에 n8n 가져오기
  - 검수: check_deliver 19항목, check_workflows 13항목, CI 6단계 success(n8n 기동·가져오기 포함), 9/14 브리핑 개발 모드 콘솔 발송 2통·sent_at 7행
  - 미완: n8n에서 W1 실제 실행(로컬 Docker 없음, n8n 2.38은 Node 24 필요인데 로컬 Node 20), 실제 메일 도착(개발 모드는 발송 금지, GMAIL_USER 비어 있음), 피드백 버튼(W3)
  - 결정 필요: n8n을 어디서 돌릴지(Docker Desktop·Railway·Node 24), 실제 메일 테스트를 운영 모드로 할지, MCP 레지스트리 ReadTimeout 2회 연속(도구 후보 0건), gemma3 첫 로드 24.5초
  - 다음 시작점: n8n 실행 환경 결정 → 자격 증명 2개 만들고 W1 켜기 → 07:00·08:00 실제 실행과 메일 도착 확인 (뼈대 완성 정의)

- 세션 4 · 2026-09-14 · 개발용 로컬 모델(Ollama)과 첫 실제 하루 실행 (main 머지 완료)
  - 끝난 것: Windows Ollama 0.34.0 설치(WSL2는 다운로드가 초당 78KB로 제외), 로컬 모델 실측(`docs/local-model.md`), 개발 제공자 순서 ollama → groq → gemini → openrouter, Groq 모델 확정, run_daily `--users`·`--limit`, 형식 실패 예시 파일 누적, 모델 장애 사용자·카드 단위 건너뜀(전원 실패 종료 코드 2), 카드 0건 empty_reason 행(briefings 기본키 이전), 계획안 모델 장애 행·한글 비율 어절 60%
  - 모델: 큐레이터·게이트 gemma3:12b(8.96GiB, 도구 호출 미지원), 해설가·검증관 groq qwen3.8-27b. qwen3:14b(9.82GiB)는 삭제
  - 첫 실제 실행(`--users 1 --limit 40`): 브리핑 1명·카드 3·반려 0·제외 0, 호출 8(ollama 4·groq 4, 전환 없음), 토큰 입력 22,963·출력 4,567, 486초, 형식 실패 2회 모두 재시도 복구, 트레이스 https://us.cloud.langfuse.com/project/cmu0jv4a1000iad0doj6r99it/traces/7c45d4178f4dfda3995a82f886e938f9
  - 검수: check_models·check_groq·check_tables·run_daily --fake 30항목·run_explainer --fake·check_folder_docs·check_readme 통과
  - 결정 필요: gemma3:12b 첫 로드 24.5초(30초 타임아웃 근접), MCP 레지스트리 ReadTimeout으로 도구 후보 0건, 전량 실행 시간(Groq 30초 간격)
  - 다음 시작점: 전량 실행(사용자 2명) 한 번 → 이메일 발송(sent_at 기록, empty_reason 행 포함) + n8n W1

- 세션 3 · 2026-09-14 · 큐레이터·해설가·검증 노드·저장·하루 실행 (가짜 모델 검수 통과, main 머지 완료)
  - 끝난 것 (main 머지): 큐레이터(선별·사용자별 후보·검증 요청), JSON 규격 응답·1회 재시도(`agent/structured.py`), 해설가·용어집 30개, 검증 노드(`pipeline/validate.py`), 저장(`pipeline/persist.py`), 하루 실행(`pipeline/run_daily.py`), MCP 수집 별 수 24시간 캐시·신규 20·버전 업 10, 개발 모델 사고·추론 설정과 호출 간격
  - 검수: run_curator 실제 통과(호출 13·63초·선별 94·두 사용자 겹침 0·검증 요청 5), run_explainer --fake 8항목, run_daily --fake 21항목(Supabase 실제 저장·재실행 멱등·발송 사용자 건너뜀) 통과
  - 무료 모델 형식 실패: 큐레이터 1차 12회(재시도 후 4건 실패, 사고·추론 토큰이 출력 한도 소진) → 설정 조정 후 1회(재시도로 복구)
  - 미완: 실제 모델 run_daily·run_explainer. Gemini·OpenRouter 무료 하루 한도 모두 소진으로 큐레이터 첫 호출에서 멈춤, 저장 0건
  - 결정 필요: 기본·대체 모델이 둘 다 실패할 때 처리(지금은 실행 전체가 멈춤), 한글 비율 어절 기준 60% 확인, 카드 0건 사용자 발송 방식
  - 다음 시작점: 9월 15일 16:00 KST 이후 `tests.pipeline.run_daily` 실제 한 번 → 이메일 발송(sent_at 기록) + n8n W1

- 세션 2 · 2026-09-14 · 지난 결정 반영과 막힌 검수 마무리 (4번 통과, main 머지 완료)
  - 끝난 것 (main 머지): Docker CI (GitHub Actions 4단계 성공), `config.py` .env 로더(값 출력 금지 규칙), psycopg와 연결 문자열 자동 변환, Gemini·Anthropic 클라이언트 닫힘 버그, 529 전환, 계획안 부록 F, mcp/ 용도, 벤처비트 제외, DEV_MODE 모델표·OpenRouter, users.is_test·가짜 프로필 2개, MCP·해커뉴스 수집 필터
  - 4번 통과: check_env / check_tables (Supabase 표 9개, is_test 칸, 가짜 프로필 id 1·2) / check_models (개발 모델 4역할 실제 호출) / run_loop (nex-n2.5-pro 안녕·도구 1개, Langfuse 트레이스)
  - 개발 모델표는 실측으로 재배정: gemma-4는 무료 공급자 429 반복으로 제외, 검증관·해설가 nex-n2.5-pro, 게이트·큐레이터 대체 nex-n2.5-mini
  - 결정 필요: 수집량 기준 (필터 적용·재측정 후 912건, MCP 7일 신규 등록만 648건), MCP 수집 137초 캐시 방식, Langfuse 스팬 전송 제한 시간(5초 초과로 최상위 스팬 1개 누락)
  - 다음 시작점: 큐레이터 (`agent/curator.py`)

- 세션 1 · 2026-09-13 · 0단계·1단계 앞부분 (착수 1~12번)
  - 끝난 것 (main 머지): 1 폴더 구조·문서, 2 루트 README, 3 pyproject·환경 검사, 4 .env.example, 6 models.py·tracing.py, 7 db.py(Supabase 전용), 8 sources 10곳, 9 pipeline, 10 loop.py, 11 mcp_server.py, 12 main.py, 폴더 README 할 일 절, .gitignore
  - 미완: 5 docker는 `feat/05-docker` 브랜치(docker 미설치로 compose config·compose up app 미검증, 머지 보류)
  - 키 없어 미실행인 검수: models 실제 호출, db Supabase 생성, loop 실제 모델 "안녕"·도구 1개
  - 결정됨: DB는 Supabase 하나(SQLite 안 씀), 로컬 작업 도구 파일은 저장소 제외, 해커뉴스는 OR 의미(optionalWords), 로컬 .env는 `uv run --env-file .env`로 읽음(python-dotenv 불필요)
  - 결정 필요: Docker 검수를 GitHub Actions로 할지(.github/ 추가), .env 키·Supabase 연결 문자열·Postgres 드라이버(psycopg), Anthropic 529 전환 포함, 수집량 기준(MCP 7일 1,964건·HN 189건), 벤처비트 429, 부록 A 트리, mcp/ 폴더 용도
  - 다음 시작점: 큐레이터 (`agent/curator.py`)
