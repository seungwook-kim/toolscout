// 프로필 입력 부품 (설정·첫 설정 공통): 관심 주제 슬라이더, 쓰는 도구 태그 입력. 모양은 profile.css
// 데이터는 GET /api/profile 응답(state): topics(id→이름), presets(직군→가중치), roles
const Profile = {
  sign(n) { n = Number(n); return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0"; },

  // 슬라이더 칠하기: 0에서 값까지 채우고, 직군 기본값 자리에 눈금(노치)을 둔다
  paint(range) {
    const v = Number(range.value), pos = (n) => (n + 5) / 10, row = range.closest(".wrow");
    range.style.setProperty("--a", pos(Math.min(0, v)));
    range.style.setProperty("--b", pos(Math.max(0, v)));
    row.classList.toggle("neg", v < 0);
    const out = row.querySelector(".wval");
    out.textContent = Profile.sign(v);
    out.classList.toggle("pos", v > 0);
    out.classList.toggle("zero", v === 0);
    row.querySelector(".whelp").hidden = v > -5;
  },

  // 관심 주제 10줄. weights: {주제id: 값}, role: 기본값 눈금을 가져올 직군, onChange(id, 값)
  topics(box, state, weights, role, onChange) {
    const def = state.presets[role] || {};
    box.innerHTML = Object.entries(state.topics).map(([id, name]) => {
      const v = weights[id] ?? 0, d = def[id];
      return `<div class="wrow" data-k="${TS.esc(id)}">
        <label class="wname" for="w-${TS.esc(id)}">${TS.esc(name)} <span class="chg" hidden>· 바뀜</span></label>
        <div class="wrange"><input class="range" type="range" id="w-${TS.esc(id)}" data-k="${TS.esc(id)}" min="-5" max="5" step="1" value="${v}" aria-describedby="w-${TS.esc(id)}-h">
          ${d == null ? "" : `<span class="notch" style="--d:${(d + 5) / 10}" aria-hidden="true"></span>`}</div>
        <output class="wval" for="w-${TS.esc(id)}"></output>
        <span class="wdef">${d == null ? "" : `기본 <span class="mono">${Profile.sign(d)}</span>`}</span>
        <p class="whelp" id="w-${TS.esc(id)}-h" hidden>${TS.ic("mute")}<span><b>받지 않음</b> · −5면 이 주제 카드는 보내지 않아요</span></p></div>`;
    }).join("");
    box.querySelectorAll("input.range").forEach((range) => {
      Profile.paint(range);
      range.oninput = () => { Profile.paint(range); onChange && onChange(range.dataset.k, Number(range.value)); };
    });
  },
  readTopics(box) {
    const out = {};
    box.querySelectorAll("input.range").forEach((r) => { out[r.dataset.k] = Number(r.value); });
    return out;
  },

  // 쓰는 도구 태그 입력: Enter나 쉼표로 넣고, 한 개 30자·15개까지. get()은 배열
  tags({ box, list, input, counter, error }, initial, onChange) {
    let tags = [];
    const MAX = 15, LEN = 30;
    const say = (text) => { error.textContent = text; error.hidden = !text; box.setAttribute("aria-invalid", String(!!text)); };
    const draw = () => {
      list.innerHTML = tags.map((t, i) => `<li class="tagchip"><span class="tn">${TS.esc(t)}</span><button type="button" data-i="${i}" aria-label="${TS.esc(t)} 빼기">${TS.ic("close", "ic-12")}</button></li>`).join("");
      counter.textContent = `${tags.length}/${MAX}`;
      list.querySelectorAll("button").forEach((b) => { b.onclick = () => { tags.splice(Number(b.dataset.i), 1); say(""); draw(); onChange && onChange(); input.focus(); }; });
    };
    const add = (raw) => {
      for (const part of raw.split(",")) {
        const t = part.trim();
        if (!t) continue;
        if (t.length > LEN) { say(`도구 이름은 ${LEN}자까지 넣을 수 있어요`); return false; }
        if (tags.some((x) => x.toLowerCase() === t.toLowerCase())) continue;
        if (tags.length >= MAX) { say(`도구는 ${MAX}개까지 넣을 수 있어요`); return false; }
        tags.push(t);
      }
      say("");
      return true;
    };
    const commit = () => { if (input.value.trim() && add(input.value)) { input.value = ""; draw(); onChange && onChange(); } };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); }
      else if (e.key === "Backspace" && !input.value && tags.length) { tags.pop(); say(""); draw(); onChange && onChange(); }
    });
    input.addEventListener("blur", commit);
    box.addEventListener("click", (e) => { if (e.target === box) input.focus(); });
    tags = []; add((initial || []).join(",")); draw();
    return { get: () => { commit(); return tags.slice(); }, set: (list2) => { tags = []; add((list2 || []).join(",")); draw(); } };
  },
};
