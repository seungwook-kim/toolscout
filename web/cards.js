// 브리핑 카드 그리기와 피드백 버튼 (오늘 브리핑·지난 브리핑 공용).
const Cards = {
  REASONS: ["번역 어색", "사실 틀림", "나랑 상관없음"],
  TOOL_TYPES: ["mcp", "skill"],

  points(label, list) {
    if (!list || !list.length) return "";
    const rows = list.map((p) => {
      const url = TS.safeUrl(p.evidence_url);
      return `<li>${TS.esc(p.text)}${url ? ` <a href="${TS.esc(url)}" target="_blank" rel="noopener">근거</a>` : ""}</li>`;
    }).join("");
    return `<div><b class="small">${label}</b><ul class="points small">${rows}</ul></div>`;
  },

  buttons(card) {
    const actions = Cards.TOOL_TYPES.includes(card.type) ? ["써봤음", "관심없음", "이상함"] : ["관심없음", "이상함"];
    const on = new Set(card.feedback.actions || []);
    return `<div class="actions">${actions.map((a) =>
      `<button class="btn ${on.has(a) ? "on" : ""}" data-action="${a}" data-item="${card.item_id}">${a}</button>`).join("")}</div>
      <div class="extra"></div><div class="msg"></div>`;
  },

  render(card) {
    const url = TS.safeUrl(card.url);
    const title = url ? `<a href="${TS.esc(url)}" target="_blank" rel="noopener">${TS.esc(card.title)}</a>` : TS.esc(card.title);
    const trace = card.trace_url
      ? `<a class="trace" href="${TS.esc(TS.safeUrl(card.trace_url) || "#")}" target="_blank" rel="noopener" title="${TS.esc(card.trace_url)}">어떻게 만들어졌나</a>` : "";
    const notice = card.notice ? `<div class="notice">${TS.esc(card.notice)}</div>` : "";
    const why = `<details><summary>왜 이 카드?</summary><div class="small">${TS.esc(card.why_this_card)}</div></details>`;
    if (Cards.TOOL_TYPES.includes(card.type)) {
      const install = card.install_cmd
        ? `<div class="install"><code>${TS.esc(card.install_cmd)}</code><button class="btn copy" data-copy="${TS.esc(card.install_cmd)}">복사</button></div>` : "";
      const probe = ["설치", "실행", "도구 목록", "인증"].map((step) => `<span>${step}<br>검증 예정</span>`).join("");
      return `<article class="card" data-item="${card.item_id}">${trace}
        <h3><span class="badge">${card.type === "skill" ? "스킬" : "MCP"}</span>${title}</h3>${notice}
        <div>${TS.esc(card.summary_ko)}</div>
        <div class="forme"><b>나한테는</b>${TS.esc(card.for_me)}</div>
        ${Cards.points("좋은 점", card.pros)}${Cards.points("아쉬운 점", card.cons)}
        <div class="probe">${probe}</div>${install}${why}${Cards.buttons(card)}</article>`;
    }
    return `<article class="card" data-item="${card.item_id}">${trace}
      <h3>${title}</h3>${notice}
      <div>${TS.esc(card.summary_ko)}</div>
      <div class="forme"><b>나한테는</b>${TS.esc(card.for_me)}</div>
      ${why}${Cards.buttons(card)}</article>`;
  },

  mount(container, briefing, day = "오늘") {
    if (!briefing.cards.length) {
      container.innerHTML = `<div class="empty">${briefing.exists
        ? `${day} 볼 만한 게 없었어요.<br><span class="small">${TS.esc(briefing.empty_reason || "")}</span>`
        : "아직 브리핑이 없어요. 설정에서 「지금 만들기」를 누르거나 내일 아침을 기다려 주세요."}</div>`;
      return;
    }
    const news = briefing.cards.filter((c) => !Cards.TOOL_TYPES.includes(c.type));
    const tools = briefing.cards.filter((c) => Cards.TOOL_TYPES.includes(c.type) && !c.related);
    const related = briefing.cards.filter((c) => c.related);
    container.innerHTML = `<h2>뉴스</h2><div class="cards">${news.map(Cards.render).join("") || `<div class="empty">${day} 뉴스 카드 없음</div>`}</div>
      <h2>새 MCP·스킬</h2><div class="cards">${tools.map(Cards.render).join("") || `<div class="empty">${day} 새 도구 없음</div>`}</div>
      ${related.length ? `<h2>이번 주 관련 MCP·스킬</h2><div class="cards">${related.map(Cards.render).join("")}</div>` : ""}`;
    container.querySelectorAll(".copy").forEach((b) => {
      b.onclick = async () => { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "복사됨"; };
    });
    container.querySelectorAll("button[data-action]").forEach((b) => { b.onclick = () => Cards.feedback(b); });
  },

  async feedback(button, extra = {}) {
    const card = button.closest(".card");
    const msg = card.querySelector(".msg");
    try {
      const data = await TS.api("/api/feedback", { method: "POST", body: { item_id: Number(button.dataset.item), action: button.dataset.action, ...extra } });
      button.classList.toggle("on", data.status === "recorded");
      TS.message(msg, data.message);
      const box = card.querySelector(".extra");
      box.innerHTML = "";
      if (data.status !== "recorded") return;
      if (button.dataset.action === "이상함") {
        box.innerHTML = `<div class="row small">${Cards.REASONS.map((r) => `<button class="btn" data-reason="${r}">${r}</button>`).join("")}</div>`;
        box.querySelectorAll("button").forEach((r) => { r.onclick = () => Cards.note(data.feedback_id, { reason: r.dataset.reason }, msg, box); });
      }
      if (button.dataset.action === "써봤음") {
        box.innerHTML = `<div class="row"><input type="text" maxlength="200" placeholder="써 본 소감 한 줄 (선택)"><button class="btn">메모 저장</button></div>`;
        box.querySelector("button").onclick = () => Cards.note(data.feedback_id, { memo: box.querySelector("input").value }, msg, box);
      }
    } catch (e) {
      TS.message(msg, e.message, true);
    }
  },

  async note(feedbackId, body, msg, box) {
    try {
      const data = await TS.api(`/api/feedback/${feedbackId}/note`, { method: "POST", body });
      TS.message(msg, data.message);
      box.innerHTML = "";
    } catch (e) {
      TS.message(msg, e.message, true);
    }
  },
};
