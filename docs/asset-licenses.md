# 외부 자산과 라이선스 기록

웹앱·메일에 들어간 아이콘·그림·글꼴의 출처와 라이선스. 새 자산을 넣거나 버전을 바꾸면 이 표를 같이 고친다. 확인일은 모두 2026-10-14.

## 표

| 파일 | 출처 | 라이선스 | 원문 URL | 가공 |
|---|---|---|---|---|
| `web/app.js` `TS.ICONS`(34종) | lucide-static 1.57.0 (`https://unpkg.com/lucide-static@1.57.0/icons/<이름>.svg`) | ISC, Feather 유래분은 MIT | https://github.com/lucide-icons/lucide/blob/main/LICENSE | 요소만 꺼내 같은 path를 한 d로 이었다(모양 같음). 선 굵기는 CSS `.ic` 1.5로 덮음. 고지 전문 `docs/licenses/lucide.txt`, app.js 둘째 줄 `/*!` 고지 |
| `web/img/illus.svg` `#pending`의 모래시계, `#done`의 봉투 | lucide-static 1.57.0 hourglass, mail | ISC | 위와 같음 | 3.5배·4.5배로 키우고 `vector-effect="non-scaling-stroke"`로 선 2px 유지, 강조 점을 더함 |
| `web/img/illus.svg` 나머지(`#empty`·`#dawn` 전부, 지평선·시계) | 자체 제작 | 우리 것 | 없음 | 디자인 회의 1장 1-6 원본 그대로, `#dawn`은 2라운드 1장 2판 1-6 원본 그대로 |
| `web/icons/mark.svg`, `TS.ICONS.mark`, `web/icons/icon.svg` | 자체 제작 "아침 프롬프트" 마크 | 우리 것 | 없음 | 상단바용은 32 격자를 0.75배, 파비콘은 작은 크기용으로 선을 굵게 하고 타일(#15181E)을 깜 |
| `web/icons/icon-192.png`·`icon-512.png`·`apple-touch-icon.png`, `web/img/mail/mark-56.png`·`empty-192.png` | 자체 제작(위 SVG를 굽기) | 우리 것 | 없음 | 루트 `bake_icons.py`가 Edge 헤드리스로 굽는다. 바탕 불투명 |
| JetBrains Mono Variable (`--mono`) | @fontsource-variable/jetbrains-mono 5.3.0, jsDelivr | OFL-1.1 | https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt | 없음(CDN 링크, 글꼴 파일을 저장소에 두지 않음) |
| Pretendard Variable (`--sans`) | orioncactus/pretendard v1.3.9 dynamic subset, jsDelivr | OFL-1.1 | https://github.com/orioncactus/pretendard/blob/main/LICENSE | 없음(CDN 링크) |

## TS.ICONS 키 → Lucide 이름
ok circle-check · bad circle-x · warn triangle-alert · na circle-dashed · key key-round · shield shield-check · risk shield-alert · clock clock · ext external-link · copy copy · star star · flag flag · mute eye-off · tried check · chev chevron-down · chat message-square-text · today newspaper · history history · settings sliders-horizontal · approve user-check · search search · logout log-out · arrow arrow-right · back arrow-left · eye eye · mail mail · close x · filter list-filter · refresh refresh-cw · up arrow-up · play play · lock lock · info info · wait hourglass · mark(자체 제작)

## 쓰지 않기로 한 것
- Open Doodles(CC0): 라이프스타일처럼 읽혀 주제와 맞지 않음 / unDraw: AI 학습 금지·묶음 재배포 금지 조항 / Open Peeps: 받는 경로가 불안정 / Tabler: 예비안
- Google 로그인 G 로고는 Google 지침에 따른 사용이라 그대로 둔다(이 표의 가공 대상 아님).
