// 브리핑 카드와 피드백 버튼 (오늘 브리핑·지난 브리핑 공용). 마크업은 docs/design-reference.html의 .item·.tool 구조.
const Cards = {
  readonly: false,  // 공개 데모(/demo)는 피드백 버튼 없이 읽기만 (2026-09-16)
  REASONS: ["번역 어색", "사실 틀림", "나랑 상관없음"],
  TOOL_TYPES: ["mcp", "skill"],
  STEPS: ["설치", "실행", "도구 목록", "인증"],
  MCP_SCOPE: "도구가 올바르게 동작하는지는 범위 밖입니다.",
  SKILL_SCOPE: "안전 보증이 아니라 위험 신호 표시입니다.",
  RISK_CHIP: { ok: "ok", caution: "warn", unverified: "warn", skipped: "na" },

  why(card) {
    const trace = card.trace_url && TS.safeUrl(card.trace_url)
      ? ` <a href="${TS.esc(card.trace_url)}" target="_blank" rel="noopener">어떻게 만들어졌나</a>` : "";
    return `<details class="why"><summary>왜 이 카드?</summary><p>${TS.esc(card.why_this_card)}${trace}</p></details>`;
  },

  forme(card) {
    return `<div class="forme"><b>나한테는</b><p>${TS.esc(card.for_me)}</p></div>`;
  },

  acts(card, actions) {
    if (Cards.readonly) return "";
    const on = new Set(card.feedback.actions || []);
    return `<div class="acts">${actions.map((a) =>
      `<button class="act${a === "써봤음" ? " p" : ""}" type="button" aria-pressed="${on.has(a)}" data-action="${a}" data-item="${card.item_id}">${a}</button>`).join("")}<span class="fb"></span></div>`;
  },

  item(card) {
    const muted = (card.feedback.actions || []).includes("관심없음") ? " muted" : "";
    const url = TS.safeUrl(card.url);
    const title = url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">${TS.esc(card.title)}</a>` : TS.esc(card.title);
    const src = [TS.host(card.url), card.notice].filter(Boolean).map(TS.esc).join(" · ");
    return `<article class="item${muted}" data-topic="${TS.esc(card.topic || "")}" data-item="${card.item_id}">
      <div class="mark"><i></i></div>
      <div>
        <div class="topic">${TS.esc(card.topic_label || "주제 미정")}</div>
        <h3>${title}</h3>
        <div class="src">${src}</div>
        <p class="sum">${TS.esc(card.summary_ko)}</p>
        ${Cards.forme(card)}${Cards.why(card)}${Cards.acts(card, ["관심없음", "이상함"])}
      </div>
    </article>`;
  },

  // 레지스트리 이름 "com.apify/apify-mcp-server 0.15.7" → 이름·버전·네임스페이스
  toolName(title) {
    const m = String(title).match(/^(.*?)(?:\s+v?(\d+(?:\.\d+)+[\w.-]*))?$/);
    const ns = (m[1] || "").match(/^([a-z0-9-]+(?:\.[a-z0-9-]+)+)\/(.+)$/i);
    return { name: ns ? ns[2] : m[1], version: m[2] || "", namespace: ns ? ns[1] : "" };
  },

  // MCP 레지스트리 네임스페이스가 도메인 인증(com.회사 등)이면 공식, GitHub 계정 인증(io.github.*)이면 커뮤니티
  kind(card, namespace) {
    if (card.type === "skill") return /github\.com\/anthropics\//.test(card.url) ? "스킬 · 공식" : "스킬 · 커뮤니티";
    if (!namespace) return "MCP";
    return namespace.startsWith("io.github.") ? "MCP · 커뮤니티" : "MCP · 공식";
  },

  distribution(cmd) {
    if (!cmd) return "";
    if (/^https?:\/\//.test(cmd)) return "원격 전용";
    if (/^(npx|npm|pnpm|bunx)\b/.test(cmd)) return "npm";
    if (/^(uvx|pip|pipx|uv)\b/.test(cmd)) return "PyPI";
    if (/^docker\b/.test(cmd)) return "Docker";
    return "";
  },

  points(title, cls, list) {
    if (!list || !list.length) return "";
    const rows = list.map((p) => {
      const url = TS.safeUrl(p.evidence_url);
      return `<li>${TS.esc(p.text)}${url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">근거</a>` : ""}</li>`;
    }).join("");
    return `<div class="${cls}"><h4>${title}</h4><ul>${rows}</ul></div>`;
  },

  // 검증 4단계 칩. 검증관 결과가 없으면 전부 na, 제목 옆에 "검증 예정"(또는 설치법 미확인 같은 메모). 범위 문구는 늘 고정
  verify(card) {
    if (card.type === "skill") return Cards.risk(card);
    const v = card.verification;
    if (!v) {
      return `<div class="verify"><div class="t">직접 깔아봤더니 <small>${TS.esc(card.verification_note || "검증 예정")}</small></div>
        <div class="steps">${Cards.STEPS.map((s) => `<span class="step na"><i></i>${s}</span>`).join("")}</div>
        <div class="note">검증관이 샌드박스에서 설치·실행·도구 목록·인증 요구를 확인해 여기에 표시합니다. ${Cards.MCP_SCOPE}</div></div>`;
    }
    const cls = { ok: "ok", success: "ok", auth: "warn", warn: "warn", fail: "bad", error: "bad", na: "na" };
    const steps = ["install", "run", "tools_list", "auth_required"].map((key, n) => {
      const value = v[key] || {};
      const state = typeof value === "object" ? value.status : value;
      const label = (typeof value === "object" && value.label) || Cards.STEPS[n];
      return `<span class="step ${cls[state] || "na"}"><i></i>${TS.esc(label)}</span>`;
    }).join("");
    return `<div class="verify"><div class="t">직접 깔아봤더니 <small>${TS.esc(v.probed_at || "")}</small></div>
      <div class="steps">${steps}</div><div class="note">설치·기동·도구 노출까지 확인한 결과입니다. ${Cards.MCP_SCOPE}</div></div>`;
  },

  // 스킬 판독: 위험 신호 칩(정상·주의·확인 필요·공식 출처 생략) + 인용 + 충실도. 안전 보증 아님 문구는 늘 고정
  risk(card) {
    const r = card.risk_signal;
    if (!r) {
      return `<div class="verify"><div class="t">SKILL.md 읽어봤더니 <small>${TS.esc(card.verification_note || "판독 예정")}</small></div>
        <div class="steps"><span class="step na"><i></i>위험 신호 판독 예정</span></div><div class="note">${Cards.SKILL_SCOPE}</div></div>`;
    }
    const chips = [`<span class="step ${Cards.RISK_CHIP[r.level] || "na"}"><i></i>위험 신호 ${TS.esc(r.label)}</span>`]
      .concat(r.completeness ? [`<span class="step na"><i></i>충실도 ${TS.esc(r.completeness)}</span>`] : [])
      .concat((r.hits || []).map((h) => `<span class="step na"><i></i>${TS.esc(h)}</span>`)).join("");
    const quote = (r.basis ? `${TS.esc(r.basis)}. ` : "") + (r.quote ? `인용: ${TS.esc(r.quote)}. ` : "");
    return `<div class="verify"><div class="t">SKILL.md 읽어봤더니 <small>${TS.esc(r.reviewed_at || "")}</small></div>
      <div class="steps">${chips}</div><div class="note">${quote}${Cards.SKILL_SCOPE}</div></div>`;
  },

  tool(card) {
    const muted = (card.feedback.actions || []).includes("관심없음") ? " muted" : "";
    const meta = card.item_meta || {};
    const { name, version, namespace } = Cards.toolName(card.title);
    const url = TS.safeUrl(card.url);
    const metaParts = [
      meta.stars != null ? `GitHub ★ ${Number(meta.stars).toLocaleString("ko-KR")}` : "",
      meta.published_at ? `공개 ${TS.daysAgo(meta.published_at)}` : "",
      Cards.distribution(card.install_cmd),
      card.notice || "",
    ].filter(Boolean);
    const pc = Cards.points("좋은 점", "pros", card.pros) + Cards.points("아쉬운 점", "cons", card.cons);
    const cmd = card.install_cmd
      ? `<div class="cmd"><span class="ps">${/^https?:/.test(card.install_cmd) ? "url" : "$"}</span><code>${TS.esc(card.install_cmd)}</code><button type="button" data-copy="${TS.esc(card.install_cmd)}">복사</button></div>` : "";
    return `<article class="tool${muted}" data-kind="${TS.esc(card.type)}" data-item="${card.item_id}">
      <span class="kind">${Cards.kind(card, namespace)}</span>
      <h3>${url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">${TS.esc(name)}</a>` : TS.esc(name)}${version ? ` <span class="ver">${TS.esc(version)}</span>` : ""}</h3>
      ${metaParts.length ? `<div class="meta">${metaParts.map((m) => `<span>${TS.esc(m)}</span>`).join("")}</div>` : ""}
      <p class="desc">${TS.esc(card.summary_ko)}</p>
      ${Cards.forme(card)}${pc ? `<div class="pc">${pc}</div>` : ""}${Cards.verify(card)}${cmd}${Cards.why(card)}
      ${Cards.acts(card, ["써봤음", "관심없음", "이상함"])}
    </article>`;
  },

  section(title, count, hint, body) {
    return `<section class="sec"><div class="sec-h"><h2>${title}</h2>${count != null ? `<span class="n">${count}</span>` : ""}${hint ? `<span class="hint">${hint}</span>` : ""}</div>${body}</section>`;
  },

  // 파이프라인 3칸 (오늘 브리핑 마스트헤드). run_stats가 없는 예전 브리핑은 수집 → 최종만, 검증관은 아직 없어 0 / 0
  pipe(briefing) {
    const stats = briefing.run_stats || {};
    const hasStats = stats.selected != null;
    const refetched = briefing.cards.filter((c) => c.source_checked).length;
    const curator = hasStats
      ? `${briefing.pool_size ?? 0} <span>→</span> ${stats.selected} <span>→</span> ${briefing.count}`
      : `${briefing.pool_size ?? 0} <span>→</span> ${briefing.count}`;
    const explained = stats.rejected != null ? `반려 ${stats.rejected} · 원문 재조회 ${refetched}` : `원문 재조회 ${refetched}`;
    return `<div class="pipe" aria-label="오늘 새벽 에이전트 작업">
      <div><div class="who"><i></i>큐레이터</div><div class="what">${curator}</div><div class="sub">${hasStats ? "수집 · 선별 · 내 기준 정렬" : "수집 · 내 기준 정렬"}</div></div>
      <div><div class="who"><i></i>검증관</div><div class="what">${stats.verified ?? 0} <span>/ ${stats.verify_requested ?? 0} 검증</span></div><div class="sub">${stats.rollbacks ? `샌드박스 설치 · 도구 목록 · 되돌림 ${stats.rollbacks}` : "샌드박스 설치 · 도구 목록"}</div></div>
      <div><div class="who"><i></i>해설가</div><div class="what">${briefing.count} <span>장 작성</span></div><div class="sub">${explained}</div></div>
    </div>`;
  },

  // 브리핑 본문 섹션들 (뉴스·새 도구·월요일 관련 카드). 0건이면 .empty에 empty_reason
  mount(container, briefing, day = "오늘") {
    if (!briefing.cards.length) {
      const body = briefing.exists
        ? `<div class="empty">${day} 볼 만한 게 없었어요.<p>${TS.esc(briefing.empty_reason || "")}</p></div>`
        : `<div class="empty">아직 브리핑이 없어요.<p>설정에서 「지금 만들기」를 누르거나 내일 아침을 기다려 주세요.</p></div>`;
      container.innerHTML = Cards.section("뉴스", 0, "", body);
      return;
    }
    const news = briefing.cards.filter((c) => !Cards.TOOL_TYPES.includes(c.type));
    const tools = briefing.cards.filter((c) => Cards.TOOL_TYPES.includes(c.type) && !c.related);
    const related = briefing.cards.filter((c) => c.related);
    container.innerHTML =
      Cards.section("뉴스", news.length, "주제 색은 내 관심도 순", news.map(Cards.item).join("") || `<div class="empty">${day} 뉴스 카드 없음</div>`)
      + Cards.section("새 MCP·스킬", tools.length, "7일 안에 등록된 것 중 아직 안 본 것", tools.map(Cards.tool).join("") || `<div class="empty">${day} 새 도구 없음</div>`)
      + (related.length ? Cards.section("이번 주 관련 MCP·스킬", related.length, "날짜와 상관없이 내 도구와 겹치는 것", related.map(Cards.tool).join("")) : "");
    container.querySelectorAll("[data-copy]").forEach((b) => {
      b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "복사됨"; };
    });
    if (!Cards.readonly) container.querySelectorAll("button[data-action]").forEach((b) => { b.onclick = () => Cards.feedback(b); });
  },

  // 버튼: aria-pressed 토글, 관심없음은 카드 muted, 서버 응답 문구를 .fb에. 같은 버튼을 다시 누르면 취소
  async feedback(button) {
    const card = button.closest(".item, .tool");
    const acts = button.closest(".acts");
    const fb = acts.querySelector(".fb");
    card.querySelectorAll(".acts.extra").forEach((row) => row.remove());
    try {
      const data = await TS.api("/api/feedback", { method: "POST", body: { item_id: Number(button.dataset.item), action: button.dataset.action } });
      const on = data.status === "recorded";
      button.setAttribute("aria-pressed", String(on));
      if (button.dataset.action === "관심없음") card.classList.toggle("muted", on);
      TS.message(fb, data.message);
      if (!on) return;
      if (button.dataset.action === "이상함") {
        acts.insertAdjacentHTML("afterend", `<div class="acts extra">${Cards.REASONS.map((r) => `<button class="act" type="button" data-reason="${r}">${r}</button>`).join("")}<span class="fb"></span></div>`);
        const row = acts.nextElementSibling;
        row.querySelectorAll("button").forEach((r) => { r.onclick = () => Cards.note(data.feedback_id, { reason: r.dataset.reason }, row); });
      }
      if (button.dataset.action === "써봤음") {
        acts.insertAdjacentHTML("afterend", `<div class="acts extra"><input type="text" maxlength="200" placeholder="써 본 소감 한 줄 (선택)" aria-label="써 본 소감"><button class="act" type="button">메모 저장</button><span class="fb"></span></div>`);
        const row = acts.nextElementSibling;
        row.querySelector("button").onclick = () => Cards.note(data.feedback_id, { memo: row.querySelector("input").value }, row);
      }
    } catch (e) {
      TS.message(fb, e.message, true);
    }
  },

  async note(feedbackId, body, row) {
    const fb = row.querySelector(".fb");
    try {
      const data = await TS.api(`/api/feedback/${feedbackId}/note`, { method: "POST", body });
      row.querySelectorAll("button, input").forEach((el) => { el.disabled = true; });
      TS.message(fb, data.message);
    } catch (e) {
      TS.message(fb, e.message, true);
    }
  },
};
