// 브리핑 카드와 보드 (오늘·지난 브리핑·예시 공용, 2026-10-09 리디자인). 모양은 web/cards.css, 견본은 docs/design-reference.html
// 카드 해부도: 머리줄 → 제목 → 요약 → 나에게 → 검증·위험 한 줄(도구만) → 발바닥 줄(자세히·피드백)
// '자세히' 안: 장단점 → 검증 세부 → 설치 명령 → 왜 이 카드 → 트레이스 줄(API가 trace_url을 주는 관리자만)
const Cards = {
  readonly: false,  // 공개 데모(/demo): 피드백 버튼 없이 읽기만 (2026-09-16)
  REASONS: ["번역 어색", "사실 틀림", "나랑 상관없음"],
  TOOL_TYPES: ["mcp", "skill"],
  STEPS: ["설치", "실행", "도구 목록", "인증"],
  STEP_KEYS: ["install", "run", "tools_list", "auth_required"],
  MCP_SCOPE: "도구가 올바르게 동작하는지는 범위 밖이에요",
  SKILL_SCOPE: "안전 보증이 아니라 위험 신호 표시예요",
  // 검증 칸 값(pipeline/verification.py card_verification) → 모양. 키가 없어 못 띄운 것(warn)은 결함이 아니라 중립 열쇠
  CHIP: { ok: "ok", success: "ok", fail: "bad", bad: "bad", error: "bad", warn: "key", auth: "key", na: "na" },
  RISK: { ok: ["ok", "shield", "정상"], caution: ["warn", "warn", "주의"], unverified: ["warn", "warn", "확인 필요"], skipped: ["na", "na", "공식 출처, 위험 신호 생략"] },
  ACTIONS: { "써봤음": ["tried", "써봤어요"], "관심없음": ["mute", "관심없음"], "이상함": ["flag", "이상함 표시됨"] },  // [아이콘, 눌렸을 때 글자]
  opts: { day: "오늘", level: 3, abs: false, weights: null }, seq: 0,

  hd(plus = 0) { return `h${Math.min(6, Cards.opts.level + plus)}`; },
  id(card) { return card.item_id != null ? String(card.item_id) : `x${++Cards.seq}`; },

  title(card, text, id) {
    const url = TS.safeUrl(card.url), tt = `<span class="tt">${TS.esc(text)}</span>`;
    return `<${Cards.hd()} class="c-title" id="t-${id}">${url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">${tt}${TS.ic("ext")}<span class="sr-only">(새 탭)</span></a>` : tt}</${Cards.hd()}>`;
  },
  // 주제는 글자 칩 + 내 관심도 숫자(opts.weights를 넘길 때만). 주제 색 10개는 없앴다
  topic(card) {
    if (!card.topic_label) return "";
    const w = Cards.opts.weights && card.topic ? Cards.opts.weights[card.topic] : null;
    const sign = w > 0 ? `+${w}` : `${w}`;
    return `<span class="topic">${TS.esc(card.topic_label)}${w == null ? "" : ` <span class="w" aria-label="내 관심도 ${sign}">${sign}</span>`}</span>`;
  },
  rel(card) {  // 나와 관련 눈금 5칸 (card.relevance 1~5)
    const n = Number(card.relevance), ticks = [1, 2, 3, 4, 5].map((i) => `<i${i <= n ? ' class="on"' : ""}></i>`).join("");
    return n >= 1 && n <= 5 ? `<span class="rel end"><span>나와 관련</span><span class="ticks" aria-hidden="true">${ticks}</span><span class="mono">${n}/5</span></span>` : "";
  },
  // 오늘은 상대 시각, 지난 브리핑(opts.abs)은 mono 절대 시각 "10.06 14:20"
  when(iso) {
    const abs = iso ? TS.stamp(iso) : "";
    if (!abs) return "";
    if (Cards.opts.abs) return `<time class="abs" datetime="${TS.esc(iso)}">${abs}</time>`;
    const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
    return `<time datetime="${TS.esc(iso)}" title="${abs}">${hours < 1 ? "방금" : hours < 24 ? `${hours}시간 전` : `${Math.floor(hours / 24)}일 전`}</time>`;
  },
  notice(card) { return card.notice ? `<p class="notice">${TS.ic("warn")}${TS.esc(card.notice)}</p>` : ""; },
  forme(card) { return `<div class="forme"><b>나에게</b><p>${TS.esc(card.for_me)}</p></div>`; },

  // 레지스트리 이름 "com.apify/apify-mcp-server 0.15.7" → 이름·버전·네임스페이스
  toolName(title) {
    const m = String(title).match(/^(.*?)(?:\s+v?(\d+(?:\.\d+)+[\w.-]*))?$/);
    const ns = (m[1] || "").match(/^([a-z0-9-]+(?:\.[a-z0-9-]+)+)\/(.+)$/i);
    return { name: ns ? ns[2] : m[1], version: m[2] || "", namespace: ns ? ns[1] : "" };
  },
  // MCP 레지스트리 네임스페이스가 도메인 인증(com.회사 등)이면 공식, GitHub 계정 인증(io.github.*)이면 커뮤니티
  kind(card, namespace) {
    if (card.type === "skill") return ["스킬", /github\.com\/anthropics\//.test(card.url) ? "공식" : "커뮤니티"];
    return ["MCP", !namespace ? "" : namespace.startsWith("io.github.") ? "커뮤니티" : "공식"];
  },
  DIST: [[/^https?:\/\//, "원격 전용"], [/^(npx|npm|pnpm|bunx)\b/, "npm"], [/^(uvx|pip|pipx|uv)\b/, "PyPI"], [/^docker\b/, "Docker"]],
  distribution(cmd) { return (Cards.DIST.find(([re]) => re.test(cmd || "")) || [null, ""])[1]; },

  // 검증 한 칸: 겉면은 짧은 말(성공·실패·키 필요·미확인·N개), 자세히에는 서버 문구 그대로
  step(value, n) {
    const state = value && typeof value === "object" ? value.status : value;
    const label = (value && typeof value === "object" && value.label) || Cards.STEPS[n];
    const cls = Cards.CHIP[state] || "na", count = /도구 (\d+)개/.exec(label);
    const short = cls === "key" ? "키 필요" : cls === "bad" ? "실패" : cls === "na" ? (/해당없음/.test(label) ? "해당없음" : "미확인")
      : n === 2 && count ? `${count[1]}개` : n === 3 ? "필요 없음" : "성공";
    return { k: Cards.STEPS[n], cls, short, label };
  },
  verify(card) {
    if (card.type === "skill") return Cards.risk(card);
    const v = card.verification;
    if (!v) return `<p class="scope">${TS.ic("clock")}<span>${TS.esc(card.verification_note || "검증 예정")}</span><span>· ${Cards.MCP_SCOPE}</span></p>`;
    const cells = Cards.STEP_KEYS.map((key, n) => Cards.step(v[key], n));
    const said = `검증: ${cells.map((c) => `${c.k} ${c.short}`).join(", ")}`;
    return `<div class="verify" role="group" aria-label="${TS.esc(said)}">${cells.map((c) =>
      `<div class="vc ${c.cls}"><span class="k">${c.k}</span><span class="v">${TS.ic(c.cls)}${TS.esc(c.short)}</span></div>`).join("")}</div>
      <p class="scope"><span>샌드박스 확인 <span class="mono">${TS.esc(String(v.probed_at || "").replace(/\s*샌드박스$/, ""))}</span></span><span>· ${Cards.MCP_SCOPE}</span></p>`;
  },
  // 스킬 판독: 위험 신호 알약 + 걸린 항목. 예시 데이터처럼 값만 있으면 그 값을 단계로 본다
  risk(card) {
    const r = typeof card.risk_signal === "string" ? { level: card.risk_signal } : card.risk_signal;
    const note = card.verification_note ? `<span>· ${TS.esc(card.verification_note)}</span>` : "";
    if (!r) return `<p class="scope">${TS.ic("clock")}<span>${TS.esc(card.verification_note || "판독 예정")}</span><span>· ${Cards.SKILL_SCOPE}</span></p>`;
    const [tone, icon, word] = Cards.RISK[r.level] || ["na", "na", r.level || ""];
    const label = r.label || word, hits = (r.hits || []).filter(Boolean);
    return `<div class="risk"><span class="pill pill-${tone}">${TS.ic(icon)}${TS.esc(r.level === "skipped" ? label : `위험 신호 · ${label}`)}</span>
      ${hits.length ? `<span class="hits" aria-label="걸린 항목">${hits.map((h) => `<span>${TS.esc(h)}</span>`).join("")}</span>` : ""}
      <p class="scope"><span>${Cards.SKILL_SCOPE}</span>${r.reviewed_at ? `<span>· 검토 <span class="mono">${TS.esc(r.reviewed_at)}</span></span>` : ""}${note}</p></div>`;
  },

  // ===== 자세히 =====
  points(title, sign, list) {
    if (!list || !list.length) return "";
    return `<div><${Cards.hd(1)} class="d-h">${title}</${Cards.hd(1)}><ul>${list.map((p) => {
      const url = TS.safeUrl(p.evidence_url);
      return `<li><span class="g" aria-hidden="true">${sign}</span><span>${TS.esc(p.text)}${url ? ` <a class="ev" href="${TS.esc(url)}" target="_blank" rel="noopener">근거${TS.ic("ext", "ic-12")}</a>` : ""}</span></li>`;
    }).join("")}</ul></div>`;
  },
  pc(card) {
    const both = Cards.points("좋은 점", "+", card.pros) + Cards.points("아쉬운 점", "−", card.cons);
    return both ? `<div class="pc">${both}</div>` : "";
  },
  verifyRows(card) {
    const v = card.verification, hd = Cards.hd(1);
    if (card.type === "skill") {
      const r = card.risk_signal && typeof card.risk_signal === "object" ? card.risk_signal : null;
      if (!r || !(r.quote || r.basis)) return "";
      return `<div><${hd} class="d-h">걸린 근거</${hd}>${r.quote ? `<div class="cmd"><pre class="wrap-text" tabindex="0">${TS.esc(r.quote)}</pre></div>` : ""}
        <p class="scope">${[r.basis, r.completeness ? `충실도 ${r.completeness}` : ""].filter(Boolean).map(TS.esc).join(" · ")}</p></div>`;
    }
    if (!v) return "";
    const rows = Cards.STEP_KEYS.map((key, n) => Cards.step(v[key], n))
      .map((c) => `<div class="vrow ${c.cls}">${TS.ic(c.cls)}<b>${c.k}</b><span class="val">${TS.esc(c.label)}</span></div>`).join("");
    return `<div><${hd} class="d-h">샌드박스 검증</${hd}><div class="vrows">${rows}</div></div>`;
  },
  cmd(card) {
    const c = card.install_cmd, hd = Cards.hd(1);
    if (!c) return "";
    const remote = /^https?:/.test(c);
    return `<div><${hd} class="d-h">${remote ? "원격 주소" : "설치 명령"}</${hd}><div class="cmd"><pre tabindex="0" role="region" aria-label="설치 명령">${remote ? "" : '<span class="p" aria-hidden="true">$ </span>'}${TS.esc(c)}</pre>
      <button type="button" data-copy="${TS.esc(c)}" aria-label="설치 명령 복사">${TS.ic("copy")}<span class="lab">복사</span></button></div></div>`;
  },
  why(card) {
    const n = Number(card.relevance), hd = Cards.hd(1);
    return `<div class="why"><${hd} class="d-h">왜 이 카드?</${hd}><p>${TS.esc(card.why_this_card || "")}</p>${n >= 1 ? `<p class="nums">나와 관련 <span class="mono">${n}/5</span></p>` : ""}</div>`;
  },
  // 관리자만: API가 Langfuse 주소를 주면 링크, 주소 설정이 없으면 "trace_id ..." 글자 + 복사
  trace(card) {
    const t = card.trace_url;
    if (!t) return "";
    const tag = `<span class="tag-mode tag-admin">${TS.ic("lock")}관리자</span>`;
    if (TS.safeUrl(t)) return `<div class="trace">${tag}<a href="${TS.esc(t)}" target="_blank" rel="noopener">Langfuse 트레이스 열기${TS.ic("ext")}<span class="sr-only">(새 탭)</span></a></div>`;
    return `<div class="trace">${tag}<span>트레이스 주소가 설정되지 않아 id만 보여요</span><div class="cmd"><pre tabindex="0" aria-label="trace id">${TS.esc(t)}</pre>
      <button type="button" data-copy="${TS.esc(t)}" aria-label="trace id 복사">${TS.ic("copy")}<span class="lab">복사</span></button></div></div>`;
  },

  // ===== 피드백: 눌림은 aria-pressed + 체크 + 글자 변화. 이상함은 사유 3택, 써봤음은 소감 한 줄(둘 다 선택) =====
  fb(card, actions) {
    if (Cards.readonly) return "";
    const on = new Set((card.feedback || {}).actions || []);
    return `<div class="fb${actions.length === 3 ? " n3" : ""}" style="--n:${actions.length}">${actions.map((a) => {
      const pressed = on.has(a) && a !== "관심없음", [icon, onText] = Cards.ACTIONS[a];
      return `<button type="button" data-action="${a}" data-item="${TS.esc(card.item_id)}" aria-pressed="${on.has(a)}">${TS.ic(pressed ? "tried" : icon)}<span class="lab">${pressed ? onText : a}</span></button>`;
    }).join("")}</div>`;
  },
  follow(card, id) {
    if (Cards.readonly) return "";
    const f = card.feedback || {}, on = new Set(f.actions || []), ids = f.ids || {};
    const odd = `<div class="follow" data-follow="이상함" data-fid="${TS.esc(ids["이상함"] || "")}"${on.has("이상함") ? "" : " hidden"}><fieldset class="rbtns">
      <legend class="q">무엇이 이상했나요? 고르지 않아도 돼요</legend>${Cards.REASONS.map((r) => `<button type="button" class="rbtn" data-reason="${r}" aria-pressed="${f.reason === r}">${r}</button>`).join("")}</fieldset></div>`;
    if (!Cards.TOOL_TYPES.includes(card.type)) return odd;
    return `${odd}<div class="follow" data-follow="써봤음" data-fid="${TS.esc(ids["써봤음"] || "")}"${on.has("써봤음") ? "" : " hidden"}><label class="q" for="memo-${id}">써 본 소감 한 줄 (선택)</label>
      <div class="row"><input class="input" id="memo-${id}" type="text" maxlength="200" value="${TS.esc(f.memo || "")}"><button type="button" class="btn btn-sm" data-memo>저장</button></div></div>`;
  },

  // 카드 한 장. surface = 머리줄~검증 한 줄, actions = 피드백 버튼, detail = 자세히 앞부분
  wrap(card, id, cls, surface, actions, detail, text) {
    const muted = !Cards.readonly && ((card.feedback || {}).actions || []).includes("관심없음");
    const hint = Cards.readonly && !Cards.hinted ? `<p class="hint-line">${TS.ic("info")}로그인하면 관심없음·써봤음·이상함으로 다음 날 추천을 바꿀 수 있어요.</p>` : "";
    Cards.hinted = Cards.hinted || Cards.readonly;
    return `<article class="card${cls}${muted ? " is-muted" : ""}" id="card-${id}" data-item="${TS.esc(card.item_id ?? "")}" data-topic="${TS.esc(card.topic || "")}" aria-labelledby="t-${id}">
      ${surface}<div class="c-foot"><button class="more" type="button" aria-expanded="false" aria-controls="d-${id}">자세히${TS.ic("chev")}</button>${Cards.fb(card, actions)}${hint}</div>
      ${Cards.follow(card, id)}<div class="detail" id="d-${id}" hidden>${detail}${Cards.why(card)}${Cards.trace(card)}</div>
      ${Cards.readonly ? "" : `<div class="muted-line"><span class="lab">관심없음으로 표시함</span><span class="t">${TS.esc(text)}</span><button type="button" class="btn btn-sm" data-undo>되돌리기</button></div>`}
    </article>`;
  },
  // 뉴스 카드. hl이면 업계 큰 소식(관심도와 상관없이 맨 위라 관심없음 버튼 없음)
  news(card, hl = false) {
    const id = Cards.id(card), host = TS.host(card.url), meta = card.item_meta || {};
    const head = Cards.topic(card) + (host ? `<span class="host">${TS.esc(host)}</span>` : "") + Cards.when(meta.published_at) + (hl ? "" : Cards.rel(card));
    const surface = `<div class="c-head">${head}</div>${Cards.title(card, card.title, id)}${Cards.notice(card)}<p class="c-sum">${TS.esc(card.summary_ko)}</p>${Cards.forme(card)}`;
    return Cards.wrap(card, id, hl ? " hl" : "", surface, hl ? ["이상함"] : ["관심없음", "이상함"], Cards.pc(card), card.title);
  },
  tool(card) {
    const id = Cards.id(card), meta = card.item_meta || {};
    const { name, version, namespace } = Cards.toolName(card.title);
    const [kindName, kindSrc] = Cards.kind(card, namespace), ver = version || meta.version || "", dist = Cards.distribution(card.install_cmd);
    const kind = `<span class="kind">${/^[A-Z]+$/.test(kindName) ? `<span class="mono">${kindName}</span>` : kindName}${kindSrc ? ` · ${kindSrc}` : ""}</span>`;
    const stars = meta.stars != null ? Number(meta.stars).toLocaleString("ko-KR") : "";
    const ago = meta.published_at ? TS.daysAgo(meta.published_at) : "";
    const metaParts = [stars ? `<span class="star">${TS.ic("star", "ic-12")}<span aria-label="GitHub 별 ${stars}개">${stars}</span></span>` : "",
      ago ? `<span>${ago === "오늘" ? "오늘 등록" : `등록 ${ago}`}</span>` : "", dist ? `<span>${dist}</span>` : "", Cards.topic(card)].filter(Boolean);
    const surface = `<div class="c-head">${kind}${Cards.rel(card)}</div>
      <div class="t-name">${Cards.title(card, name, id)}${ver ? `<span class="ver">v${TS.esc(ver.replace(/^v/, ""))}</span>` : ""}</div>
      ${metaParts.length ? `<p class="meta">${metaParts.join('<span aria-hidden="true">·</span>')}</p>` : ""}${Cards.notice(card)}
      <p class="c-sum">${TS.esc(card.summary_ko)}</p>${Cards.forme(card)}${Cards.verify(card)}`;
    return Cards.wrap(card, id, "", surface, ["써봤음", "관심없음", "이상함"], Cards.pc(card) + Cards.verifyRows(card) + Cards.cmd(card), name);
  },
  card(card) {
    return Cards.TOOL_TYPES.includes(card.type) ? Cards.tool(card) : Cards.news(card, Boolean(card.headline));
  },

  // ===== 보드: 큰 소식 띠 → 뉴스 레인 | 도구 레인(월요일 관련 카드는 도구 레인 아래). 0건이면 .empty =====
  // opts: day("오늘"·"이날"), level(카드 제목 h 단계, 기본 3), abs(절대 시각), weights(주제 관심도), one(한 열), empty(빈 상태 HTML)
  mount(container, briefing, opts = {}) {
    if (typeof opts === "string") opts = { day: opts };  // 예전 부르기: Cards.mount(el, briefing, "이날")
    const o = Cards.opts = { day: "오늘", level: 3, abs: false, weights: null, one: false, ...opts };
    const h = `h${o.level - 1}`, isTool = (c) => Cards.TOOL_TYPES.includes(c.type);
    Cards.hinted = false;
    if (!briefing.cards.length) {
      container.innerHTML = o.empty || (briefing.exists
        ? `<section class="empty"><${h}>${o.day} 볼 만한 게 없었어요</${h}><p>${TS.esc(briefing.empty_reason || "")}</p></section>`
        : `<section class="empty"><${h}>아직 ${o.day} 브리핑이 없어요</${h}><p>매일 아침 08:00에 메일로도 보내요. 설정의 지금 만들기로 바로 만들 수도 있어요.</p></section>`);
      return;
    }
    const hl = briefing.cards.filter((c) => c.headline && !isTool(c) && !c.related);
    const news = briefing.cards.filter((c) => !c.headline && !isTool(c) && !c.related);
    const tools = briefing.cards.filter((c) => isTool(c) && !c.related);
    const related = briefing.cards.filter((c) => c.related);
    const head = (id, title, n, hint) => `<div class="lane-h${id ? "" : " sub"}"><${h}${id ? ` id="${id}-h"` : ""}>${title}</${h}><span class="n">${n}</span>${hint ? `<span class="hint">${hint}</span>` : ""}</div>`;
    const band = hl.length ? `<section class="hl-band" id="hl" aria-labelledby="hl-h"><div class="band-h"><span class="dblaze" aria-hidden="true"><i></i><i></i></span>
      <${h} id="hl-h">업계 큰 소식</${h}><span class="hint">내 관심도와 상관없이 맨 위에 둬요</span></div><div class="hl-grid${hl.length === 1 || o.one ? " one" : ""}">${hl.map(Cards.card).join("")}</div></section>` : "";
    const newsLane = `<section class="lane" id="news" aria-labelledby="news-h">${head("news", "뉴스", news.length, "")}${news.map(Cards.card).join("") || `<p class="help">${o.day} 뉴스 카드는 없어요</p>`}</section>`;
    const toolLane = tools.length || related.length ? `<section class="lane" id="tools" aria-labelledby="tools-h">${head("tools", "새 MCP·스킬", tools.length, "7일 안에 등록된 것 중 아직 안 본 것")}
      ${tools.map(Cards.card).join("") || `<p class="help">${o.day} 새 도구는 없어요</p>`}${related.length ? head("", "이번 주 관련 MCP·스킬", related.length, "날짜와 상관없이 내 도구와 겹치는 것") + related.map(Cards.card).join("") : ""}</section>` : "";
    container.innerHTML = `<div class="brief">${band}<div class="board${o.one ? " one" : ""}${toolLane ? "" : " no-tools"}">${newsLane}${toolLane}</div></div>`;
    if (!container.dataset.cards) {
      container.dataset.cards = "1";
      container.addEventListener("click", Cards.onClick);
    }
    Cards.openHash();
  },

  // 오늘 머리줄: mono 날짜 h1 + 상태줄 + 기준 줄 + 오른쪽 파이프라인, 아래 '어떻게 골랐나' 펼침. demo면 '예시' 칩
  today(briefing, { basis = "", status = null, demo = false } = {}) {
    const d = new Date(`${briefing.date}T00:00:00`), two = (n) => String(n).padStart(2, "0");
    const dow = new Intl.DateTimeFormat("ko-KR", { weekday: "long" }).format(d), has = briefing.cards.length > 0;
    const line = status ?? (!has && !briefing.exists ? `${TS.ic("clock")}<span>아직 오늘 브리핑이 없어요 · 매일 아침 <span class="mono">08:00</span>에 보내요</span>`
      : briefing.sent ? `${TS.ic("mail")}<span>메일로도 보냈어요</span>` : `${TS.ic("clock")}<span>매일 아침 <span class="mono">08:00</span>에 메일로도 보내요</span>`);
    return `<section class="today" aria-labelledby="today-h"><div class="today-l">
      <h1 id="today-h"><span class="date">${two(d.getMonth() + 1)}.${two(d.getDate())}</span><span class="dow">${dow}</span>${demo ? '<span class="tag-mode">예시</span>' : ""}<span class="sr-only">브리핑</span></h1>
      ${line ? `<p class="status-line">${line}</p>` : ""}${basis ? `<p class="basis">${basis}</p>` : ""}</div>${has ? Cards.pipe(briefing) : ""}</section>${has ? Cards.agents(briefing) : ""}`;
  },
  // 파이프라인 mono 한 줄(수집 → 선별 → 카드) + 검증 미터(분모가 작은 '검증 N/M'에만). run_stats가 없는 예전 브리핑은 수집 → 카드
  pipe(briefing) {
    const s = briefing.run_stats || {}, pool = briefing.pool_size ?? 0, req = s.verify_requested || 0, done = s.verified || 0;
    const refetched = briefing.cards.filter((c) => c.source_checked).length, arr = '<span class="arr">→</span>';
    const main = `수집 ${pool}${arr}${s.selected != null ? `선별 ${s.selected}${arr}` : ""}카드 ${briefing.count}`;
    const meter = req ? `<span>검증 <span class="mono">${done}/${req}</span></span><span class="meter" aria-hidden="true"><i style="width:${Math.round((done / req) * 100)}%"></i></span>` : "";
    const extra = [s.rejected != null ? `반려 <span class="mono">${s.rejected}</span>` : "", `원문 재조회 <span class="mono">${refetched}</span>`,
      s.rollbacks ? `되돌림 <span class="mono">${s.rollbacks}</span>` : ""].filter(Boolean).join(" · ");
    const said = `${pool}건을 모아${s.selected != null ? ` ${s.selected}건을 고르고` : ""} 카드 ${briefing.count}장을 만들었어요.${req ? ` 도구 ${req}개 중 ${done}개를 검증했어요.` : ""}`;
    return `<div class="pipe"><p class="pipe-main" aria-hidden="true">${main}</p><p class="sr-only">${said}</p>
      <p class="pipe-sub">${meter}<span class="pipe-extra">${meter ? "· " : ""}${extra}</span><button class="more" type="button" aria-expanded="false" aria-controls="agents">어떻게 골랐나${TS.ic("chev")}</button></p></div>`;
  },
  agents(briefing) {
    const s = briefing.run_stats || {}, refetched = briefing.cards.filter((c) => c.source_checked).length;
    return `<div class="agents" id="agents" hidden>
      <div><b>큐레이터 · ${briefing.pool_size ?? 0}건 → ${s.selected ?? briefing.count}건</b>내 직군과 주제 관심도로 골랐어요. 이미 받은 소식은 뺐어요.</div>
      <div><b>검증관 · 도구 ${s.verify_requested || 0}개 중 ${s.verified || 0}개 검증</b>새 MCP는 샌드박스에서 설치·실행·도구 목록을 확인하고, 스킬은 SKILL.md를 읽어 위험 신호를 봐요.${s.rollbacks ? ` 되돌림 ${s.rollbacks}건.` : ""}</div>
      <div><b>해설가 · 카드 ${briefing.count}장${s.rejected != null ? `, 반려 ${s.rejected}건` : ""}</b>한국어 요약과 ‘나에게’ 문장을 썼어요. 원문 ${refetched}건은 다시 읽었어요.</div></div>`;
  },

  // ===== 동작 =====
  onClick(e) {
    const t = e.target.closest("[data-action], [data-undo], [data-reason], [data-memo]");
    if (!t) return;
    if (t.dataset.action) Cards.feedback(t);
    else if (t.dataset.undo !== undefined) Cards.feedback(t.closest(".card").querySelector('[data-action="관심없음"]'));
    else if (t.dataset.reason) Cards.note(t, { reason: t.dataset.reason });
    else Cards.note(t, { memo: t.closest(".follow").querySelector("input").value });
  },
  // 같은 버튼을 다시 누르면 취소(서버가 status cancelled). 관심없음은 카드를 한 줄로 접고, 되돌리기는 같은 요청
  async feedback(button) {
    const card = button.closest(".card"), action = button.dataset.action;
    button.disabled = true;
    try {
      const data = await TS.api("/api/feedback", { method: "POST", body: { item_id: Number(button.dataset.item), action } });
      const on = data.status === "recorded", [icon, onText] = Cards.ACTIONS[action], mark = on && action !== "관심없음";
      button.setAttribute("aria-pressed", String(on));
      button.innerHTML = `${TS.ic(mark ? "tried" : icon)}<span class="lab">${mark ? onText : action}</span>`;
      const follow = card.querySelector(`.follow[data-follow="${action}"]`);
      if (follow) { follow.hidden = !on; if (on) follow.dataset.fid = data.feedback_id; }
      if (action === "관심없음") {
        card.classList.toggle("is-muted", on);
        (on ? card.querySelector("[data-undo]") : button).focus();
      }
      TS.say(data.message);
    } catch (e) {
      TS.say(e.message);
    } finally { button.disabled = false; }
  },
  async note(button, body) {
    const follow = button.closest(".follow");
    try {
      const data = await TS.api(`/api/feedback/${follow.dataset.fid}/note`, { method: "POST", body });
      if (body.reason) follow.querySelectorAll(".rbtn").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      TS.say(data.message);
    } catch (e) { TS.say(e.message); }
  },
  // #card-… 주소로 들어오면 그 카드의 '자세히'를 펼친다
  openHash() {
    const id = location.hash.slice(1), el = id.startsWith("card-") ? document.getElementById(id) : null;
    if (el) { el.querySelector('.more[aria-expanded="false"]')?.click(); el.scrollIntoView({ block: "start" }); }
  },
};

window.addEventListener("hashchange", Cards.openHash);
