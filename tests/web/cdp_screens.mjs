// 화면 자동 검수(디자인 회의 4장 4-5 항목 + 2판 2-4의 10 잘림·11 flex 맨 글자·브랜드 검수)와 스크린샷. tests/web/check_screens.py가 화면마다 따로 부른다.
// 실행: node --experimental-websocket cdp_screens.mjs <디버깅 포트> <작업 JSON 경로>
// 작업 JSON: {out, cases, tool_head, steps:[{login:url} | {clear:true} | {name, url, wait, verdict, brand}]}. 화면마다 폭 1366(높이 650)·390·360 × 라이트·자동 다크·수동 다크
// 출력: 조합마다 {screen, width, theme, final, fails:{항목: [...]}} 한 줄, 판정 사례는 {verdict: [...]}·{tool_head: [...]} 한 줄씩. 스크린샷 out/<화면>_<폭>(_dark|_mdark).png
// 10 clip·11 flextext·brand는 모양만 보므로 라이트에서 한 번만 잰다
import { writeFileSync, readFileSync } from "node:fs";
const [port, jobPath] = process.argv.slice(2);
const job = JSON.parse(readFileSync(jobPath, "utf-8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let nextId = 1, errors = [];
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result || { error: msg.error }); pending.delete(msg.id); return; }
  const p = msg.params || {};
  if (msg.method === "Runtime.exceptionThrown") errors.push("예외: " + (p.exceptionDetails.exception?.description || p.exceptionDetails.text).split("\n")[0]);
  else if (msg.method === "Runtime.consoleAPICalled" && p.type === "error") errors.push("console.error: " + p.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200));
  // 비로그인 확인(TS.api allow401)이 받는 /api/me 401은 의도된 응답이라 오류로 세지 않는다
  else if (msg.method === "Log.entryAdded" && p.entry.level === "error" && !(p.entry.text.includes("401") && (p.entry.url || "").endsWith("/api/me"))) errors.push(`로그: ${p.entry.text} ${p.entry.url || ""}`.slice(0, 200));
});
const send = (method, params = {}) => new Promise((resolve) => { const id = nextId++; pending.set(id, resolve); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result?.value;
for (const d of ["Runtime", "Log", "Page", "Network"]) await send(`${d}.enable`);

// ----- 페이지 안에서 도는 검사(문자열로 넘긴다). 결과: {항목: [설명...]} -----
function audit(o) {
  const out = { overflow: [], contrast: [], border: [], size: [], touch: [], cfoot: [], focus: [], motion: [], clip: [], flextext: [], brand: [] };
  const W = innerWidth, cs = (e) => getComputedStyle(e);
  const name = (e) => `${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""}${[...e.classList].slice(0, 3).map((c) => "." + c).join("")}${(e.innerText || e.value || "").trim() ? ` "${(e.innerText || e.value || "").trim().slice(0, 24)}"` : e.getAttribute("href") ? ` [${e.getAttribute("href").slice(0, 30)}]` : e.getAttribute("aria-label") ? ` [${e.getAttribute("aria-label")}]` : ""}`;
  const parse = (c) => { const m = String(c).match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const blend = (t, b) => [0, 1, 2].map((i) => t[i] * t[3] + b[i] * (1 - t[3])).concat(1);
  const lum = (c) => { const l = c.slice(0, 3).map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return Math.round(((x + 0.05) / (y + 0.05)) * 100) / 100; };
  const memo = new Map(), opa = new Map();
  const bgOf = (el) => {  // 가장 가까운 불투명 배경까지 반투명 층을 겹친다(요소별로 한 번만 계산)
    if (memo.has(el)) return memo.get(el);
    const layers = [];
    for (let e = el; e; e = e.parentElement) { const c = parse(cs(e).backgroundColor); if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; } }
    let col = layers.length && layers[layers.length - 1][3] >= 1 ? layers.pop() : (parse(cs(document.body).backgroundColor) || [255, 255, 255, 1]);
    while (layers.length) col = blend(layers.pop(), col);
    memo.set(el, col);
    return col;
  };
  const opacityOf = (el) => { if (!el) return 1; if (!opa.has(el)) opa.set(el, Number(cs(el).opacity) * opacityOf(el.parentElement)); return opa.get(el); };
  const visible = (e) => { const r = e.getBoundingClientRect(), s = cs(e); return r.width > 0 && r.height > 0 && r.bottom + scrollY > 0 && s.visibility !== "hidden" && !e.closest(".sr-only,[aria-hidden='true']") && r.right > 0 && r.left < W; };
  const push = (k, v) => { if (out[k].length < 12 && !out[k].includes(v)) out[k].push(v); };
  // 1. 가로 넘침 (가로 스크롤·잘라 내는 상자 안은 제외)
  if (document.documentElement.scrollWidth > W) push("overflow", `문서 폭 ${document.documentElement.scrollWidth} > ${W}`);
  const clipped = (e) => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) if (/(auto|scroll|hidden|clip)/.test(cs(a).overflowX)) return true; return false; };
  for (const e of document.body.querySelectorAll("*")) {
    const r = e.getBoundingClientRect();
    if (r.right > W + 1 && r.width > 0 && r.left < W && cs(e).position !== "fixed" && !clipped(e) && !(e.parentElement && e.parentElement.getBoundingClientRect().right > W + 1)) push("overflow", `${name(e)} 오른쪽 ${Math.round(r.right)}`);
  }
  // 3·5. 글자 대비·크기 (보이는 글자 노드마다)
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement, text = n.textContent.trim();
    if (!text || !el || el.closest("script,style,noscript,svg,option") || !visible(el)) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    if (![...range.getClientRects()].some((r) => r.width > 0 && r.right > 0 && r.left < W)) continue;
    const s = cs(el), size = parseFloat(s.fontSize), weight = Number(s.fontWeight) || 400;
    if (/[가-힣]/.test(text) && size < 13) push("size", `${name(el)} ${size}px`);
    else if (size < 12) push("size", `${name(el)} ${size}px`);
    if (el.closest("button:disabled,[aria-disabled='true'],.btn[disabled]")) continue;
    const fg = parse(s.color); if (!fg) continue;
    const bg = bgOf(el), c = ratio(blend([fg[0], fg[1], fg[2], fg[3] * opacityOf(el)], bg), bg);
    const need = size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5;
    if (c < need) push("contrast", `${name(el)} ${c} < ${need}`);
  }
  // 4. 누르는 것의 테두리 대비 (테두리가 있을 때만, 바깥 배경과)
  for (const e of document.querySelectorAll("button,.btn,.fchip,.rchip,.input")) {
    if (!visible(e) || e.disabled) continue;
    const s = cs(e), w = parseFloat(s.borderTopWidth), bc = parse(s.borderTopColor);
    if (!w || s.borderTopStyle === "none" || !bc || bc[3] === 0) continue;
    const outside = bgOf(e.parentElement), c = ratio(blend(bc, outside), outside);
    if (c < 3) push("border", `${name(e)} ${c}`);
  }
  // 6. 터치 44×44 (폰 폭만, 문장 속 인라인 링크 제외)
  if (o.touch) for (const e of document.querySelectorAll("a,button,summary,input,select,label.rchip,[role=button]")) {
    if (!visible(e) || (e.tagName === "INPUT" && (e.type === "hidden" || Number(cs(e).opacity) === 0))) continue;
    const r = e.getBoundingClientRect();
    if (e.tagName === "A" && cs(e).display === "inline" && e.parentElement && e.parentElement.textContent.trim().length > e.textContent.trim().length) continue;
    if (r.width < 44 - 0.5 || r.height < 44 - 0.5) push("touch", `${name(e)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  // 6-1. 카드 버튼 줄(360): 쉴 때·하나 눌렸을 때 한 줄인지
  if (o.cfoot) for (const f of document.querySelectorAll(".c-foot")) {
    if (!visible(f)) continue;
    const line = () => { const s = cs(f), inner = f.getBoundingClientRect().height - parseFloat(s.paddingTop) - parseFloat(s.paddingBottom) - parseFloat(s.borderTopWidth) - parseFloat(s.borderBottomWidth);
      const tallest = Math.max(0, ...[...f.querySelectorAll("button,a")].filter(visible).map((b) => b.getBoundingClientRect().height)); return inner <= tallest + 4; };
    if (!line()) push("cfoot", `${name(f.closest(".card") || f)} 쉴 때 두 줄`);
    const b = f.querySelector('button[aria-pressed="false"]');
    if (b) { b.setAttribute("aria-pressed", "true"); if (!line()) push("cfoot", `${name(f.closest(".card") || f)} 하나 눌림 두 줄`); b.setAttribute("aria-pressed", "false"); }
  }
  // 10. 잘림: 세로로 넘치는데 잘라 내거나 자체 스크롤하는 상자(1366×650에서 레일 아래 칸이 안 보이던 병). 일부러 줄이는 것·입력·가로 스크롤 칸은 뺀다
  if (o.layout) for (const e of document.body.querySelectorAll("*")) {
    const s = cs(e);
    if (!/(auto|scroll|hidden|clip)/.test(s.overflowY) || e.scrollHeight <= e.clientHeight + 2) continue;
    if (e.matches("textarea,select,.jump,.cmd pre,.dl-wrap,.sres,.sheet .thread,.otp,.sr-only") || e.closest(".sr-only") || !visible(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1 || (s.webkitLineClamp && s.webkitLineClamp !== "none") || (s.whiteSpace === "nowrap" && s.textOverflow === "ellipsis")) continue;
    push("clip", `${name(e)} 내용 ${e.scrollHeight} > 보임 ${e.clientHeight}`);
  }
  // 11. flex 맨 글자: gap이 있는 flex·grid 안에서 맨 글자와 글자 요소가 형제로 붙으면 사이에 gap이 끼어 '도구 5 개'처럼 띄어 보인다(아이콘 svg와 맨 글자는 괜찮다)
  if (o.layout) {
    const texty = new Set(["SPAN", "B", "CODE", "A", "EM", "STRONG"]);
    const near = (n, dir) => { let x = n[dir]; while (x && (x.nodeType === 8 || (x.nodeType === 3 && !x.textContent.trim()))) x = x[dir]; return x; };
    for (const e of document.body.querySelectorAll("*")) {
      const s = cs(e);
      if (!/^(inline-)?(flex|grid)$/.test(s.display) || !(parseFloat(s.columnGap) > 0 || parseFloat(s.rowGap) > 0) || !visible(e)) continue;
      for (const n of e.childNodes) {
        if (n.nodeType !== 3 || !n.textContent.trim()) continue;
        const sib = [near(n, "previousSibling"), near(n, "nextSibling")].find((x) => x && x.nodeType === 1 && texty.has(x.tagName) && !/(absolute|fixed)/.test(cs(x).position));
        if (sib) { push("flextext", `${name(e)}: "${n.textContent.trim().slice(0, 12)}" + <${sib.tagName.toLowerCase()}${sib.className ? "." + [...sib.classList].join(".") : ""}>`); break; }
      }
    }
  }
  // 브랜드 검수(1장 2판 검수 1·2·4·5): 제호·리드 크기, 제호 마크, 그림 자리, 워드마크 옆 설명
  if (o.brand) {
    const b = o.brand, shown = (e) => !!e && cs(e).display !== "none" && e.getBoundingClientRect().width > 0;
    const date = document.querySelector(".today .date");
    if (shown(date)) {
      const fs = parseFloat(cs(date).fontSize), want = W >= 1200 ? 36 : W < 768 ? 26 : 0, lead = document.querySelector(".card.hl .c-title");
      if (want && Math.abs(fs - want) > 0.5) push("brand", `제호 .date ${fs}px != ${want}px`);
      if (shown(lead) && parseFloat(cs(lead).fontSize) >= fs) push("brand", `리드 제목 ${parseFloat(cs(lead).fontSize)}px >= 제호 ${fs}px`);
      const mk = (date.closest("h1,h2") || date.parentElement).querySelector(".mark-lg"), r = mk && mk.getBoundingClientRect();
      if (W >= 1200 && !(shown(mk) && Math.round(r.width) === 40 && Math.round(r.height) === 40)) push("brand", `제호 .mark-lg ${mk ? `${Math.round(r.width)}x${Math.round(r.height)}` : "없음"} (40x40이어야 함)`);
      if (W < 1200 && mk && cs(mk).display !== "none") push("brand", "제호 .mark-lg가 1199 이하에서 보임");
    }
    const tag = document.querySelector(".appbar .tagline");
    if (b.app && tag) push("brand", "앱 상단바에 .tagline이 있음");
    if (b.tagline && W >= 1200 && !shown(tag)) push("brand", "상단바 .tagline 없음");
    if (b.tagline && W < 768 && shown(tag)) push("brand", "상단바 .tagline이 폰에서 보임");
    if (b.oneIll) { const n = [...document.querySelectorAll("svg.ill")].filter(shown).length; if (n !== 1) push("brand", `그림 .ill ${n}개(1개여야 함)`); }
    if (b.dawn && !document.querySelector('use[href$="#dawn"]')) push("brand", "아직 없음 상태에 dawn 그림 없음");
    if (b.dawn) { const n = document.body.innerText.split("아직 오늘 브리핑이 없어요").length - 1; if (n > 1) push("brand", `'아직 오늘 브리핑이 없어요' ${n}번`); }
    if (b.zero && !document.querySelector('use[href$="#empty"]')) push("brand", "카드 0장 상태에 empty 그림 없음");
  }
  // 7. 포커스 링: outline 또는 box-shadow 색이 바깥 배경과 3:1
  const focusables = [...document.querySelectorAll("a[href],button,summary,input:not([type=hidden]),select,textarea,[tabindex='0']")].filter((e) => visible(e) && !e.disabled);
  const seen = new Set();
  for (const e of focusables) {
    const sig = `${e.tagName}|${e.className}|${e.getAttribute("aria-pressed")}|${bgOf(e.parentElement).join()}`;  // 같은 모양은 한 번만
    if (seen.has(sig)) continue;
    seen.add(sig);
    e.focus({ preventScroll: true });
    if (document.activeElement !== e) continue;
    const s = cs(e), outside = bgOf(e.parentElement), rings = [];
    if (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 1) rings.push(parse(s.outlineColor));
    for (const m of (s.boxShadow === "none" ? "" : s.boxShadow).matchAll(/rgba?\([^)]+\)/g)) rings.push(parse(m[0]));
    const best = Math.max(0, ...rings.filter((c) => c && c[3] > 0).map((c) => ratio(blend(c, outside), outside)));
    if (best < 3) push("focus", `${name(e)} ${best}`);
    e.blur();
  }
  // 8. 움직임 줄이기: reduce에서 transition 시간 0
  if (o.motion) for (const e of document.querySelectorAll("*")) {
    if (cs(e).transitionDuration.split(",").some((d) => parseFloat(d) > 0)) push("motion", `${name(e)} ${cs(e).transitionDuration}`);
  }
  return out;
}
const runAudit = (o) => evaluate(`(${audit.toString()})(${JSON.stringify(o)})`);
const media = (dark, reduce = false) => send("Emulation.setEmulatedMedia", { features: [
  { name: "prefers-color-scheme", value: dark ? "dark" : "light" }, { name: "prefers-reduced-motion", value: reduce ? "reduce" : "no-preference" }] });
const key = async () => { for (const type of ["keyDown", "keyUp"]) await send("Input.dispatchKeyEvent", { type, key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 }); };

for (const step of job.steps) {
  if (step.clear) { await send("Network.clearBrowserCookies"); continue; }
  if (step.login) { await send("Page.navigate", { url: step.login }); await sleep(2500); continue; }
  for (const width of [1366, 390, 360]) {
    const mobile = width < 768;
    await send("Emulation.setDeviceMetricsOverride", { width, height: mobile ? 844 : 650, deviceScaleFactor: 1, mobile });  // 1366×768 노트북의 실제 안쪽 높이 약 650
    await send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
    await media(false);
    errors = [];
    await send("Page.navigate", { url: step.url });
    await sleep(step.wait || 2500);
    const final = await evaluate("location.pathname");
    await key();
    for (const theme of ["light", "dark", "mdark"]) {
      await media(theme === "dark");
      await evaluate(theme === "mdark" ? 'document.documentElement.dataset.theme = "dark"' : 'document.documentElement.removeAttribute("data-theme")');
      await sleep(400);
      const t0 = Date.now(), light = theme === "light";
      const fails = await runAudit({ touch: mobile, cfoot: width === 360 && light, layout: light, brand: light ? step.brand || {} : null }) || { audit: ["검사 스크립트 실패"] };
      if (light) { await media(false, true); await sleep(200); fails.motion = (await runAudit({ motion: true }))?.motion || []; await media(false); }
      fails.console = light ? errors.slice(0, 12) : [];
      const m = await send("Page.getLayoutMetrics");
      const h = Math.min(Math.ceil((m.cssContentSize || m.contentSize).height), 4000);
      const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width, height: h, scale: 1 } });
      if (shot.data) writeFileSync(`${job.out}/${step.name}_${width}${light ? "" : theme === "dark" ? "_dark" : "_mdark"}.png`, Buffer.from(shot.data, "base64"));
      console.log(JSON.stringify({ screen: step.name, width, theme, final, fails, ms: Date.now() - t0 }));
    }
    await evaluate('document.documentElement.removeAttribute("data-theme")');
    if (step.verdict && width === 1366) {  // 9. 판정 배지와 도구 머리 글: 사례를 페이지 안 Cards.badge·Cards.toolHead로
      const got = await evaluate(`(() => { const cases = ${JSON.stringify(job.cases)};
        if (!window.Cards || typeof Cards.badge !== "function") return [{ id: "*", error: "Cards.badge 없음" }];
        return cases.map((c) => { try { const b = Cards.badge(c.card); return { id: c.id, got: b ? { word: b.word, tone: b.tone, icon: b.icon } : null }; } catch (e) { return { id: c.id, error: String(e) }; } }); })()`);
      console.log(JSON.stringify({ verdict: got }));
      const head = await evaluate(`(() => { const cases = ${JSON.stringify(job.tool_head || [])};
        if (!window.Cards || typeof Cards.toolHead !== "function") return cases.length ? [{ id: "*", error: "Cards.toolHead 없음" }] : [];
        const text = (v) => { const d = document.createElement("div"); d.innerHTML = typeof v === "string" ? v : String((v && (v.html ?? v.text)) || ""); return d.textContent.replace(/\\s+/g, " ").trim(); };
        return cases.map((c) => { try { return { id: c.id, got: text(Cards.toolHead(c.cards)) }; } catch (e) { return { id: c.id, error: String(e) }; } }); })()`);
      console.log(JSON.stringify({ tool_head: head }));
    }
  }
}
ws.close();
