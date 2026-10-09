/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */
// 질문 시트 (W2, /api/ask). TS.shell이 승인·첫 설정을 마친 화면에서 불러 붙인다 (app.js가 300줄을 넘지 않게 나눔, 2026-10-09)
// 범위는 routes/ask.py: 모은 소식 키워드 검색 + 내 브리핑 카드, 대화는 오늘 하루. 데스크톱 오른쪽 비모달 시트, 모바일 아래에서 올라오는 대화상자
TS.askSheet = function askSheet() {
  if (document.getElementById("ask")) return;
  document.body.insertAdjacentHTML("beforeend", `<div class="scrim" id="ask-scrim" hidden></div>
    <aside class="sheet" id="ask" role="dialog" aria-modal="false" aria-labelledby="ask-h" hidden>
      <div class="sheet-head"><h2 id="ask-h">브리핑에 묻기</h2><span class="quota">오늘 남은 질문 <b class="mono" data-quota></b></span>
        <button type="button" class="icon-btn" data-ask-close aria-label="질문창 닫기">${TS.ic("close", "ic-18")}</button></div>
      <p class="sheet-scope">그동안 모은 소식과 내 브리핑에서 찾아 답해요. 원문을 다시 읽으면 1~2분 걸릴 수 있어요.</p>
      <div class="thread" id="ask-thread" role="log" aria-live="polite"></div>
      <form class="composer" id="ask-composer"><label class="sr-only" for="ask-input">질문</label>
        <textarea id="ask-input" rows="1" maxlength="300" placeholder="예: 지난주에 본 벡터 DB 소식 다시 보여 줘" enterkeyhint="send"></textarea>
        <button type="submit" class="btn btn-primary">묻기</button></form>
    </aside>`);
  const sheet = document.getElementById("ask"), scrim = document.getElementById("ask-scrim"), input = document.getElementById("ask-input");
  const thread = document.getElementById("ask-thread"), form = document.getElementById("ask-composer"), small = matchMedia("(max-width: 767px)");
  let limit = null, last = null;
  const quota = (left) => document.querySelectorAll("[data-quota]").forEach((el) => { el.textContent = limit != null ? `${left}/${limit}` : `${left}`; });
  // 답: 확인한 곳 칩(http 링크만), 연속 out이면 질문 예시, out이면 "AI 질문이었어요"(게이트를 건너뛰고 다시 묻기)
  const answer = (a) => {
    const refs = (a.sources || []).filter((s) => TS.safeUrl(s.url)).map((s) => `<a href="${TS.esc(s.url)}" target="_blank" rel="noopener">${TS.esc(s.title || TS.host(s.url))}${TS.ic("ext", "ic-12")}<span class="sr-only">(새 탭)</span></a>`).join("");
    return `<p class="qa-a">${TS.esc(a.answer)}</p>${refs ? `<p class="qa-src"><span>확인한 곳</span>${refs}</p>` : ""}${a.examples
      ? `<p class="help">이렇게 물어볼 수 있어요: ${a.examples.map(TS.esc).join(" / ")}</p>` : ""}${a.gate === "out" ? '<button type="button" class="btn btn-sm" data-retry>AI 질문이었어요</button>' : ""}`;
  };
  const bindRetry = (box, question) => {
    const retry = box.querySelector("[data-retry]");
    if (retry) retry.onclick = () => { retry.disabled = true; send(question, true); };
  };
  const turn = (question, body) => {
    thread.insertAdjacentHTML("beforeend", `<div class="qa"><p class="qa-q">${TS.esc(question)}</p>${body}</div>`);
    const box = thread.lastElementChild;
    bindRetry(box, question);
    box.scrollIntoView({ block: "end" });
    return box;
  };
  const send = async (question, forceUnclear = false) => {
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    const box = turn(question, '<p class="qa-a wait">답을 찾는 중이에요. 원문을 다시 읽으면 1~2분 걸릴 수 있어요</p>');
    try {
      const data = await TS.api("/api/ask", { method: "POST", body: { question, force_unclear: forceUnclear } });
      box.innerHTML = `<p class="qa-q">${TS.esc(question)}</p>${answer(data)}`;
      bindRetry(box, question);
      quota(data.remaining);
    } catch (e) {
      box.querySelector(".qa-a").textContent = e.message;
    } finally { submit.disabled = false; }
  };
  const toggle = (open, from) => {
    if (open) last = from || document.activeElement;
    sheet.hidden = !open;
    scrim.hidden = !open || !small.matches;
    sheet.setAttribute("aria-modal", String(open && small.matches));
    document.querySelectorAll("[data-ask]").forEach((b) => b.setAttribute("aria-expanded", String(open)));
    if (open) input.focus(); else if (last && last.focus) last.focus();
  };
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-ask]");
    if (opener) { e.preventDefault(); toggle(sheet.hidden, opener); }
    else if (e.target.closest("[data-ask-close]") || e.target === scrim) toggle(false);
  });
  document.addEventListener("keydown", (e) => {
    if (sheet.hidden) return;
    if (e.key === "Escape") toggle(false);
    if (e.key === "Tab" && small.matches) {  // 모바일 대화상자는 안에서만 돈다
      const f = sheet.querySelectorAll("button:not(:disabled), a[href], textarea");
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight + 2, 120)}px`; });
  input.addEventListener("keydown", (e) => {  // Enter로 보내기, Shift+Enter는 줄바꿈, 한글 조합 중에는 보내지 않음
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return input.focus();
    input.value = "";
    input.style.height = "auto";
    send(question);
  };
  TS.api("/api/ask").then((h) => {
    limit = h.limit;
    h.turns.forEach((t) => turn(t.question, answer(t)));
    quota(h.remaining);
  }).catch(() => quota("-"));
  if (location.hash === "#ask") toggle(true);
};
