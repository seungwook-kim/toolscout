# agent/ CHANGELOG

- 2026-10-16 · select_memo.py 추가(load·save, select_memos 표), curator.select·run에 known(재사용 판정)·judged(모델이 판정한 뉴스), 트레이스 출력에 reused · 수집 창 48시간이라 전날 판정한 뉴스가 다시 판정돼 같은 오답이 이틀 나감(10/8~10/11 오답 85건 중 약 10건), 사용자 결정 "전부 다 진행"(C)·curator.py 300줄 넘김 허용 · check_select_memo 10(신규)·check_headline·check_importance·check_tables·run_daily --fake 통과
- 2026-10-14 · injection.py(신규): clean(보이지 않는 글자·태그 문자·<data> 흉내·채팅 틀 토큰 지우기), scan(지시 문장 10종, 경고만), output_problems(카드 글의 링크·메일·구분자 흔적), safe_install(치환·리다이렉트·여러 줄 금지, 주소는 그 도구 자신의 저장소·사이트만). loop.run이 입력을 scrub하고 tool_guard로 도구 요청을 거부할 수 있게, explainer는 항목 제목·요약 정리·injection_suspect 알림·프롬프트 규칙 2줄·설치 명령 safe_install, answer는 fetch_article을 후보 링크만·답 글의 후보 밖 링크 지움, skill_check.wrap_data·gate 질문 정리 · 사용자 "인젝션 방어로직도 넣어놔"(레딧 글 본문을 원문으로 넣게 된 날). 전에는 <data> 감싸기와 '따르지 않는다' 문구, 스킬 정규식뿐이었고 </data>만 정확히 막았다 · check_injection 18항목 통과, --live(운영 Haiku 5.5, 호출 3) 심은 낱말·주소·프롬프트 흔적 0, 실제 피드 281건 중 지시 의심 1건(헤드라인 'You are now an enemy…'), 지난 카드 630장 중 출력 검사 걸림 0·설치 명령 뺌 7
- 2026-10-14 · explainer: 피드 글 본문(source_text)이 있으면 그것을 원문으로(<data>로 감쌈, 바깥 링크가 있으면 읽어서 덧붙임, source_checked=True), 장단점 근거 링크는 own_links가 맞춤(항목·읽은 링크와 그 아래 경로는 카드 링크로, 다른 사이트 근거 줄은 뺌, 형식 실패로 돌리지 않음), for_me 프롬프트에 "마침표 하나, 단서는 '~지만'으로 같은 문장에" · 10/14 jCodemunch 카드가 읽은 /releases를 근거로 적어 형식 실패 2회로 빠짐, for_me 두 문장이 카드 62장 중 28장(재시도 21번) · run_explainer --fake 10항목(신규 2) 통과
- 2026-10-11 · structured.ask_json: 호출 동안 models.STRUCTURED_SCHEMA에 규격(JSON Schema)을 올려 Anthropic 구조화 출력으로 보냄(다른 제공자는 무시) · gpt-4o-mini가 10/10에 형식 실패 18번·복구 못함 8번 · check_anthropic 통과, 실제 게이트 호출 형식 실패 0
- 2026-10-08 · same_story.drop: 남긴 기사에 뺀 기사 제목·출처·요약을 also_reported로 붙이고 해설가가 남긴 기사에 없는 사실(요금·크레딧·한도)을 summary_ko·for_me에 담게 함, headline 후보 30 → 80건(자른 뒤 묶어서 다룬 곳 수가 적게 세어지던 것) · 10/8 크레딧이 적힌 GeekNews 기사가 같은 소식으로 빠지고 AI Times 기사만 남음, 큰 소식 후보 30건 밖으로 GeekNews가 잘림 · check_same_story 10·check_headline 18·run_explainer --fake 통과
- 2026-10-07 · loop: MCP_URL=inproc이면 같은 프로세스의 mcp_server.mcp에 메모리로 붙는다 · Vercel 웹은 자기 /mcp를 HTTP로 못 부르고 Railway 크론은 서버를 띄우지 않는다(사용자 결정 "vercel + railway") · github.com fetch_article 실측 3,064자, check_cron 통과
- 2026-10-06 · importance: 개발 모드도 Jev가 먼저, Jev가 못 매긴 기사(키 없음·연결 실패)만 구독 Haiku로 다시 매기고(span importance_fallback, 보고 fallback), 그것도 실패하면 선별 점수 · 사용자 결정 "JEV로 돌려". Jev의 10/1~10/5 ConnectError는 사이트 장애가 아니라 이 PC의 안랩 차단이었다(check-host.net 바깥 노드는 200, 10/6 10:44부터 이 PC도 접속됨) · check_importance 25 통과
- 2026-10-05 · importance: 개발 모드는 Jev 대신 구독 모델("importance" 역할, Haiku 4.5 생각 끔)로 20건 묶음마다 같은 5단계 점수, 선별 점수는 importance_select에, 묶음 실패면 선별 점수 그대로 · loop.DEV_MODE_NOTICE를 "개발 모드: Claude 구독만, 실제 사용자 데이터 금지"로 · 사용자 결정 "다 로컬에 도구모델(Claude 구독) 기반으로, 구독만·실패하면 건너뜀", Jev는 10/1~10/5 매일 ConnectError · check_importance 23·check_same_story 8 통과
- 2026-10-05 · curator 선별 입력: 요약이 빈 뉴스(해커뉴스 링크 글)에 link_site(링크 도메인, 예: blog.google)를 더함. 수집·저장 요약은 그대로 · 해커뉴스 링크 글은 story_text가 없어 제목만으로 판정돼 Muse Gadgets·구글 Suncatcher 위성을 AI 무관으로 놓침(10/3·10/4, 사용자 승인) · check_promo 13·check_topic_guide 6·run_daily --fake 통과. 효과는 다음 실행 골든셋으로 본다
- 2026-10-04 · probe: 도움말만 찍고 끝나는 CLI는 도움말의 stdio MCP 하위 명령(serve·mcp, HTTP·SSE 서버는 빼고)으로 1회 더 실행, 그래도 도움말이면 실행·도구 목록·인증을 실패가 아니라 미확인으로(도움말 낱말을 인증 요구로 안 봄). 출력 끝부분을 8,000바이트까지 읽는다 · 10/3 카드의 llm-wiki-compiler·gflow-cli가 서버 시작 명령 없이 돌아 "실행 실패"로 나감 · check_probe_labels 10(신규)·check_probe(실제 E2B) 통과, 실제 재실측 llm-wiki-compiler 실행 성공·도구 16개, gflow-cli 미확인
- 2026-09-30 · 선별 worth_today: 에세이·칼럼·의견 글, 개인 사용기·비교 후기, 커뮤니티 토론 글 false / AI 기업 투자 유치·인수·실적, AI 서비스 장애·보안 사고, 신제품 발표 예고, 연구 결과 공개 true · 9/30 골든셋에서 놓친 11건이 투자·장애·예고, 잘못 통과 26건이 에세이·사용기 · check_promo·check_topic_guide(1,795자) 통과, 효과는 10/1 채점

- 2026-09-28 · loop.DEV_MODE_NOTICE를 "개발 모드: Claude 구독(없으면 무료 모델), 실제 사용자 데이터 금지"로 · 개발 모드 1순위가 Claude 구독이 됨(루트 claude_cli.py·models.py) · run_explainer --fake·check_verifier·check_ask 통과

- 2026-09-28 · headline.attach: 주제 가중치 -5여도 큰 소식에 넣는다(본 소식만 뺌) · 예외 처리 표 점검에서 계획안 부록 C "그 주제는 카드에 안 나오되 헤드라인엔 남음"과 어긋난 것을 찾음(9/23에 -5 제외를 넣었었다) · check_headline 18·check_appendix_c 통과

- 2026-09-28 · pick_related(월요일 관련 카드)에도 게시자 반복 줄이기(owners.spread)와 데이터 근거 이유(card_why) · 9/28 관련 카드 3장이 모델 이유("관심이 있어보입니다")로 나가고 fuxicodex 스킬이 또 나감. 9/27에 일반 경로에만 적용했었다 · check_card_why 8·check_appendix_c·check_owners·run_daily --fake 48 통과

- 2026-09-28 · verifier.verify_one: 제공자 400 등 예상 못 한 오류도 그 항목만 미완료(다음 날 재시도)로 두고 계속. providers.gemini_contents: 다른 제공자가 만든 도구 호출·결과는 글로 바꿔 넘김(Gemini 호출은 원본 parts·서명 그대로) · 9/28 07:19 Groq 429 → Gemini 전환 때 Gemini 3가 서명 없는 도구 호출을 400으로 거절해 검증 연결이 끊김(발송 전 검증 anythingmcp). 문서 3곳에서 우회값을 찾지 못해 글로 바꾸는 방식 · check_fallback_errors 7·check_verifier·check_mcp_now·check_rollback 통과

- 2026-09-27 · card_why.py 추가: 카드 이유(why_this_card)를 가중치 양수인 관심 주제·제목과 설명에 나온 쓰는 도구로 만들고 모델 이유는 pick_why로 트레이스에만. 근거 없으면 모델 이유 · 9/27 메일에도 "관심 있는 개발자에게 유용한 도구입니다" 되풀이, 프롬프트 기준을 로컬 모델이 안 따름 · check_card_why 7·check_owners·check_same_story·check_headline·check_appendix_c 통과, 9/27 실제 카드 8장 적용 결과 확인

- 2026-09-27 · 선별 worth_today에 행사 예고·연사·등록, 책·서평, 웨비나·교육 모집, 채용 false. 해설가는 합니다체, 3인칭·호칭("사용자가"·"개발자님") 금지, 없는 관심사 지어내기 금지, why_this_card 되풀이 금지, 뉴스 장단점은 발표된 것 자체만(기사 읽는 이점·원문 못 읽음은 아님). 큐레이터 why는 프로필 무엇과 이어지는지 구체적으로 합니다체 · 9/16~9/26 발송 메일 점검 · check_promo·check_topic_guide 통과. 모델 전후 비교는 사용자 지시로 멈춤, 9/27 07:00 실행으로 확인

- 2026-09-27 · owners.py 추가, pick_for_user 도구 후보에서 최근 7일 안에 카드로 나간 GitHub 게시자는 빼고 같은 게시자는 하루 한 건(excluded.same_owner), memory.read에 seen_recent_urls(오늘 제외) · 9/24·25 같은 게시자(fuxicodex) 스킬 4장 · check_owners 8·check_same_story·check_headline·check_importance·check_topic_guide·check_appendix_c·run_daily --fake 48 통과

- 2026-09-25 · 사용자 후보에서 Jev 중요도 2 이하 뉴스를 뺀다(남는 게 10건 미만이면 그대로). same_story는 시간 초과·503이면 같은 모델로 한 번 더(models.py). 큐레이터 트레이스에 큰 소식·중요도 결과를 남긴다 · 9/25 본인 뉴스 5장 중 4장이 모델 출시로 잘못 분류된 OpenAI 고객 사례였고, 9/24는 큰 소식 묶기 호출이 한 번 시간 초과로 실패해 큰 소식 칸이 빠졌다(원인을 호출 기록을 뒤져 찾음) · check_importance 14항목(3 추가)·check_headline·check_same_story·check_topic_guide·check_reject_rate·check_rollback·check_mail_layout·run_daily --fake·모델명 하드코딩 검사 통과

- 2026-09-23 · importance.py 추가: 선별 통과 뉴스마다 Jev(models.JEV)에 제목·요약 300자와 영어 5단계 기준을 보내 중요도를 바꾼다(동시 4개, 실패하면 선별 모델 점수 그대로, 가짜 모델 검수에서는 안 부름). same_story는 해설가 순서를 빌리던 것을 models.SINGLE_MODEL_ROLES['same_story'](OpenRouter 유료 모델, 사용자 지정)로 바꿨다 · 선별 모델 중요도가 평범한 기업 소식에 4~5점을 줬고, 같은 소식 묶기 모델을 임의로 빌려 쓴 것을 사용자가 바로잡았다 (둘 다 2026-09-23 사용자 결정) · 골든셋 32건(한국어 18·영어 14) 같은 영어 기준 순위상관: Jev 0.94, 선별 모델 0.82. Jev 32건 비용 $0.0076. check_importance 11항목(신규)·check_same_story·check_headline·check_topic_guide·check_mail_layout·check_rollback·run_daily --fake 2회·모델명 하드코딩 검사 통과

- 2026-09-23 · 오늘의 큰 소식 headline.py 추가. 선별 판정에 importance(1~5)를 받고, 중요도 3 이상 뉴스 30건을 same_story.groups로 묶어 점수(최고 중요도 + 다룬 곳 - 1 + 공식 1)가 가장 높은 소식을 사용자 관심도와 상관없이 뉴스 맨 위에 둔다. 3곳 이상 또는 중요도 5를 2곳 이상일 때만, 두 번째도 8점 이상이면 2칸. 같은 소식의 다른 기사는 빼고 뉴스는 합쳐 5장. 카드에 headline 칸, same_story는 groups/drop으로 나눴다 · 9/23 오퍼스 5.5가 관심도에 밀려 빠졌다. Jev는 보류(사용자 결정) · 9/23 뉴스 193건 실측: 큰 소식 GPT-6 Sol·Luna(4곳·공식·9점). check_headline 17항목(신규)·check_same_story·check_mail_layout·check_rollback·run_daily --fake 통과

- 2026-09-23 · same_story.py 추가, pick_for_user가 고른 뉴스에서 같은 소식을 빼고 same_story_dropped를 남긴다. 후보 프롬프트에 '같은 소식은 하나만' 한 줄 · 9/23 본인 뉴스 5장 중 2장이 GPT-6 Sol·Luna 영문·한국어였다. 프롬프트 한 줄만으로는 로컬 모델이 못 지켰고, 예비를 같이 고르게 하자 뉴스를 3장만 골랐다. gemma3:12b는 이름만 같은 다른 소식을 묶어 5건 중 3건을 잘못 뺐고, qwen3.8-27b는 9건 중 8건을 빼고 잘못 뺀 것 0이라 해설가 모델 순서를 빌린다 · check_same_story 8항목(신규)·run_daily --fake 3회·check_rollback·check_skill_now·check_scheduler·check_reject_rate·check_topic_guide 통과

- 2026-09-23 · 선별 프롬프트에 주제별 경계(schemas.TOPIC_GUIDE)와 규칙 두 줄(제목 단어가 아니라 글이 다루는 것으로, agent_framework·mcp_tools·coding_tools는 개발 방법·도구 자체일 때만)을 붙였다 · 주제 이름표만 주자 로컬 모델이 'GPT'·'NPU' 같은 단어에 끌려 회사 사례를 model_release로, 칩·교육 소식을 coding_tools로 붙였고, 관심도 가중치가 이 판정을 믿고 움직인다 · 측정: 9/23 48시간 뉴스 193건을 고정해 같은 시드로 선별(gemma3:12b), 통과 약 120건을 사람이 매긴 주제(애매하면 여러 개 인정, AI 무관 몇 건 제외)와 비교. 정확 56% → 경계 추가 64% → 개발 주제 규칙 70%, model_release 정확 22/29 → 21/26. 로컬 실행·에이전트 앱 경계를 더 넣은 3차는 70% 그대로라 넣지 않았다. 선별 통과 건수 125 → 124로 고르는 기준은 그대로. Ollama 실측 입력 묶음 최대 2,845 → 3,226토큰 · check_topic_guide 6항목(신규)·run_daily --fake 통과

- 2026-09-21 · 해설가 프롬프트에서 for_me 범위를 넓히고(당장 쓸 일이 없어도 이 직군이 알아둘 이유) 반려 조건을 좁힘(큐레이터가 고른 이유가 납득되면 살리고, 어느 것과도 이어 볼 수 없을 때만 반려), 관련도 3의 뜻을 명시 · 자유 한 줄에 적힌 지금 하는 일에 그대로 쓸 수 있는지로만 보아 백엔드 7건 중 6건 반려, 마케터는 9월 18·19일 후보 8건이 모두 반려돼 브리핑이 비었다 · check_reject_rate 5항목 통과(전에 반려된 3건이 모두 관련도 3으로 회복, 무관한 대조 항목은 계속 반려), 마케터 프로필도 2건 회복

- 2026-09-21 · curator.PICK_PROMPT에 제외 규칙 한 줄(자유 한 줄에 보기 싫다고 적힌 기술·주제·회사는 고르지 않는다, 다른 기준보다 먼저) · 사용자가 Java·Spring 생태계를 빼 달라고 요청했는데 프로필에 싫음을 적을 자리가 자유 한 줄뿐이었고 프롬프트가 그것을 제외로 읽지 않았다 · check_news_window 제외 규칙 항목 통과

- 2026-09-16 · verifier.registry_plan(설치 정보가 있으면 모델 없이 npx·uvx·원격, 자리표시자 주소·도커 이미지만이면 실측 불가), probe npm 설치 전 Node 22 준비·자리표시자 주소 거부 문구 · 실제 5건에서 판단 단계가 항목당 약 200초(모델이 README 두 번·30초 제한), desktop-commander가 Node 20.9 require(esm)으로 실행 실패 · check_verifier 21항목·desktop-commander 4단계 성공(도구 26개)
- 2026-09-16 · curator.replan_failed(되돌림 1: 대체 선택·비움, 모델 장애면 그 도구만 빠짐), schemas ReplanDecision·Card.verification_note, 해설가 입력에 검증 결과, reverify 스팬 이름 verify:reverify · 세션 8 되돌림 5단계 · check_rollback 16항목 통과
- 2026-09-15 · verifier.py(설치 방법 판단·probe_mcp, 스킬 판독·정규식 비교·공식 생략, reverify), schemas McpProbePlan·SkillJudgment · 세션 8 검증관 4단계 · check_verifier 17항목 통과(삽입 문장에 모델이 넘어가도 정상이 아니라 확인 필요)
- 2026-09-15 · skill_check.py 추가(원문 주소 변환·SkillsMP API로 GitHub 원문, 절단 전 전체 정규식, 보이지 않는 문자는 [U+XXXX] 인용) · 세션 8 검증관 3단계 read_skill · check_skill_read 13항목 통과, 실제 스킬 6개(공식 3·SkillsMP 3) 오탐 0
- 2026-09-15 · probe.py 추가(설치 명령 파싱·가드·4단계·인증 요구 감지·probes 저장), loop MCP 읽기 제한 120 → 240초 · 세션 8 검증관 2단계 probe_mcp · check_probe 10항목 통과(server-everything 22초 도구 13, mcp-server-fetch 28초, DeepWiki 원격, Apify 401, brave-search BRAVE_API_KEY 감지)
- 2026-09-15 · curator.pick_related·RELATED_PROMPT, schemas.RelatedPicks·Card.related, explainer가 related 항목도 카드로 · F3-b 관련 카드(월요일 최대 3장, 사용자 결정) · run_daily --fake 관련 카드 5항목·부록 C 기준 2 통과
- 2026-09-15 · explainer.answer·AnswerOutput 추가, loop.run에 max_tool_calls · 질문창 W2(부록 E 도구 최대 3회·600자·확인한 곳) · check_ask 20항목, run_loop·run_explainer --fake 회귀 통과
- 2026-09-15 · curator: 모델이 고른 후보를 주제 가중치로 안정 정렬, 결과·트레이스에 사용자별 weights · 부록 C "다음 날 큐레이터가 가중치를 읽어 정렬" · check_appendix_c 6항목·run_daily --fake 통과
- 2026-09-15 · 해설가 출력에 relevance(1~5) 추가·3 미만 반려, 초안 카드(DraftCard)로 긴 요약·빈 값을 검증 노드에 넘김, 프롬프트에 두 문장·120자·빈 값 금지·관련도 기준, 원문은 source_url 우선·skip_fetch면 요약만, 알림 문구 합치기 · 세션 7 결정 1·5·6, format_failures.json 예시 4건 · run_explainer --fake 통과

- 2026-09-15 · structured: JSON이 아닌 답은 형식 실패로 처리, curator: 후보 단계 입력 상한(뉴스 60·도구 20, 이유 60자·요약 120자, 가중치·출처·최신·별 수 순) · 실제 실행에서 후보 140건이 로컬 문맥 8192토큰을 채워 답이 잘렸고 빈 후보로 통과해 B·C 메일이 "오늘 볼 만한 게 없었음"으로 나감 · run_daily --fake 회귀 3항목 통과

- 2026-09-14 · 큐레이터·해설가 모델 장애 단위 건너뜀, structured 실패 예시에 제공자·모델 기록·예시 전부 보관, loop 결과에 제공자·모델 · 로컬 모델 전환과 모델 장애 결정(세션 4) · run_daily --fake 29항목 통과

- 2026-09-14 · explainer.explain_item에 feedback 인자 추가 · 검증 노드가 돌려보낸 이유를 붙여 1회 재시도하려고 · run_daily --fake에서 영어 첫 응답이 재시도로 복구됨 확인

- 2026-09-14 · explainer.py·glossary.md 추가, JSON 규격 응답을 structured.py로 분리 · 계획안 5장 해설가·부록 B 4, 무료 한도 절약으로 항목당 원문 1회·모델 1회 · run_explainer --fake 8항목 통과, 실제 모델 검수는 한도 초기화 후

- 2026-09-14 · curator.py·schemas.py 추가, loop.py 토큰 합계·원문 반환 · 계획안 5장 큐레이터·부록 B 1~3 · 1차 형식 실패 4건(사고·추론 토큰이 출력 한도 소진) → 사고 minimal·추론 끔 적용 후 run_curator 통과(호출 13회·63초·형식 실패 1회 재시도로 복구)
- 2026-09-14 · 할 일에 Langfuse 전송 제한 시간 초과 건 추가 · run_loop 실제 모델 실행 중 스팬 묶음 전송이 5초를 넘어 최상위 스팬 1개 누락 · run_loop 통과(실제 안녕·도구 1개)
- 2026-09-14 · loop.py 개발 모드 안내 로그, tracing.py config 연결·trace_url() 추가 · DEV_MODE 승인·값 출력 금지 규칙 · run_loop 루프 동작 9항목 통과, 실제 모델은 OpenRouter 키 401로 미통과
- 2026-09-13 · loop.py 직접 판단 루프 구현 · 착수 10번 · run_loop 루프 동작 8항목 통과, 실제 모델 실행은 키 없어 미실행
- 2026-09-13 · README에 할 일 절 추가, 파일 상태 갱신 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · tracing.py 추가 · 모든 LLM·도구 호출을 스팬으로 남기고 Langfuse 장애 시 로컬 로그 대체(절대 규칙 10) · tests/models/check_models.py에서 로컬 모드 trace_id 발급 확인
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
