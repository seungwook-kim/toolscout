// toolscout 웹앱 공통 도우미. 프레임워크 없음. 화면 모양은 docs/design-reference.html이 기준이다.
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
  // 기준 줄: 직군·쓰는 도구, 발송 시각·채널 (GET /api/profile)
  basis(state) {
    const p = state.profile;
    const channel = (state.channels.find((c) => c.id === p.channel) || {}).label || p.channel;
    const tools = (p.tools_tags || []).join(", ");
    return `기준 <b>${TS.esc(p.role || "직군 미설정")}</b>${tools ? ` · 쓰는 도구 <b>${TS.esc(tools)}</b>` : ""}<br>${TS.esc(p.notify_time)} 발송, ${TS.esc(channel)}`;
  },
  // 마스트헤드. session이 false면 메뉴·DEV 배지 없이 (로그인·메일 피드백 화면)
  async mast({ active = "", title, when = "", basis = "", pipe = "", session = true }) {
    const me = session ? await TS.api("/api/me") : null;
    const nav = me
      ? `<nav class="nav" aria-label="주 메뉴">${[["/", "오늘"], ["/history", "지난 브리핑"], ["/settings", "설정"]]
        .map(([href, label]) => `<a href="${href}"${href === active ? ' aria-current="page"' : ""}>${label}</a>`).join("")}<a href="/login" id="logout">로그아웃</a></nav>`
      : "";
    document.getElementById("mast").innerHTML = `<div class="in">
      <div class="bar"><a class="brand" href="/">tool<em>scout</em></a>${me && me.dev_mode ? '<span class="mode">DEV</span>' : ""}${nav}</div>
      <div class="date"><h1><small>${TS.esc(when || TS.longDate())}</small>${TS.esc(title)}</h1>${basis ? `<div class="basis">${basis}</div>` : ""}</div>
      ${pipe}</div>`;
    const logout = document.getElementById("logout");
    if (logout) {
      logout.onclick = async (event) => {
        event.preventDefault();
        await TS.api("/api/auth/logout", { method: "POST", allow401: true });
        location.href = "/login";
      };
    }
    return me;
  },
  // 버튼 반응 문구 (.fb). isError면 붉은 글씨
  message(el, text, isError = false) {
    el.textContent = text;
    el.classList.add("on");
    el.classList.toggle("bad", isError);
  },
};
