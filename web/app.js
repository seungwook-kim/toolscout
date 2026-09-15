// toolscout 웹앱 공통 도우미. 프레임워크 없음.
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
  async header(active) {
    const me = await TS.api("/api/me");
    const nav = [["/", "오늘"], ["/history", "지난 브리핑"], ["/settings", "설정"]]
      .map(([href, label]) => `<a href="${href}" class="${href === active ? "on" : ""}">${label}</a>`).join("");
    document.getElementById("top").innerHTML = `<div class="wrap">
      <a class="brand" href="/">toolscout</a>${me.dev_mode ? '<span class="dev">개발 모드</span>' : ""}
      <nav>${nav}<a href="#" id="logout">로그아웃</a></nav></div>`;
    document.getElementById("logout").onclick = async (event) => {
      event.preventDefault();
      await TS.api("/api/auth/logout", { method: "POST", allow401: true });
      location.href = "/login";
    };
    return me;
  },
  message(el, text, isError = false) {
    el.textContent = text;
    el.classList.toggle("err", isError);
  },
};
