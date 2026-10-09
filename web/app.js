/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */
// toolscout 웹앱 공통 도우미와 앱 셸. 프레임워크 없음. 모양 기준은 docs/design-reference.html (2026-10-09 리디자인)
const TS = {
  async api(path, options = {}) {
    const init = { method: options.method || "GET", headers: {}, credentials: "same-origin" };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    const response = await fetch(path, init);
    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (response.status === 401 && !options.allow401) {
      location.href = "/login";
      throw new Error("로그인이 필요해요");
    }
    if (!response.ok) {
      const detail = data && (data.detail || data.message);
      throw new Error(typeof detail === "string" ? detail : `요청 실패 (${response.status})`);
    }
    return data;
  },
  esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },
  safeUrl(url) {
    return /^https?:\/\//.test(url || "") ? url : "";
  },
  host(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; }
  },
  longDate(value) {
    const d = value ? new Date(`${value}T00:00:00`) : new Date();
    return new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" }).format(d);
  },
  daysAgo(iso) {
    const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    return Number.isFinite(days) ? (days <= 0 ? "오늘" : `${days}일 전`) : "";
  },
  // 버튼 옆 반응 문구. isError면 붉은 글씨 (새 화면은 .msg 또는 TS.say를 쓴다)
  message(el, text, isError = false) {
    el.textContent = text;
    el.classList.add("on");
    el.classList.toggle("bad", isError);
  },
  // 기준 줄: 직군·쓰는 도구 (GET /api/profile). link면 끝에 "기준 바꾸기"
  basis(state, link = false) {
    const p = state.profile;
    const tools = (p.tools_tags || []).join(", ");
    return `기준 <b>${TS.esc(p.role || "직군 미설정")}</b>${tools ? ` · ${TS.esc(tools)}` : ""}${link ? ' · <a href="/settings">기준 바꾸기</a>' : ""}`;
  },
  // 지난 일은 절대 시각 "10.06 14:20" (이 기기 시간대)
  stamp(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const two = (n) => String(n).padStart(2, "0");
    return `${two(d.getMonth() + 1)}.${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
  },
  // 승인 대기 수 표시: 0이면 숫자 없음, 100 이상은 99+
  count(n) {
    n = Number(n) || 0;
    return n <= 0 ? "" : n >= 100 ? "99+" : String(n);
  },

  // ===== 아이콘: 인라인 SVG 한 벌(이모지·유니코드 기호는 아이콘으로 쓰지 않는다). TS.ic("ok") =====
  ICONS: {
    ok: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8 5.4-5.6"/>', bad: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    warn: '<path d="M12 3.8l9.2 16H2.8z"/><path d="M12 10v4.2M12 17v.2"/>', na: '<circle cx="12" cy="12" r="9" stroke-dasharray="2.4 2.6"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l8.5-8.5M16 7l2.5 2.5M13.5 9.5l2 2"/>',
    shield: '<path d="M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z"/><path d="M8.8 12l2.3 2.3 4.2-4.3"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>', ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    star: '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/>', flag: '<path d="M5 21V4M5 4h11.5l-2 4 2 4H5"/>',
    mute: '<path d="M3 12s3.5-6 9-6c1.6 0 3 .5 4.2 1.2M21 12s-3.5 6-9 6c-1.6 0-3-.5-4.2-1.2M4 4l16 16"/>', tried: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    chev: '<path d="M6 9l6 6 6-6"/>', chat: '<path d="M4 5h16v11H9.5L4 20z"/><path d="M8 9.5h8M8 12.5h5"/>',
    today: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    history: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 9"/><path d="M4.5 4.5V9H9M12 8v4.5l3 2"/>',
    settings: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    approve: '<circle cx="10" cy="8" r="3.5"/><path d="M3.5 20c.8-3.5 3.4-5.5 6.5-5.5 1.3 0 2.5.3 3.5 1M15 18l2 2 4-4"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>', logout: '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 16l-4-4 4-4M6 12h10"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>', back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5l8.5 6.5 8.5-6.5"/>', close: '<path d="M6 6l12 12M18 6L6 18"/>',
    filter: '<path d="M4 6h16M7 12h10M10 18h4"/>', refresh: '<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5L20 16M20 20v-4h-4"/>',
    up: '<path d="M12 19V6M6.5 11.5L12 6l5.5 5.5"/>', play: '<path d="M7 5l12 7-12 7z"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.2"/>',
  },
  ic(name, cls = "") {
    return `<svg class="ic${cls ? ` ${cls}` : ""}" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  },
  sprite() {
    if (document.getElementById("ts-icons")) return;
    const symbols = Object.entries(TS.ICONS).map(([k, v]) => `<symbol id="i-${k}" viewBox="0 0 24 24">${v}</symbol>`).join("");
    document.body.insertAdjacentHTML("afterbegin", `<svg id="ts-icons" width="0" height="0" style="position:absolute" aria-hidden="true">${symbols}</svg>`);
  },

  // 상태 알림(토스트). 화면 읽기 프로그램도 읽는다
  say(text) {
    const live = document.getElementById("live");
    if (!live) return;
    clearTimeout(TS._sayTimer);
    live.textContent = "";
    setTimeout(() => { live.textContent = text; }, 30);
    TS._sayTimer = setTimeout(() => { live.textContent = ""; }, 3000);
  },

  // ===== 앱 셸 =====
  // 공통 바탕: 아이콘, 본문 건너뛰기, 토스트, 상단바 자리(#appbar, 없으면 main 앞에 만든다)
  frame(barHtml) {
    TS.sprite();
    const main = document.querySelector("main");
    if (main && !main.id) main.id = "main";
    let bar = document.getElementById("appbar");
    if (!bar) {
      const html = '<header id="appbar"></header>';
      if (main) main.insertAdjacentHTML("beforebegin", html); else document.body.insertAdjacentHTML("afterbegin", html);
      bar = document.getElementById("appbar");
    }
    if (!document.querySelector(".skip")) document.body.insertAdjacentHTML("afterbegin", '<a class="skip" href="#main">본문으로 건너뛰기</a>');
    bar.className = "appbar";
    bar.innerHTML = `<div class="wrap"><a class="brand" href="/"><span class="blaze" aria-hidden="true"></span>toolscout</a>${barHtml}</div>`;
    if (!document.getElementById("live")) document.body.insertAdjacentHTML("beforeend", '<div id="live" class="toast" role="status" aria-live="polite"></div>');
    if (window.visualViewport && !TS._kb) {  // 가상 키보드가 올라오면 하단 고정 바를 숨긴다
      TS._kb = true;
      visualViewport.addEventListener("resize", () => document.body.classList.toggle("kb", innerHeight - visualViewport.height > 150));
    }
  },

  // 세션 없는 화면(첫 화면·가입·데모·/f): 브랜드만. actions = [[주소, 글자, 주 버튼이면 true]], ctabar면 모바일은 아래 고정 바로
  bare({ actions = [], ctabar = false } = {}) {
    const link = (size) => ([href, label, primary]) =>
      `<a class="btn ${size} ${primary ? "btn-primary" : "btn-quiet"}" href="${TS.esc(href)}">${TS.esc(label)}</a>`;
    const links = actions.map(link("btn-sm")).join("");
    TS.frame(links ? `<div class="bar-right${ctabar ? " hide-sm" : ""}">${links}</div>` : "");
    if (ctabar && links && !document.querySelector(".ctabar")) {
      document.body.insertAdjacentHTML("beforeend", `<div class="ctabar">${actions.map(link("btn-lg")).join("").replace(/btn-quiet/g, "")}</div>`);
      document.body.classList.add("has-ctabar");
    }
  },

  // 로그인한 화면. GET /api/me로 계정 상태를 보고 탭만 더하거나 뺀다 (회의 합의 "한 셸, 네 가지 계정 상태")
  // 승인 전: 탭 없음(이메일·로그아웃) / 첫 설정: 탭 없음, 관리자만 "첫 설정 · 승인 N" / 일반: 오늘·지난 브리핑·설정 + 질문하기 / 관리자: + 승인 N
  // active: 지금 화면 주소(기본 location.pathname), ask: 질문 시트를 붙일지. 반환: /api/me 응답
  async shell({ active = location.pathname, ask = true } = {}) {
    const me = await TS.api("/api/me");
    const pending = me && me.is_admin ? Number(me.pending_applications) || 0 : 0;
    const first = me.approved && !me.profile_done;
    const full = me.approved && me.profile_done;
    const withAsk = full && ask;
    const cur = (href) => (href === active ? ' aria-current="page"' : "");
    const badge = `<span class="count" data-pending${pending ? "" : " hidden"}>${TS.count(pending)}</span>`;
    const tabs = !me.approved ? [] : first ? (me.is_admin ? [["/settings", "첫 설정"], ["/admin/invites", "승인"]] : [])
      : [["/", "오늘"], ["/history", "지난 브리핑"], ["/settings", "설정"]].concat(me.is_admin ? [["/admin/invites", "승인"]] : []);
    const nav = tabs.length ? `<nav class="tabs" aria-label="주 메뉴">${tabs.map(([href, label]) => `<a href="${href}"${cur(href)}>${label}${href === "/admin/invites"
      ? ` ${badge}<span class="sr-only">건 대기</span>` : ""}</a>`).join("")}</nav>` : "";
    const email = TS.esc(me.email || "");
    const right = !me.approved
      ? `<span class="bar-email mono">${email}</span><a class="btn btn-quiet btn-sm" href="/login" data-logout>로그아웃</a>`
      : `${first && me.is_admin ? `<a class="btn btn-sm only-sm" href="/admin/invites">${TS.ic("approve")}승인 ${badge}</a>` : ""}
        ${withAsk ? `<button type="button" class="btn btn-sm hide-sm" data-ask aria-haspopup="dialog" aria-expanded="false">${TS.ic("chat")}질문하기 <span class="mono" data-quota></span></button>` : ""}
        <details class="acct"><summary aria-label="계정 메뉴"><span class="avatar" aria-hidden="true">${TS.esc((me.email || "?")[0].toUpperCase())}</span></summary>
        <div class="acct-menu"><p class="mono">${email}</p>${me.is_admin ? `<p class="acct-role"><span class="tag-mode tag-admin">${TS.ic("lock")}관리자</span></p>` : ""}
        ${full ? `<a href="/settings">${TS.ic("settings")}설정</a>` : ""}<a href="/login" data-logout>${TS.ic("logout")}로그아웃</a></div></details>`;
    TS.frame(`${me.dev_mode ? '<span class="tag-mode tag-dev">DEV</span>' : ""}${nav}<div class="bar-right">${right}</div>`);
    document.body.dataset.acct = me.is_admin ? "admin" : "user";
    if (full && !document.querySelector(".tabbar")) {
      const items = [["/", "today", "오늘"], ["/history", "history", "지난"], withAsk ? ["ask", "chat", "질문"] : null, ["/settings", "settings", "설정"],
        me.is_admin ? ["/admin/invites", "approve", "승인"] : null].filter(Boolean);
      document.body.insertAdjacentHTML("beforeend", `<nav class="tabbar" aria-label="주 메뉴" style="--tabs:${items.length}">${items.map(([href, icon, label]) => href === "ask"
        ? `<button type="button" data-ask aria-haspopup="dialog" aria-expanded="false">${TS.ic(icon, "ic-22")}${label}</button>`
        : `<a href="${href}"${cur(href)}>${TS.ic(icon, "ic-22")}${label}${href === "/admin/invites" ? badge : ""}</a>`).join("")}</nav>`);
      document.body.classList.add("has-tabbar");
    }
    document.querySelectorAll("[data-logout]").forEach((a) => {
      a.onclick = async (event) => {
        event.preventDefault();
        await TS.api("/api/auth/logout", { method: "POST", allow401: true });
        location.href = "/login";
      };
    });
    if (withAsk) TS.script("/static/ask.js").then(() => TS.askSheet && TS.askSheet()).catch(() => TS.say("질문창을 불러오지 못했어요"));
    return me;
  },
  // 스크립트 한 번만 불러오기 (질문 시트 web/ask.js)
  script(src) {
    if (document.querySelector(`script[src="${src}"]`)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  },

  // 복사 버튼(data-copy="글자", 화면 어디서나): 클립보드에 넣고, 못 쓰면 바로 앞 글자(pre)를 선택해 둔다
  async copy(button) {
    const lab = button.querySelector(".lab");
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      TS.say("복사했어요");
      if (lab) { lab.textContent = "복사됨"; setTimeout(() => { lab.textContent = "복사"; }, 2000); }
    } catch (e) {
      const range = document.createRange();
      range.selectNodeContents(button.previousElementSibling || button);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      TS.say("글자를 선택했어요. Ctrl+C로 복사하세요");
    }
  },

  // 승인·거절할 때마다 탭·하단 탭의 대기 수를 함께 바꾼다
  setPending(n) {
    document.querySelectorAll("[data-pending]").forEach((el) => {
      el.textContent = TS.count(n);
      el.hidden = !TS.count(n);
    });
  },

  // 제자리 확인 줄 (confirm()·모달 없음). button 바로 뒤에 열고 [확정][취소]. 다시 누르면 닫는다. html은 부르는 쪽이 이스케이프
  confirmLine(button, { html, ok = "확인", onOk }) {
    const open = button.nextElementSibling;
    const close = (line) => { line.remove(); button.setAttribute("aria-expanded", "false"); };
    if (open && open.classList.contains("confirm-line")) return close(open);
    button.insertAdjacentHTML("afterend", `<div class="confirm-line" tabindex="-1"><div>${html}</div><div class="acts">
      <button type="button" class="btn btn-danger" data-ok>${TS.esc(ok)}</button><button type="button" class="btn btn-quiet" data-cancel>취소</button></div></div>`);
    const line = button.nextElementSibling, go = line.querySelector("[data-ok]");
    button.setAttribute("aria-expanded", "true");
    line.focus();
    line.querySelector("[data-cancel]").onclick = () => { close(line); button.focus(); };
    go.onclick = async () => {
      go.disabled = true;
      try { await onOk(); close(line); } catch (e) { TS.say(e.message); go.disabled = false; }
    };
  },
};

// 화면 어디서나: 펼침 버튼(button.more[aria-controls], 카드 '자세히'·'어떻게 골랐나')은 가리키는 칸을 열고 닫고, [data-copy]는 복사
document.addEventListener("click", (e) => {
  const copy = e.target.closest("[data-copy]");
  if (copy) return TS.copy(copy);
  const more = e.target.closest("button.more[aria-controls]");
  const panel = more && document.getElementById(more.getAttribute("aria-controls"));
  if (!panel) return;
  const open = more.getAttribute("aria-expanded") !== "true";
  more.setAttribute("aria-expanded", String(open));
  panel.hidden = !open;
});
