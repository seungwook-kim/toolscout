# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 13 · 2026-09-26 · 발송된 메일 전체 점검(9/14~9/26 본인 카드 71장)과 그 뒤 수정
  - 결정(사용자): "가장 정확도가 높은 쪽으로, 추천대로". run_daily.py는 나눈다(발송 전 검증을 pipeline/presend.py로)
  - 점검 결과: MCP 카드 24장 중 10장이 검증 요청 없이 "검증 예정"으로 나감 / 위험 신호 "확인 필요" 줄에 내부 표시와 마크다운 /
    같은 게시자(fuxicodex) 스킬이 이틀에 4장 / 뉴스 제목 39개 중 18개 영어 / 카드 말투 흔들림·지어낸 관심사 / 행사 홍보 같은 낮은 가치 뉴스.
    문제없던 것: 큰 소식 칸(9/25·26), 오퍼스 5.5(9/24), 스킬 카드 8장 모두 판독 결과, 9/26 고객 사례 0건
  - 끝난 것: MCP 카드 발송 전 E2B 설치 검증(4건·10분 예산), 검증 메모를 요청 상태대로, 위험 신호 근거·인용 정리.
    check_mcp_now 18(신규)·run_daily --fake 48·check_skill_now·check_rollback·check_verifier·check_mail_layout·check_deliver·웹 검수 통과.
    실제 E2B 한 건(Browsentic): 28초, 설치 성공 8.9s·실행 실패·도구 목록 실패·인증 필요로 기록
  - 끝난 것(9/27 0시대): 도구 후보 게시자 반복 줄이기(agent/owners.py, 최근 7일 본 게시자 빼기·하루 한 건). check_owners 8(신규) 통과.
    함께 찾음: 부록 C 검수(check_appendix_c)가 9/23 같은 소식 묶기 추가 뒤로 깨져 있었다. 가짜 모델만 고쳐 7항목 통과
  - 끝난 것(9/27 0시대, 사용자 "추천대로, 행사 책 홍보는 걸러"): pipeline/promo.py(책 연재·TechCrunch 자체 행사 홍보·웨비나를
    모델 전에 뺌, 9/27 0시 후보 152건에서 6건·오탐 0), 선별 worth_today 기준, 해설가·큐레이터 문장 기준(합니다체·3인칭 금지·
    지어내기 금지·뉴스 장단점은 발표된 것만). check_promo 8(신규)·run_daily --fake 48 통과
  - 끝난 것(9/27 오후): 9/27 메일 확인(발송 08:00, MCP 카드에 실제 검증 결과, 홍보 뉴스 0, 합니다체). 남은 것 두 가지를 고침:
    카드 이유를 데이터 근거로(agent/card_why.py), 교체 카드에 내부 사정 안 나가게. 함께 찾음: tests/pipeline/format_failures.json을
    하루 실행이 쓰면 작업 트리가 바뀌어 자동 재시작이 멈춘다 → git 추적에서 뺌. check_card_why 7(신규)·run_daily --fake 48 통과
  - 끝난 것(9/27 저녁, 추천 기능 1): 선별 골든셋. 모델을 다시 부르지 않고 그날 실행의 판정을 Langfuse 트레이스에서 꺼내(tests/golden/fetch_select.py)
    Claude Code가 단 정답과 채점(score_select.py). 9/27 뉴스 141건: 재현율 95.2%, 정밀도 63.2%(목표 90%). 개발자 검토·두 번째 채점자는 아직
  - 끝난 것(추천 기능 2, 사용자 승인으로 범위 조정): "써봤음" 기록이 0건이라 받아 본 MCP(30일)의 새 버전 알림으로. pipeline/tool_updates.py,
    레지스트리 수집이 거르기 전 최신 버전 목록을 넘김. 실측 본인 MCP 21개 중 4개 새 버전(anythingmcp 0.9.0 → 0.13.1 등). check_tool_updates 12(신규) 통과
  - 끝난 것(추천 기능 3): 금요일 메일 맨 아래 "이번 주 요약"(pipeline/weekly.py, 카드 데이터만·모델 없음). 따로 메일을 보내지 않는다.
    9/25 실데이터 미리보기: 7일 카드 46장, 큰 소식 1, 주제 상위 3, 설치 3개 중 2개 성공. check_weekly 9(신규) 통과. 첫 실제 적용은 10/2(금)
  - 로직 점검(사용자 "버그 없는지"): 새 버전 카드가 발송 전 검증 한도에 밀려 예전 버전 결과가 붙을 수 있던 것, 금요일 요약 설치 수에 원격 전용이
    섞이던 것 고침. 전체 오프라인 검수 46개 통과(모델·E2B 호출 0). 실제 모델·E2B 검수 10개는 작업 중 모델 호출 금지로 돌리지 않았다
  - 결정(사용자, 9/27 밤): RAG를 쌓인 데이터에만 붙인다. Supabase pgvector + 로컬 Ollama 임베딩, 별도 벡터 DB·라이브러리는 여전히 금지.
    질문창부터, 넣기 전후를 숫자로 비교. 순서: 9/28 새 기능 확인 → 선별 정밀도 개선 → RAG. 계획안 5장·1장 표·하지 않을 것·설계 이유 3 수정
  - 끝난 것(사용자 요청): 이용 신청서와 관리자 전용 승인 탭. 승인 전에는 브리핑·메일 없음(이미 그랬음), 초대 코드 화면에 신청서를 더했다.
    개발자 본인 계정은 ADMIN_EMAILS로 관리자이고 users.is_admin도 켰다. users에 application·applied_at 칸(init_db로 반영).
    주의: 개발 모드에서는 ADMIN_EMAILS만 로그인할 수 있어 신청서는 운영 모드로 열 때 실제로 쓰인다. check_apply 18(신규) 통과
  - 끝난 것(9/28 새벽, 사용자 요청): 승인 이력. status_changes 표(누가·누구를·이전→새 상태·언제·관리자인지 초대 코드인지),
    관리자 화면에 변경 이력과 마지막 결정. Langfuse는 AI·도구 호출 기록용이라 가입 관리 기록은 DB에 둔다. check_apply 24 통과
  - 사고(9/27 23:57): 자동 재시작 직후 런처(PowerShell)가 Ctrl+C 이벤트(0xC000013A)로 새 앱과 함께 끝났다. 00:10에 손으로 발견해 작업을 다시 시작.
    보낸 쪽은 모른다(9/15에도 한 번). 결정(사용자): 감시 작업을 10분마다, 꺼져 있으면 스스로 되살리게. 재현 시험에서 57초에 복구
  - 영어 뉴스 제목: 원문 제목 유지(추천. 링크와 같은 제목이 정확하고 [확정] 규격을 바꾸지 않는다)
  - 결정(사용자, 9/27): 작업 중 판정·검토는 Claude Code 모델이 한다. 로컬 Ollama·Groq로 돌리던 프롬프트 전후 비교는 멈췄다.
    그래서 프롬프트 효과는 모델로 재지 않았고 9/27 07:00 실행 결과를 Claude Code가 읽어 판단한다
  - 다음 시작점: 9/27 07:00이 MCP 발송 전 검증·홍보 거르기·문장 기준 첫 실행. app.log에서 실행 끝 시각(08:00 전인지), 보고의 mcps_probed,
    메일 MCP 카드에 "검증 예정" 대신 실제 결과가 붙었는지, 도구 카드에 같은 게시자가 반복되지 않는지 본다

- 세션 12 · 2026-09-23 · 스킬 수집(SkillsMP), 모델 출시 주제 관심도 올림
  - 결정(사용자): 스킬도 나오게 한다 / 주제 관심도 `model_release`를 5로 올린다 / 스킬 판독은 발송 전에 바로 한다
  - 끝난 것: sources/skillsmp.py(주제어 8개 검색·githubUrl로 합침·items에 없는 것만·게시자당 3건·별 수 상위 20건)와 collect 연결.
    본인(45) weights.model_release 2 → 5, 월요일 합치기가 되돌리지 않게 해당 주제 피드백의 weight_delta를 0으로
  - 검수: check_skillsmp 11(신규)·check_fallbacks·check_news_window·check_catalog_title·run_daily --fake·check_reject_rate·check_folder_docs 통과
  - 확인한 것(오퍼스 5.5가 본인 브리핑에 없던 일): 기사는 수집됐고 데모 프로필(113)에는 카드로 나갔다. 본인에게는 안 나갔다.
    처음에는 후보 60건 자르기에서 낮은 가중치 주제가 통째로 빠진 탓으로 봤는데, 오늘 데이터로 끝까지 돌려 보니 예전 방식에서도
    오퍼스 기사는 후보에 있었다(model_release 17건). 모델이 보고도 GPT-6 쪽을 골랐다. 진짜 원인은 뉴스 5장 상한과,
    자유 한 줄("새 모델 소식을 가장 먼저")과 어긋난 관심도(model_release 2 < agent_framework·coding_tools·mcp_tools 3)였다
  - 되돌린 것: 후보를 주제별로 돌아가며 담는 변경(_spread)을 만들었다가 지웠다. 검수에 "후보 단계는 가중치 높은 주제 먼저"가
    규칙으로 있고(계획안 부록 C 피드백 루프), 시뮬레이션에서도 이번 문제를 풀지 못했다
  - 관심도 5로 올린 뒤 같은 데이터 재시뮬레이션: 같은 후보에서 뉴스 5장 중 4장이 model_release가 되고 오퍼스 5.5가 3순위로 들어왔다(전에는 0장)
  - 스킬 발송 전 판독: run_daily.review_skills_now. 카드로 나갈 스킬(관련 카드 포함)을 하루 실행 안에서 판독해 그날 카드에 붙인다.
    이미 판독된 것·이번에 안 뽑힌 스킬은 건너뛰고 한 번에 5건, 실패해도 브리핑은 나간다. MCP는 E2B 설치 90초라 06:00 W1-a 그대로.
    check_skill_now 10항목(신규)·run_daily --fake·check_verifier·check_rollback·check_scheduler 통과. 9/23 10:20 앱 재시작으로 반영
  - 코드 수정 뒤 자동 재시작(사용자 요청): pipeline/autorestart.py. 예약 루프가 한 바퀴마다 main 새 커밋을 보고, 06~09시가 아니고
    실행·검증·재실행 예약이 없고 다음 예정 작업까지 10분 넘게 남았으면 스스로 꺼져 런처가 새 코드로 띄운다. 기능 브랜치·커밋 안 한 수정이면 기다림.
    check_autorestart 14항목(신규)·check_scheduler·check_skill_now·run_daily --fake·check_folder_docs 통과. 이제 손 재시작은 필요 없다
  - 보강 3건(사용자 요청 "전체적으로 수정해"):
    ① 앱 바깥 감시 pipeline/watchdog.py + Windows 작업 `toolscout watchdog`(08:30·09:30·12:30·18:30). 앱 무응답·브리핑 없음·미발송·DB 실패를 알림
    ② 선별 주제 분류: 주제별 경계(schemas.TOPIC_GUIDE). 9/23 뉴스 고정 비교에서 사람 판정과 일치 56% → 70%(로컬 모델 한계로 보임)
    ③ 같은 소식 겹침 빼기 agent/same_story.py: 해설가 모델 순서를 빌려 같은 사건은 하나만, 빈 자리는 안 채움
    남은 것: tests/pipeline/run_daily --fake가 가끔 실패(장애 전후 briefings 비교가 조회 순서에 따라 달라지는 것으로 보임).
    9/25 고침: 조회에 ORDER BY가 없었다. 상세는 tests/CHANGELOG
  - 오늘의 큰 소식(agent/headline.py): 여러 곳이 다룬 소식을 관심도와 상관없이 뉴스 맨 위에 1칸, 두 번째도 8점 이상이면 2칸
  - 결정(사용자): 뉴스 중요도는 Jev(agent/importance.py, models.JEV), 같은 소식 묶기는 OpenRouter 유료 단일 모델(models.SINGLE_MODEL_ROLES).
    OpenRouter는 사용자가 정한 모델만 쓰고 다른 모델을 시험하지 않는다. Jev 키는 jevtypesafeai.com(비공식 재판매) 것이라 그 사이트 주소로 부른다
  - 저장소 흔적 정리: .gitignore의 로컬 도구 항목을 .git/info/exclude로, agent/probe.py 설명 문구 정리. 과거 기록 다시 쓰기는 권한에서 막혀 보류
  - 주의: pipeline/run_daily.py가 300줄이 됐다. 더 늘리기 전에 나눌지 물어야 한다 (작업 규칙)
  - 다음 시작점(9/24 아침에 볼 것): ① 스킬 카드가 실제로 나오는지, 나왔다면 "SKILL.md 읽어봤더니"에 판독 예정이 아닌 결과가 붙었는지
    ② 오퍼스 5.5가 본인 브리핑에 들어왔는지(관심도 5로 올린 효과) ③ 메일이 본인 구역 하나로만 오는지, 새 메일 모양이 폰에서 읽을 만한지
    → 결정 대기: 뉴스 상한 5장을 올릴지 / 묶음 메일 표시를 한 사람용으로 바꿀지

- 세션 11 · 2026-09-22 · 메일 가독성, 검수용 프로필 끄기, 어제 수정의 반영 여부 확인
  - 결정(사용자): 검수를 마쳤으니 가짜 프로필 A·B·C(user 1·2·3)는 하루 실행과 메일에서 뺀다. 지우지 않고 status를 blocked로 둔다
    (되돌리려면 approved). 하루 실행 대상은 본인 계정(45)과 데모(113)만 남는다
  - 끝난 것: 메일 모양 정리(어두운 머리·요일, 종류 칩·제목·요약·나한테는 순의 무게, 장단점 한 줄, 근거는 원문과 다를 때만,
    묶음 메일 머리 한 번, 웹앱 색 토큰), run_daily --fake가 검수 동안만 프로필을 승인했다가 되돌리게
  - 검수: check_mail_layout 12(신규)·check_deliver·run_daily --fake·check_scheduler·check_reject_rate·check_access·check_folder_docs 통과
  - 확인: 예약 실행은 앱 프로세스 안에서 돌아서 코드를 고치면 앱을 재시작해야 반영된다. 9/21 19:55 재시작 뒤 커밋한
    도구 목록 제목(22:51)·해설가 반려 기준(23:00)은 9/22 07:00 실행에 들어가지 않았다. 9/22 20:33 재시작으로 9/23부터 적용.
    9/22 반려 감소(17→12)는 그래서 해설가 수정 효과가 아니다. 제목은 보정해 둔 덕에 새로 쌓인 이름 제목 0건으로 피해 없음
  - 9/22 실행: 후보 213건(48시간 창으로 142에서 늘어남), 06:55 예열·07:27 마지막 호출·08:00 발송으로 제시간. 형식 실패 0,
    explainer groq 429 10회(가짜 프로필 셋을 빼서 해설 호출이 줄어들 것). Jev는 레딧 글 1건만 들어갔고 AI타임스 제브 기사(9/20 17:40)는
    48시간 창 안이었지만 뽑히지 않았다(선별은 모델 판단이라 보장되지 않는다. 한·영 같은 소식 묶기가 없는 것도 한 원인)
  - 다음 시작점: 9/23 07:00이 해설가 반려 기준이 실제로 적용되는 첫 실행이다. 본인 계정 반려 수(9/22 3건)와 카드 수를 본다
    → 코드 수정 뒤 재시작을 잊지 않게 할 방법 결정(사용자 결정 대기) → 묶음 메일은 이제 프로필 하나라 묶음 표시를 둘지

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
  - 첫 월요일 관련 카드(F3-b) 실제 확인: 11건 생성, 관련도 3~5, for_me 75~108자. 기능은 통과.
    마케터만 0건인데 도구 목록에 notion 관련이 0건이라 매칭될 게 없었다(수집 범위 문제)
  - 이어서 고친 것 셋
    1) 도구 목록 제목이 저장소 이름으로 굳던 문제: 별 수 캐시가 표시명을 안 보고 두 upsert가 title을 갱신하지 않아
       56건 중 55건이 io.github 형태였고 관련 카드 11건이 전부 그렇게 나갔다. display_title로 규칙을 모으고 upsert에 title 추가,
       backfill_titles로 기존 40건 보정(표시명 없음 12, 못 찾음 0)
    2) 해설가가 큐레이터 선택을 과하게 뒤집던 문제: 자유 한 줄에 적힌 지금 하는 일에 그대로 쓸 수 있는지로만 보아
       백엔드 7건 중 6건 반려, 마케터는 9/18·19 후보 8건 전부 반려로 브리핑이 비었다. for_me 범위를 넓히고 반려 조건을 좁혔다.
       실측으로 반려됐던 3건이 모두 관련도 3으로 회복, 무관한 대조 항목은 계속 반려, 마케터 프로필도 2건 회복
    3) 검수 클라이언트가 secure 쿠키를 못 받던 문제: APP_BASE_URL이 https라 쿠키가 secure로 발급되는데 TestClient가 http로
       요청해 로그인 검수가 401로 깨졌다(코드 버그 아님). 검수 클라이언트를 https://testserver로
  - 검수: check_catalog_title 9(신규)·check_reject_rate 5(신규)·run_daily --fake 전체·check_design·check_auth·check_settings·
    check_briefings·check_feedback·check_ask·check_access·check_fallbacks·check_news_window·check_folder_docs 통과
  - 다음 시작점: 9/22 07:00이 48시간 창·새 제목·새 반려 기준으로 도는 첫 실행이다. 반려율과 카드 수를 본다
    (바로잡음 9/22: 제목·반려 기준 수정은 19:55 재시작 뒤에 커밋돼 9/22 실행에 반영되지 않았다. 세션 11 참고)
    → 묶음 메일 본인 구역 순서(사용자 결정 대기) → 마케터 수집 범위(개발자용 MCP만 들어와 붙을 도구가 없다)

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
