/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */
// 브리핑 카드와 오늘 배치 (오늘·지난 브리핑·예시 공용, 2026-10-14 2차 리디자인, 2026-10-15 2라운드). 모양은 web/cards.css, 견본은 docs/design-reference.html
// 카드 겉면: 머리줄[꼭지 글 | 판정 배지] → 제목 → 메타 줄 → 요약 → 나에게(점선 괘선) → 판정(도구만: 통과 한 줄 / 문제 2×2) → 고정 문구 → $ 설치 명령 → 버튼 줄
// 세 무게(모양은 cards.css): 큰 소식 첫 장 = 리드(상자 없음), 둘째 큰 소식(위 1px 괘선), 뉴스(.nw, 상자 없는 괘선 목록), 도구만 상자. '자세히' 안: 장단점 → 검증 세부 → 왜 이 카드 → 트레이스
const Cards = {
  readonly: false,  // 공개 데모(/demo)·첫 화면 예시: 피드백 버튼 없이 읽기만 (2026-09-16)
  REASONS: ["번역 어색", "사실 틀림", "나랑 상관없음"], TOOL_TYPES: ["mcp", "skill"],
  STEPS: ["설치", "실행", "도구 목록", "인증"], STEP_KEYS: ["install", "run", "tools_list", "auth_required"],
  MCP_SCOPE: "도구가 올바르게 동작하는지는 범위 밖입니다.",
  SKILL_SCOPE: "안전 보증이 아니라 위험 신호 표시입니다.",
  AI_NOTE: "요약은 원문을 바탕으로 AI가 썼습니다. 중요한 결정 전에는 원문 링크를 확인하세요.",
  // 검증 칸 값(pipeline/verification.py card_verification) → 모양. 키가 없어 못 띄운 것(warn)은 결함이 아니라 중립 열쇠
  CHIP: { ok: "ok", success: "ok", fail: "bad", bad: "bad", error: "bad", warn: "key", auth: "key", na: "na" },
  // 스킬 위험 신호 단계 → [배지 모양, 아이콘, 낱말]. 낱말은 tests/web/verdict_cases.json·메일과 같다
  RISK: { ok: ["pass", "shield", "정상"], caution: ["warn", "risk", "주의"], unverified: ["warn", "risk", "확인 필요"], skipped: ["plain", "na", "생략"] },
  ACTIONS: { "써봤음": ["tried", "써봤어요"], "관심없음": ["mute", "관심없음"], "이상함": ["flag", "이상함 표시됨"] },  // [아이콘, 눌렸을 때 글자(768 이상)]
  DOT: '<span aria-hidden="true">·</span>',
  opts: { day: "오늘", level: 3, abs: false, weights: null }, seq: 0,
  hd(plus = 0) { return `h${Math.min(6, Cards.opts.level + plus)}`; }, id(card) { return card.item_id != null ? String(card.item_id) : (card._id ||= `x${++Cards.seq}`); },  // 도구 줄이 같은 id를 다시 쓴다
  isTool(card) { return Cards.TOOL_TYPES.includes(card.type); },
  // 제목: tabindex -1이라 '오늘 한눈에'에서 누르면 여기로 포커스가 온다
  title(card, text, id) {
    const url = TS.safeUrl(card.url), tt = `<span class="tt">${TS.esc(text)}</span>`;
    return `<${Cards.hd()} class="c-title" id="t-${id}" tabindex="-1">${url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">${tt}${TS.ic("ext")}<span class="sr-only">(새 탭)</span></a>` : tt}</${Cards.hd()}>`;
  },
  // 주제 이름만(꼭지 글·메타 줄). 내 관심도 숫자는 '왜 이 카드?'로 옮겼다
  topic(card) { return card.topic_label ? `<span class="topic">${TS.esc(card.topic_label)}</span>` : ""; },
  weight(card) { const w = Cards.opts.weights && card.topic ? Cards.opts.weights[card.topic] : null; return w == null ? "" : w > 0 ? `+${w}` : `${w}`; },
  // 오늘은 상대 시각, 지난 브리핑(opts.abs)은 mono 절대 시각 "10.06 14:20"
  when(iso) {
    const abs = iso ? TS.stamp(iso) : "", hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
    if (!abs) return ""; if (Cards.opts.abs) return `<time class="abs" datetime="${TS.esc(iso)}">${abs}</time>`;
    return `<time datetime="${TS.esc(iso)}" title="${abs}">${hours < 1 ? "방금" : hours < 24 ? `${hours}시간 전` : `${Math.floor(hours / 24)}일 전`}</time>`;
  },
  // 판정 배지 {word, tone, icon} 또는 null. 웹·메일·'오늘 한눈에'가 같은 낱말 (tests/web/verdict_cases.json)
  badge(card) {
    const B = (word, tone, icon) => ({ word, tone, icon });
    if (card.type === "skill") {
      const r = typeof card.risk_signal === "string" ? { level: card.risk_signal } : card.risk_signal, b = r && Cards.RISK[r.level];
      return b ? B(`위험 신호 ${b[2]}`, b[0], b[1]) : B("미판독", "plain", "na");
    }
    if (card.type !== "mcp") return card.notice ? B(String(card.notice), "warn", "warn") : null;
    if (!card.verification) return B("미검증", "plain", "na");
    const cls = Cards.STEP_KEYS.map((key, n) => Cards.step(card.verification[key], n).cls);
    return cls.includes("bad") ? B("검증 실패", "bad", "bad") : cls.includes("key") ? B("키 필요", "plain", "key") : cls[2] === "ok" ? B("검증 통과", "pass", "ok") : B("미확인", "plain", "na");
  },
  pill(b) { return b ? `<span class="pill pill-${b.tone}">${TS.ic(b.icon)}${TS.esc(b.word)}</span>` : ""; },
  forme(card) { return card.for_me ? `<div class="forme"><b>나에게</b><p>${TS.esc(card.for_me)}</p></div>` : ""; },
  // 레지스트리 이름 "com.apify/apify-mcp-server 0.15.7" → 이름·버전·네임스페이스
  toolName(title) {
    const m = String(title).match(/^(.*?)(?:\s+v?(\d+(?:\.\d+)+[\w.-]*))?$/), ns = (m[1] || "").match(/^([a-z0-9-]+(?:\.[a-z0-9-]+)+)\/(.+)$/i);
    return { name: ns ? ns[2] : m[1], version: m[2] || "", namespace: ns ? ns[1] : "" };
  },
  // MCP 레지스트리 네임스페이스가 도메인 인증(com.회사 등)이면 공식, GitHub 계정 인증(io.github.*)이면 커뮤니티
  // GitHub 검색으로 모은 항목(item_meta.source === "github_search")은 출처를 "GitHub"로 보인다 (레지스트리 인증이 없어 공식/커뮤니티를 가르지 않는다)
  kind(card, namespace) {
    const github = (card.item_meta || {}).source === "github_search";
    if (card.type === "skill") return ["스킬", /github\.com\/anthropics\//.test(card.url) ? "공식" : github ? "GitHub" : "커뮤니티"];
    return ["MCP", github ? "GitHub" : !namespace ? "" : namespace.startsWith("io.github.") ? "커뮤니티" : "공식"];
  },
  DIST: [[/^https?:\/\//, "원격 전용"], [/^(npx|npm|pnpm|bunx)\b/, "npm"], [/^(uvx|pip|pipx|uv)\b/, "PyPI"], [/^docker\b/, "Docker"]],
  distribution(cmd) { return (Cards.DIST.find(([re]) => re.test(cmd || "")) || [null, ""])[1]; },
  // 검증 한 칸: 겉면은 짧은 말(성공·실패·키 필요·미확인·N개), 자세히에는 서버 문구 그대로
  step(value, n) {
    const state = value && typeof value === "object" ? value.status : value, label = (value && typeof value === "object" && value.label) || Cards.STEPS[n];
    const cls = Cards.CHIP[state] || "na", count = /도구 (\d+)개/.exec(label);
    const short = cls === "key" ? "키 필요" : cls === "bad" ? "실패" : cls === "na" ? (/해당없음/.test(label) ? "해당없음" : "미확인")
      : n === 2 && count ? `${count[1]}개` : n === 3 ? "필요 없음" : "성공";
    return { k: Cards.STEPS[n], cls, short, label };
  },
  // 판정 자리. MCP: 모두 통과(인증만 키 필요·미확인 포함)면 한 줄, 문제가 있으면 2×2, 결과 없음은 미검증 한 줄. 스킬은 risk()
  verify(card) {
    if (card.type === "skill") return Cards.risk(card);
    const v = card.verification, scope = (pre) => `<p class="scope">${pre}${Cards.MCP_SCOPE}</p>`;
    if (!v) return `<p class="verdict na">${TS.ic("na")}<span>${TS.esc(card.verification_note || "아직 직접 설치해 보지 않았어요")}</span></p>${scope("")}`;
    const cells = Cards.STEP_KEYS.map((key, n) => Cards.step(v[key], n)), cls = cells.map((c) => c.cls), m = (x) => `<span class="mono">${TS.esc(x)}</span>`;
    const at = v.probed_at ? `샌드박스 확인 ${m(String(v.probed_at).replace(/\s*샌드박스$/, ""))} · ` : "";
    const remote = /^https?:/.test(card.install_cmd || "") || (cells[0].short === "해당없음" && cells[1].short === "해당없음");
    if (!cls.includes("bad") && cls[2] === "ok" && cls[0] !== "key" && cls[1] !== "key" && (remote || (cls[0] === "ok" && cls[1] === "ok"))) {
      const tools = /^(\d+)개$/.exec(cells[2].short), key = /[A-Z][A-Z0-9_]{2,}/.exec(cells[3].label);
      const parts = [remote ? "원격 연결" : `${m(cls.filter((c) => c === "ok").length)}단계 통과`, tools ? `도구 ${m(tools[1])}개` : "",
        cls[3] === "key" ? (key ? `${m(key[0])} 필요` : "키 필요") : cls[3] === "na" ? "인증 미확인" : ""].filter(Boolean);
      return `<p class="verdict">${TS.ic("ok")}<span>${parts.join(" · ")}</span></p>${scope(at)}`;
    }
    const said = `검증: ${cells.map((c) => `${c.k} ${c.short}`).join(", ")}`;
    return `<div class="verify" role="group" aria-label="${TS.esc(said)}">${cells.map((c) =>
      `<div class="vc ${c.cls}"><span class="k">${c.k}</span><span class="v">${TS.ic(c.cls)}${TS.esc(c.short)}</span></div>`).join("")}</div>${scope(at)}`;
  },
  // 스킬 판독: 단계 낱말은 배지가 맡고, 본문은 걸린 항목 칩(있을 때만) + 고정 문구·검토 시각
  risk(card) {
    const r = typeof card.risk_signal === "string" ? { level: card.risk_signal } : card.risk_signal, hits = ((r && r.hits) || []).filter(Boolean);
    const bits = [Cards.SKILL_SCOPE, r && r.reviewed_at ? `검토 <span class="mono">${TS.esc(r.reviewed_at)}</span>` : "",
      card.verification_note ? TS.esc(card.verification_note) : r ? "" : "판독 예정"].filter(Boolean);
    return `${hits.length ? `<p class="hits"><span class="k">걸린 항목</span>${hits.map((h) => `<span>${TS.esc(h)}</span>`).join("")}</p>` : ""}<p class="scope">${bits.join(" · ")}</p>`;
  },
  // 설치 명령(겉면): $ 프롬프트 + mono 한 줄(가로 스크롤) + 복사. 원격 주소면 $ 없이 라벨
  cmd(card) {
    const c = card.install_cmd, remote = /^https?:/.test(c || ""), what = remote ? "원격 주소" : "설치 명령"; if (!c) return "";
    return `<div class="cmd">${remote ? `<span class="cmd-k">${what}</span>` : ""}<pre tabindex="0" role="region" aria-label="${what}">${remote ? "" : '<span class="p" aria-hidden="true">$ </span>'}${TS.esc(c)}</pre>
      <button type="button" data-copy="${TS.esc(c)}" aria-label="${what} 복사">${TS.ic("copy")}<span class="lab">복사</span></button></div>`;
  },
  // ===== 자세히 =====
  points(title, sign, list) { if (!list || !list.length) return "";
    return `<div><${Cards.hd(1)} class="d-h">${title}</${Cards.hd(1)}><ul>${list.map((p) => {
      const url = TS.safeUrl(p.evidence_url);
      return `<li><span class="g" aria-hidden="true">${sign}</span><span>${TS.esc(p.text)}${url ? ` <a class="ev" href="${TS.esc(url)}" target="_blank" rel="noopener">근거${TS.ic("ext", "ic-12")}</a>` : ""}</span></li>`;
    }).join("")}</ul></div>`;
  },
  pc(card) { const both = Cards.points("좋은 점", "+", card.pros) + Cards.points("아쉬운 점", "−", card.cons); return both ? `<div class="pc">${both}</div>` : ""; },
  verifyRows(card) {
    const v = card.verification, hd = Cards.hd(1), r = card.risk_signal && typeof card.risk_signal === "object" ? card.risk_signal : null;
    if (card.type === "skill") {
      if (!r || !(r.quote || r.basis)) return "";
      return `<div><${hd} class="d-h">걸린 근거</${hd}>${r.quote ? `<div class="cmd"><pre class="wrap-text" tabindex="0">${TS.esc(r.quote)}</pre></div>` : ""}
        <p class="scope">${[r.basis, r.completeness ? `충실도 ${r.completeness}` : ""].filter(Boolean).map(TS.esc).join(" · ")}</p></div>`;
    }
    if (!v) return "";
    const rows = Cards.STEP_KEYS.map((key, n) => Cards.step(v[key], n))
      .map((c) => `<div class="vrow ${c.cls}">${TS.ic(c.cls)}<b>${c.k}</b><span class="val">${TS.esc(c.label)}</span></div>`).join("");
    return `<div><${hd} class="d-h">샌드박스 검증</${hd}><div class="vrows">${rows}</div></div>`;
  },
  why(card) {
    const n = Number(card.relevance), w = Cards.weight(card), hd = Cards.hd(1);
    const nums = [n >= 1 && n <= 5 ? `나와 관련 <span class="mono">${n}/5</span>` : "", w ? `${TS.esc(card.topic_label || "")} 관심도 <span class="mono">${w}</span>` : ""].filter(Boolean);
    return `<div class="why"><${hd} class="d-h">왜 이 카드?</${hd}><p>${TS.esc(card.why_this_card || "")}</p>${nums.length ? `<p class="nums">${nums.join(" · ")}</p>` : ""}</div>`;
  },
  // 관리자만: API가 Langfuse 주소를 주면 링크, 주소 설정이 없으면 "trace_id ..." 글자 + 복사
  trace(card) {
    const t = card.trace_url, tag = `<span class="tag-mode tag-admin">${TS.ic("lock")}관리자</span>`; if (!t) return "";
    if (TS.safeUrl(t)) return `<div class="trace">${tag}<a href="${TS.esc(t)}" target="_blank" rel="noopener">Langfuse 트레이스 열기${TS.ic("ext")}<span class="sr-only">(새 탭)</span></a></div>`;
    return `<div class="trace">${tag}<span>트레이스 주소가 설정되지 않아 id만 보여요</span><div class="cmd"><pre tabindex="0" aria-label="trace id">${TS.esc(t)}</pre>
      <button type="button" data-copy="${TS.esc(t)}" aria-label="trace id 복사">${TS.ic("copy")}<span class="lab">복사</span></button></div></div>`;
  },
  // ===== 피드백: 쉴 때 테두리 없는 글자 버튼. 눌림(aria-pressed)은 체크 + blaze 테두리, 글자 변화는 768 이상만(cards.css가 고름) =====
  fb(card, actions) {
    const on = new Set((card.feedback || {}).actions || []);
    return Cards.readonly ? "" : `<div class="fb">${actions.map((a) => `<button type="button" data-action="${a}" data-item="${TS.esc(card.item_id)}" aria-pressed="${on.has(a)}">${TS.ic(Cards.ACTIONS[a][0], "ic-act")}${TS.ic("tried", "ic-on")}<span class="lab">${a}</span><span class="lab-on">${Cards.ACTIONS[a][1]}</span></button>`).join("")}</div>`;
  },
  follow(card, id) {
    const f = card.feedback || {}, on = new Set(f.actions || []), ids = f.ids || {}; if (Cards.readonly) return "";
    const odd = `<div class="follow" data-follow="이상함" data-fid="${TS.esc(ids["이상함"] || "")}"${on.has("이상함") ? "" : " hidden"}><fieldset class="rbtns">
      <legend class="q">무엇이 이상했나요? 고르지 않아도 돼요</legend>${Cards.REASONS.map((r) => `<button type="button" class="rbtn" data-reason="${r}" aria-pressed="${f.reason === r}">${r}</button>`).join("")}</fieldset></div>`;
    if (!Cards.isTool(card)) return odd;
    return `${odd}<div class="follow" data-follow="써봤음" data-fid="${TS.esc(ids["써봤음"] || "")}"${on.has("써봤음") ? "" : " hidden"}><label class="q" for="memo-${id}">써 본 소감 한 줄 (선택)</label>
      <div class="row"><input class="input" id="memo-${id}" type="text" maxlength="200" value="${TS.esc(f.memo || "")}"><button type="button" class="btn btn-sm" data-memo>저장</button></div></div>`;
  },
  // 카드 한 장. surface = 머리줄~설치 명령, actions = 피드백 버튼, detail = 자세히 앞부분. 예시(readonly) 힌트는 버튼 줄 아래
  wrap(card, id, cls, surface, actions, detail, text) {
    const muted = !Cards.readonly && ((card.feedback || {}).actions || []).includes("관심없음");
    const hint = Cards.readonly && !Cards.hinted ? `<p class="hint-line">${TS.ic("info")}로그인하면 관심없음·써봤음·이상함으로 다음 날 추천을 바꿀 수 있어요.</p>` : "";
    Cards.hinted = Cards.hinted || Cards.readonly;
    return `<article class="card${cls}${muted ? " is-muted" : ""}" id="card-${id}" data-item="${TS.esc(card.item_id ?? "")}" data-topic="${TS.esc(card.topic || "")}" aria-labelledby="t-${id}">
      ${surface}<div class="c-foot"><button class="more" type="button" aria-expanded="false" aria-controls="d-${id}">자세히${TS.ic("chev")}</button>${Cards.fb(card, actions)}</div>${hint}
      ${Cards.follow(card, id)}<div class="detail" id="d-${id}" hidden>${detail}${Cards.why(card)}${Cards.trace(card)}</div>
      ${Cards.readonly ? "" : `<div class="muted-line"><span class="lab">관심없음으로 표시함</span><span class="t">${TS.esc(text)}</span><button type="button" class="btn btn-sm" data-undo>되돌리기</button></div>`}
    </article>`;
  },
  head(kicker, card) { const b = Cards.pill(Cards.badge(card)); return kicker || b ? `<div class="c-head">${kicker}${b}</div>` : ""; },
  // 뉴스 카드(.nw). hl이면 업계 큰 소식(관심도와 상관없이 맨 위라 관심없음 버튼 없음). 폰 뉴스는 요약을 '자세히' 펼침 맨 위로(cards.css order)
  news(card, hl = false) {
    const id = Cards.id(card), host = TS.host(card.url), meta = [host ? `<span>${TS.esc(host)}</span>` : "", Cards.when((card.item_meta || {}).published_at)].filter(Boolean);
    const surface = `${Cards.head(Cards.topic(card), card)}${Cards.title(card, card.title, id)}${meta.length ? `<p class="meta">${meta.join(Cards.DOT)}</p>` : ""}
      <p class="c-sum">${TS.esc(card.summary_ko)}</p>${Cards.forme(card)}`;
    return Cards.wrap(card, id, hl ? " hl" : " nw", surface, hl ? ["이상함"] : ["관심없음", "이상함"], Cards.pc(card), card.title);
  },
  tool(card) {
    const id = Cards.id(card), meta = card.item_meta || {}, { name, version, namespace } = Cards.toolName(card.title);
    const [kindName, kindSrc] = Cards.kind(card, namespace), ver = version || meta.version || "", dist = Cards.distribution(card.install_cmd);
    const stars = meta.stars != null ? Number(meta.stars).toLocaleString("ko-KR") : "", ago = meta.published_at ? TS.daysAgo(meta.published_at) : "";
    const metaParts = [dist ? `<span>${dist}</span>` : "", stars ? `<span class="star">${TS.ic("star", "ic-12")}<span aria-label="GitHub 별 ${stars}개">${stars}</span></span>` : "",
      ago ? `<span>${ago} 등록</span>` : "", Cards.topic(card)].filter(Boolean);  // '3일 전 등록'·'오늘 등록'(메일과 같은 어순)
    const surface = `${Cards.head(`<span class="kind">${kindName}${kindSrc ? ` · ${kindSrc}` : ""}</span>`, card)}
      <div class="t-name">${Cards.title(card, name, id)}${ver ? `<span class="ver">v${TS.esc(ver.replace(/^v/, ""))}</span>` : ""}</div>
      ${metaParts.length ? `<p class="meta">${metaParts.join(Cards.DOT)}</p>` : ""}<p class="c-sum">${TS.esc(card.summary_ko)}</p>${Cards.forme(card)}
      <div class="judge">${Cards.verify(card)}</div>${Cards.cmd(card)}`;
    return Cards.wrap(card, id, "", surface, ["써봤음", "관심없음", "이상함"], Cards.pc(card) + Cards.verifyRows(card), name);
  },
  card(card) { return Cards.isTool(card) ? Cards.tool(card) : Cards.news(card, Boolean(card.headline)); },
  // 빈 상태 상자: 그림(dawn = 곧 와요, empty = 다 살펴봤지만 고를 게 없음) 왼쪽(폰은 위) + 제목·본문·버튼. index 인라인 script도 쓴다
  empty(h, pic, title, body) { return `<section class="empty empty-ill" aria-labelledby="empty-h"><svg class="ill" viewBox="0 0 160 120" aria-hidden="true" focusable="false"><use href="/static/img/illus.svg#${pic}"/></svg><div class="empty-b"><${h} id="empty-h">${title}</${h}>${body}</div></section>`; },
  // ===== 오늘 배치: 큰 소식 → 뉴스 → 새 MCP·스킬(월요일 관련 카드는 그 아래) → 다 봤어요. 한 열. 0건이면 Cards.empty(그림 #empty, 웹·메일 같은 문구) =====
  // opts: day("오늘"·"이날"·"예시"), level(카드 제목 h 단계, 기본 3), abs(절대 시각), weights(주제 관심도). 화면에 #toc가 있으면 '오늘 한눈에'(큰 소식·뉴스), #tool-rows가 있으면 도구 줄 목록을 채운다(레일). 거르기·관심없음으로 숨긴 카드는 목록에서도 숨김
  mount(container, briefing, opts = {}) {
    if (typeof opts === "string") opts = { day: opts };  // 예전 부르기: Cards.mount(el, briefing, "이날")
    const o = Cards.opts = { day: "오늘", level: 3, abs: false, weights: null, ...opts }, h = `h${o.level - 1}`, cards = briefing.cards, rows = document.getElementById("tool-rows");
    Cards.hinted = false;
    if (rows) rows.innerHTML = cards.length ? Cards.toolRows(cards) : "";
    if (!cards.length) {
      const acts = `<div class="acts"><a class="btn btn-primary" href="/settings#topics">관심 주제 넓히기</a>${o.day === "오늘" ? '<a class="btn" href="/history">지난 브리핑 보기</a>' : ""}</div>`;
      container.innerHTML = briefing.exists ? Cards.empty(h, "empty", `${o.day}은 볼 만한 게 없었어요`, `<p>모은 소식과 도구를 살펴봤지만 내 기준에 맞는 게 없어 억지로 채우지 않았어요.</p>${briefing.empty_reason
        ? `<p class="note">선별 기록 · ${TS.esc(briefing.empty_reason)}</p>` : ""}${Cards.readonly ? "" : acts}`) : Cards.empty(h, "dawn", `아직 ${o.day} 브리핑이 없어요`, "<p>매일 아침 08:00에 메일로도 보내요.</p>");
      return Cards.toc(container);
    }
    const hl = cards.filter((c) => c.headline && !Cards.isTool(c) && !c.related), news = cards.filter((c) => !c.headline && !Cards.isTool(c) && !c.related);
    const tools = cards.filter((c) => Cards.isTool(c) && !c.related), related = cards.filter((c) => c.related);
    const head = (id, title, n, hint) => `<div class="lane-h${id ? "" : " sub"}"><${h}${id ? ` id="${id}-h"` : ""}>${title}</${h}><span class="n">${n}</span>${hint ? `<span class="hint">${hint}</span>` : ""}</div>`;
    const band = hl.length ? `<section class="hl-band" id="hl" aria-labelledby="hl-h"><div class="band-h"><${h} id="hl-h">업계 큰 소식</${h}><span class="hint">모두에게 같은 소식</span></div>${hl.map(Cards.card).join("")}</section>` : "";
    const newsLane = `<section class="lane" id="news" aria-labelledby="news-h">${head("news", "뉴스", news.length, "")}${news.map(Cards.card).join("") || `<p class="help">${o.day} 뉴스 카드는 없어요</p>`}</section>`;
    const toolLane = `<section class="lane" id="tools" aria-labelledby="tools-h">${head("tools", "새 MCP·스킬", tools.length, "7일 안 새로 등록")}${tools.map(Cards.card).join("") || `<p class="help">${o.day} 새 도구는 없어요</p>`}
      ${related.length ? head("", "이번 주 관련 MCP·스킬", related.length, "날짜와 상관없이 내 도구와 겹치는 것") + related.map(Cards.card).join("") : ""}</section>`;
    const acts = o.day === "오늘" && !Cards.readonly ? `<div class="acts"><button type="button" class="btn" data-ask data-ask-opt aria-haspopup="dialog" aria-expanded="false">${TS.ic("chat")}질문하기</button>
      <a class="btn" href="/history">${TS.ic("history")}지난 브리핑 보기</a></div>` : "";
    const endcap = `<section class="endcap" aria-label="목록 끝"><p class="end-h"><span>다 봤어요 · ${o.day} <span class="mono">${cards.length}</span>장</span></p>${acts}<p class="ai-note">${Cards.AI_NOTE}</p></section>`;
    container.innerHTML = `<div class="brief">${band}<div class="board">${newsLane}${toolLane}</div>${endcap}</div>`;
    if (!container.dataset.cards) { container.dataset.cards = "1"; container.addEventListener("click", Cards.onClick); }
    Cards.toc(container);
    Cards.openHash();
  },
  // 레일 '오늘 한눈에'(큰 소식·뉴스만, 도구는 도구 줄 목록이 맡는다): 그려진 카드에서 제목·배지를 읽어 한 줄씩. 누르면 그 카드로 스크롤하고 제목에 포커스
  toc(container) {
    const box = document.getElementById("toc"); if (!box) return;
    box.innerHTML = [["hl", "큰 소식"], ["news", "뉴스"]].map(([sec, label]) => {
      const rows = [...container.querySelectorAll(`#${sec} .card`)].map((c) => `<li><button type="button" class="toc-row" data-toc="${c.id}"><span class="tt">${TS.esc(c.querySelector(".c-title .tt")?.textContent || "")}</span>${(c.querySelector(".c-head .pill")?.outerHTML || "").replace('class="pill ', 'class="pill pill-sm ')}</button></li>`).join("");
      return rows ? `<div class="toc-g"><p class="toc-k">${label}</p><ul>${rows}</ul></div>` : "";
    }).join("");
    const sync = () => box.querySelectorAll("[data-toc]").forEach((b) => { const c = document.getElementById(b.dataset.toc);
      if (c) { b.parentElement.hidden = c.hidden; b.classList.toggle("is-muted", c.classList.contains("is-muted")); } });
    if (Cards.watch) Cards.watch.disconnect();
    (Cards.watch = new MutationObserver(sync)).observe(container, { subtree: true, attributes: true, attributeFilter: ["hidden", "class"] });
    sync();
  },
  // 도구 셈(4장 2판 2-2, tests/web/verdict_cases.json tool_head.rules): n 도구 카드(related 뺌), b 원격 전용이 아닌 MCP, a 그중 설치 ok, c 판독 결과가 있는 스킬
  counts(cards) {
    const t = cards.filter((x) => Cards.isTool(x) && !x.related), ins = (x) => Cards.step((x.verification || {}).install, 0);
    const local = t.filter((x) => x.type === "mcp" && !/^https?:/.test(x.install_cmd || "") && !/해당없음/.test(ins(x).label));
    return { n: t.length, b: local.length, a: local.filter((x) => ins(x).cls === "ok").length, c: t.filter((x) => x.type === "skill" && x.risk_signal).length };
  },
  // 도구 머리 글 '새 MCP·스킬 n개 · MCP 설치 확인 a/b'(숫자만 mono). 메일 pipeline/verification.py tool_head와 같은 규칙(사례: verdict_cases.json tool_head)
  toolHead(cards, day = "오늘") { const { n, a, b } = Cards.counts(cards), m = (x) => `<span class="mono">${x}</span>`;
    return n ? `새 MCP·스킬 ${m(n)}개${b ? ` · MCP 설치 확인 ${m(`${a}/${b}`)}` : ""}` : `${day} 새 MCP·스킬은 없어요`; },
  // 도구 줄 목록(1366 레일 맨 위 칸, 1199 이하는 칩 줄 아래로 흐른다): 머리 = toolHead, 줄 = 이름 + 판정 배지 (+ $ 명령, 1200 이상 레일만). 누르면 그 카드로(data-go, id 없음)
  toolRows(cards) {
    const list = cards.filter((c) => Cards.isTool(c) && !c.related), cmdOf = (c) => c.install_cmd && !/^https?:/.test(c.install_cmd) ? TS.esc(c.install_cmd) : "", anyCmd = list.some(cmdOf);
    const rows = list.map((c) => { const name = TS.esc(Cards.toolName(c.title).name), cmd = cmdOf(c);  // 명령 줄은 하나라도 있을 때만 모든 줄에 둬 레일 줄 높이를 맞춘다
      return `<li><button type="button" class="tool-row" data-go="card-${Cards.id(c)}"><span class="tt" title="${name}">${name}</span>${Cards.pill(Cards.badge(c)).replace('class="pill ', 'class="pill pill-sm ')}${anyCmd ? `<span class="tr-c${cmd ? "" : " none"}" aria-hidden="true">${cmd ? `$ ${cmd}` : "설치 명령 없음"}</span>` : ""}</button></li>`; });
    return `<p class="tool-h">${Cards.toolHead(cards)}</p>${rows.length ? `<ul class="tool-rows">${rows.join("")}</ul>` : ""}`; },
  // 마스트헤드: 제호(마크 40px + 날짜) → 둘째 줄(도구 머리 글 + 글자 단추 '어떻게 골랐나') → 기준 줄(메일 상태 · 기준) → 펼침(rule-2 위) → 이중 괘선. status: 둘째 줄 대신 쓸 글(만드는 중). mail: 기준 줄 앞 글(기본 메일 상태, 예시는 ""). 아직 없음이면 둘째 줄을 비운다(빈 상태 상자와 같은 말 두 번 금지)
  today(briefing, { basis = "", status = null, demo = false, mail = null, day = "오늘" } = {}) {
    const date = new Intl.DateTimeFormat("ko-KR", { month: "long", day: "numeric", weekday: "long" }).format(new Date(`${briefing.date}T00:00:00`));
    const how = briefing.exists ? `<button class="more" type="button" aria-expanded="false" aria-controls="agents">어떻게 골랐나${TS.ic("chev")}</button>` : "";
    const line = status ?? (how && `<span class="th">${Cards.toolHead(briefing.cards, day)}</span>${how}`);
    if (demo) basis = basis.replace(/\s*·\s*<a [^>]*>[^<]*<\/a>\s*$/, "");  // 예시 띠에 같은 링크가 있다
    const sent = mail ?? (!briefing.exists ? "" : briefing.sent ? "메일로 보냈어요" : "메일은 안 보냈어요"), cut = basis.lastIndexOf(" · <a ");
    const text = [sent, cut < 0 ? basis : basis.slice(0, cut)].filter(Boolean).join(" · "), link = cut < 0 ? "" : basis.slice(cut + 3);
    return `<section class="today" aria-labelledby="today-h"><div class="today-l">
      <h1 id="today-h"><svg class="mark mark-lg" aria-hidden="true" focusable="false"><use href="#i-mark"/></svg><span class="date">${date}</span><span class="sr-only"> 브리핑</span></h1>
      ${line ? `<p class="status-line">${line}</p>` : ""}${text ? `<p class="basis"><span class="b-t">${text}</span>${link ? ` ${link}` : ""}</p>` : ""}</div>${how && Cards.pipe(briefing)}<div class="rule-2" aria-hidden="true"></div></section>`;
  },
  // 어떻게 골랐나(펼침): 한글 문장(숫자만 mono, MCP·스킬 셈은 counts) → 파이프라인 mono 한 줄(수집 → 선별 → 카드)·반려·원문 재조회·되돌림 → 세 에이전트
  pipe(briefing) {
    const s = briefing.run_stats || {}, pool = briefing.pool_size ?? 0, n = briefing.count ?? briefing.cards.length, { a, b, c } = Cards.counts(briefing.cards);
    const refetched = briefing.cards.filter((x) => x.source_checked).length, m = (x) => `<span class="mono">${x}</span>`, arr = '<span class="arr" aria-hidden="true">→</span>';
    const tool = [b ? `MCP ${m(b)}개 중 ${m(a)}개는 샌드박스 설치에 성공했` : "", c ? `스킬 ${m(c)}개는 SKILL.md를 읽었` : ""].filter(Boolean).join("고, ");
    const said = `${m(pool)}건을 모아${s.selected != null ? ` ${m(s.selected)}건을 고르고` : ""} 카드 ${m(n)}장을 만들었어요.${tool ? ` ${tool}어요.` : ""}`;
    const extra = [s.rejected != null ? `반려 ${m(s.rejected)}` : "", `원문 재조회 ${m(refetched)}`, s.rollbacks ? `되돌림 ${m(s.rollbacks)}` : ""].filter(Boolean).join(" · ");
    return `<div class="agents" id="agents" hidden><p class="pipe-said">${said}</p><p class="pipe-main">수집 ${pool}${arr}${s.selected != null ? `선별 ${s.selected}${arr}` : ""}카드 ${n}</p><p class="pipe-extra">${extra}</p>${Cards.agents(briefing)}</div>`;
  },
  agents(briefing) {
    const s = briefing.run_stats || {}, refetched = briefing.cards.filter((c) => c.source_checked).length;
    return `<div><b>큐레이터 · ${briefing.pool_size ?? 0}건 → ${s.selected ?? briefing.count}건</b>내 직군과 주제 관심도로 골랐어요. 이미 받은 소식은 뺐어요.</div>
      <div><b>검증관 · 도구 ${s.verify_requested || 0}개 중 ${s.verified || 0}개 검증</b>새 MCP는 샌드박스에서 설치·실행·도구 목록을 확인하고, 스킬은 SKILL.md를 읽어 위험 신호를 봐요.${s.rollbacks ? ` 되돌림 ${s.rollbacks}건.` : ""}</div>
      <div><b>해설가 · 카드 ${briefing.count}장${s.rejected != null ? `, 반려 ${s.rejected}건` : ""}</b>한국어 요약과 ‘나에게’ 문장을 썼어요. 원문 ${refetched}건은 다시 읽었어요.</div>`;
  },
  // ===== 동작 =====
  onClick(e) {
    const t = e.target.closest("[data-action], [data-undo], [data-reason], [data-memo]");
    if (!t) return; if (t.dataset.action) Cards.feedback(t);
    else if (t.dataset.undo !== undefined) Cards.feedback(t.closest(".card").querySelector('[data-action="관심없음"]'));
    else if (t.dataset.reason) Cards.note(t, { reason: t.dataset.reason });
    else Cards.note(t, { memo: t.closest(".follow").querySelector("input").value });
  },
  // 같은 버튼을 다시 누르면 취소(서버가 status cancelled). 관심없음은 카드를 한 줄로 접고, 되돌리기는 같은 요청. 체크·글자는 aria-pressed를 보고 CSS가 바꾼다
  async feedback(button) {
    const card = button.closest(".card"), action = button.dataset.action; button.disabled = true;
    try {
      const data = await TS.api("/api/feedback", { method: "POST", body: { item_id: Number(button.dataset.item), action } });
      const on = data.status === "recorded", follow = card.querySelector(`.follow[data-follow="${action}"]`);
      button.setAttribute("aria-pressed", String(on));
      if (follow) { follow.hidden = !on; if (on) follow.dataset.fid = data.feedback_id; }
      if (action === "관심없음") { card.classList.toggle("is-muted", on); (on ? card.querySelector("[data-undo]") : button).focus(); }
      TS.say(data.message);
    } catch (e) { TS.say(e.message); } finally { button.disabled = false; }
  },
  async note(button, body) {
    const follow = button.closest(".follow"); try {
      const data = await TS.api(`/api/feedback/${follow.dataset.fid}/note`, { method: "POST", body });
      if (body.reason) follow.querySelectorAll(".rbtn").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      TS.say(data.message); } catch (e) { TS.say(e.message); }
  },
  // #card-… 주소로 들어오면 그 카드의 '자세히'를 펼친다 (메일 링크가 기댄다)
  openHash() { const id = location.hash.slice(1), el = id.startsWith("card-") ? document.getElementById(id) : null;
    if (el) { el.querySelector('.more[aria-expanded="false"]')?.click(); el.scrollIntoView({ block: "start" }); } },
};

window.Cards = Cards;  // 검사(tests/web/cdp_screens.mjs 9번)가 window.Cards.badge·Cards.toolHead로 판정·도구 머리 사례를 돌린다
window.addEventListener("hashchange", Cards.openHash);
document.addEventListener("click", (e) => {  // '오늘 한눈에' 줄(data-toc)과 도구 줄(.tool-row data-go): 그 카드로 스크롤하고 제목에 포커스
  const row = e.target.closest("[data-toc], .tool-row"), card = row && document.getElementById(row.dataset.toc || row.dataset.go);
  if (card) { card.scrollIntoView({ block: "start" }); card.querySelector(".c-title")?.focus({ preventScroll: true }); }
});
