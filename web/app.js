/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */
/*! Lucide 1.57.0 (ISC) https://lucide.dev, 일부 Feather (MIT). 고지 전문: docs/licenses/lucide.txt */
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

  // ===== 아이콘: 인라인 SVG 한 벌(이모지·유니코드 기호는 아이콘으로 쓰지 않는다). TS.ic("ok"). 키는 그대로, 선은 Lucide 1.57.0(이름 대응표는 docs/asset-licenses.md) =====
  ICONS: {
    ok: '<circle cx="12" cy="12" r="10"/><path d="M16 9l-5.5 5.5L8 12"/>', bad: '<circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6 M9 9l6 6"/>',
    warn: '<path d="M21.73 18l-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3 M12 9v4 M12 17h.01"/>',
    na: '<path d="M10.1 2.182a10 10 0 0 1 3.8 0 M13.9 21.818a10 10 0 0 1-3.8 0 M17.609 3.721a10 10 0 0 1 2.69 2.7 M2.182 13.9a10 10 0 0 1 0-3.8 M20.279 17.609a10 10 0 0 1-2.7 2.69 M21.818 10.1a10 10 0 0 1 0 3.8 M3.721 6.391a10 10 0 0 1 2.7-2.69 M6.391 20.279a10 10 0 0 1-2.69-2.7"/>',
    key: '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z M9 12l2 2 4-4"/>',
    risk: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z M12 8v4 M12 16h.01"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>', ext: '<path d="M15 3h6v6 M10 14 21 3 M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    star: '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
    flag: '<path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528"/>',
    mute: '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49 M14.084 14.158a3 3 0 0 1-4.242-4.242 M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143 M2 2l20 20"/>',
    tried: '<path d="M20 6 9 17l-5-5"/>', chev: '<path d="M6 9l6 6 6-6"/>',
    chat: '<path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z M7 11h10 M7 15h6 M7 7h8"/>',
    today: '<path d="M15 18h-5 M18 14h-8 M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"/><rect width="8" height="4" x="10" y="6" rx="1"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2"/>',
    settings: '<path d="M10 5H3 M12 19H3 M14 3v4 M16 17v4 M21 12h-9 M21 19h-5 M21 5h-7 M8 10v4 M8 12H3"/>',
    approve: '<path d="M16 11l2 2 4-4 M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>', search: '<path d="M21 21l-4.34-4.34"/><circle cx="11" cy="11" r="8"/>',
    logout: '<path d="M16 17l5-5-5-5 M21 12H9 M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>', arrow: '<path d="M5 12h14 M12 5l7 7-7 7"/>', back: '<path d="M12 19l-7-7 7-7 M19 12H5"/>',
    eye: '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>',
    mail: '<path d="M22 7l-8.991 5.727a2 2 0 0 1-2.009 0L2 7"/><rect x="2" y="4" width="20" height="16" rx="2"/>', close: '<path d="M18 6 6 18 M6 6l12 12"/>',
    filter: '<path d="M2 5h20 M6 12h12 M9 19h6"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8 M21 3v5h-5 M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16 M8 16H3v5"/>', up: '<path d="M5 12l7-7 7 7 M12 19V5"/>',
    play: '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>', info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4 M12 8h.01"/>',
    wait: '<path d="M5 22h14 M5 2h14 M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22 M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
    // 아침 프롬프트 마크(자체 제작, web/icons/mark.svg의 0.75배). 몸은 currentColor, 해(점)는 --blaze
    mark: '<path d="M3.75 6.375l5.625 5.625L3.75 17.625" fill="none" stroke="currentColor" stroke-width="2.625" stroke-linecap="round" stroke-linejoin="round"/><rect x="11.25" y="16.3125" width="9.75" height="2.625" rx="1.3125" fill="currentColor" stroke="none"/><circle cx="16.125" cy="9.75" r="2.625" stroke="none" style="fill:var(--blaze)"/>',
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
    bar.innerHTML = `<div class="wrap"><a class="brand" href="/"><svg class="mark" aria-hidden="true" focusable="false"><use href="#i-mark"/></svg>toolscout</a>${barHtml}</div>`;
    TS.footer();
    if (!document.getElementById("live")) document.body.insertAdjacentHTML("beforeend", '<div id="live" class="toast" role="status" aria-live="polite"></div>');
    if (window.visualViewport && !TS._kb) {  // 가상 키보드가 올라오면 하단 고정 바를 숨긴다
      TS._kb = true;
      visualViewport.addEventListener("resize", () => document.body.classList.toggle("kb", innerHeight - visualViewport.height > 150));
    }
  },

  // 모든 화면 맨 아래 공통 푸터(2026-10-09): 운영정책·이용약관·개인정보처리방침(굵게)·고객센터 문의하기 + 저작권. frame()이 붙이니 shell·bare 둘 다 나온다
  footer() {
    if (document.querySelector(".site-foot")) return;
    const html = `<footer class="site-foot"><nav aria-label="정책과 문의"><a href="/policy">운영정책</a><a href="/terms">이용약관</a><a class="strong" href="/privacy">개인정보처리방침</a><a href="/support">고객센터 문의하기</a></nav><p class="mono">© 2026 toolscout</p></footer>`;
    const main = document.querySelector("main");
    if (main) main.insertAdjacentHTML("afterend", html); else document.body.insertAdjacentHTML("beforeend", html);
  },

  // 세션 없는 화면(첫 화면·가입·데모·/f): 브랜드만. actions = [[주소, 글자, 주 버튼이면 true]], ctabar면 모바일은 아래 고정 바로
  // tagline이면 워드마크 옆 설명(login·signup·demo만 켠다. 앱 상단바 shell에는 없음, 폰에서는 CSS가 숨김)
  bare({ actions = [], ctabar = false, tagline = false } = {}) {
    const link = (size) => ([href, label, primary]) =>
      `<a class="btn ${size} ${primary ? "btn-primary" : "btn-quiet"}" href="${TS.esc(href)}">${TS.esc(label)}</a>`;
    const links = actions.map(link("btn-sm")).join("");
    TS.frame(`${tagline ? '<span class="tagline">개발자용 AI·MCP 아침 브리핑</span>' : ""}${links ? `<div class="bar-right${ctabar ? " hide-sm" : ""}">${links}</div>` : ""}`);
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
    // 탭·버튼은 gap 있는 flex라 글자와 배지(span)를 형제로 두지 않고 span 하나로 감싼다(flex 맨 글자 규칙, check_screens 11)
    const nav = tabs.length ? `<nav class="tabs" aria-label="주 메뉴">${tabs.map(([href, label]) => `<a href="${href}"${cur(href)}>${href === "/admin/invites"
      ? `<span>${label} ${badge}<span class="sr-only">건 대기</span></span>` : label}</a>`).join("")}</nav>` : "";
    const email = TS.esc(me.email || "");
    const right = !me.approved
      ? `<span class="bar-email mono">${email}</span><a class="btn btn-quiet btn-sm" href="/login" data-logout>로그아웃</a>`
      : `${first && me.is_admin ? `<a class="btn btn-sm only-sm" href="/admin/invites">${TS.ic("approve")}<span>승인 ${badge}</span></a>` : ""}
        ${withAsk ? `<button type="button" class="btn btn-sm hide-sm" data-ask aria-haspopup="dialog" aria-expanded="false">${TS.ic("chat")}<span>질문하기<span data-quota-bar hidden> · <span class="mono"></span>회 남음</span></span></button>` : ""}
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
    if (withAsk) TS.script("/static/ask.js").then(() => { if (TS.askSheet) TS.askSheet(); TS.quotaBar(); }).catch(() => TS.say("질문창을 불러오지 못했어요"));
    return me;
  },
  // 상단바 "질문하기 · N회 남음": 시트의 남은 질문 수(ask.js가 "남음/한도"로 채움)를 따라 앞 숫자만 옮긴다
  quotaBar() {
    const src = document.querySelector("#ask [data-quota]"), bar = document.querySelector("[data-quota-bar]");
    if (!src || !bar) return;
    const sync = () => { const n = (src.textContent.match(/^\d+/) || [""])[0]; bar.hidden = !n; bar.querySelector(".mono").textContent = n; };
    new MutationObserver(sync).observe(src, { childList: true, characterData: true, subtree: true });
    sync();
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
