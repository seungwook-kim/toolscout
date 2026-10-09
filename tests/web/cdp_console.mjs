// Edge 원격 디버깅으로 화면을 열어 콘솔 오류를 모은다 (tests/web/check_minify.py가 부른다).
// 실행: node --experimental-websocket cdp_console.mjs <디버깅 포트> <기준 주소> <경로1> <경로2> ... (경로가 "LOGIN=<주소>"면 그 주소로 이동만 하고 오류는 모으지 않는다)
// 출력: 화면마다 {path, final, errors, bodyChars} 한 줄씩 JSON
const [port, base, ...paths] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let nextId = 1;
const pending = new Map();
let errors = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result); pending.delete(msg.id); return; }
  const p = msg.params || {};
  if (msg.method === "Runtime.exceptionThrown") errors.push("예외: " + (p.exceptionDetails.exception?.description || p.exceptionDetails.text));
  else if (msg.method === "Runtime.consoleAPICalled" && p.type === "error") errors.push("console.error: " + p.args.map((a) => a.value ?? a.description).join(" "));
  else if (msg.method === "Log.entryAdded" && p.entry.level === "error") errors.push(`로그: ${p.entry.text} ${p.entry.url || ""}`);
});
const send = (method, params = {}) => new Promise((resolve) => { const id = nextId++; pending.set(id, resolve); ws.send(JSON.stringify({ id, method, params })); });
for (const domain of ["Runtime", "Log", "Page"]) await send(`${domain}.enable`);

for (const path of paths) {
  errors = [];
  const login = path.startsWith("LOGIN=");
  await send("Page.navigate", { url: login ? path.slice(6) : base + path });
  await sleep(2500);
  const there = await send("Runtime.evaluate", { expression: "location.pathname + ' ' + document.body.innerText.length", returnByValue: true });
  const [final, chars] = String(there.result.value).split(" ");
  if (!login) console.log(JSON.stringify({ path, final, errors, bodyChars: Number(chars) }));
}
ws.close();
