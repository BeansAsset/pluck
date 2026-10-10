"use strict";

/* Pluck overlay. Python freezes the screen, reads text and talks to the
 * desktop; this file draws the selection, the invisible text layer and the
 * action bar. Recognised text is only ever set with textContent. */

// ---- bridge -----------------------------------------------------------------

const pending = new Map();
let nextId = 1;
function call(cmd, ...args) {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    window.webkit.messageHandlers.pluck.postMessage({ id, cmd, args });
  });
}
const on = {};
window.Pluck = {
  resolve(id, result) { const r = pending.get(id); pending.delete(id); if (r) r(result); },
  emit(name, data) { if (on[name]) on[name](data); },
};

// ---- helpers ------------------------------------------------------------------

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const $ = (s) => document.querySelector(s);

const ICONS = {
  copy: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
  phone: '<path d="M6 3.5h3l1.5 4.5-2 1.5a11 11 0 0 0 6 6l1.5-2 4.5 1.5v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5.5a2 2 0 0 1 2-2z"/>',
  tall: '<rect x="6" y="3.5" width="12" height="17" rx="2"/><path d="M9.5 9.5 12 12l2.5-2.5M9.5 14 12 16.5l2.5-2.5"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.5"/>',
};
function icon(name) {
  const t = document.createElement("template");
  t.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  return t.content.firstChild;
}

// ---- state ----------------------------------------------------------------------

let drag = null;          // {x0, y0} while the mouse is down
let region = null;        // {x, y, w, h} of the last selection
let result = null;        // what Python read
let readToken = 0;
let canScroll = false;    // Vertorama needs X11 to scroll other windows

function reset() {
  drag = null; region = null; result = null; readToken++;
  document.body.className = "";
  $("#region").hidden = true;
  $("#words").replaceChildren();
  closeBar();
}

// ---- the frozen screen ---------------------------------------------------------------

function showShot(shot) {
  reset();
  const img = $("#screen");
  img.onload = () => {
    img.style.width = `${shot.width}px`;
    img.style.height = `${shot.height}px`;
    // The image is decoded and in place: Python can show the window now.
    // (Not requestAnimationFrame: a hidden window never gets frames.)
    call("drawn");
  };
  img.onerror = () => console.log("pluck: couldn't load the frozen screen " + shot.url);
  img.src = shot.url;
}
on.shot = showShot;

// ---- selecting -------------------------------------------------------------------------

function setRegion(r) {
  const el = $("#region");
  Object.assign(el.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` });
  el.style.setProperty("--h", `${Math.max(0, r.h - 1)}px`);
  el.hidden = false;
}

document.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || e.target.closest("#bar") || e.target.closest(".line")) return;
  reset();
  drag = { x0: e.clientX, y0: e.clientY };
  document.body.classList.add("selecting");
  setRegion({ x: e.clientX, y: e.clientY, w: 0, h: 0 });
  e.preventDefault();
});

document.addEventListener("mousemove", (e) => {
  if (!drag) return;
  const x = Math.min(drag.x0, e.clientX), y = Math.min(drag.y0, e.clientY);
  setRegion({ x, y, w: Math.abs(e.clientX - drag.x0), h: Math.abs(e.clientY - drag.y0) });
});

document.addEventListener("mouseup", (e) => {
  if (!drag || e.button !== 0) return;
  const r = { x: Math.min(drag.x0, e.clientX), y: Math.min(drag.y0, e.clientY),
              w: Math.abs(e.clientX - drag.x0), h: Math.abs(e.clientY - drag.y0) };
  drag = null;
  if (r.w < 6 || r.h < 6) { reset(); return; }
  read(r);
});

async function read(r) {
  region = r;
  const token = ++readToken;
  document.body.className = "selecting reading";
  const res = await call("read", r.x, r.y, r.w, r.h);
  if (token !== readToken) return;
  document.body.className = "done";
  result = res;
  if (res.error) { showBar([note(res.error), closeButton()]); return; }
  if (!res.text.trim()) {
    showBar([note("No text found here."), canScroll && vertoramaButton(), closeButton()]);
    return;
  }
  layWords(res.lines);
  showBar(actions(res));
}

// ---- the invisible text layer ------------------------------------------------------------

/* Each word is a transparent span stretched to cover the word in the
 * screenshot, so selecting with the mouse highlights the real pixels and
 * copying gives the recognised text, spaces and line breaks included. */
function layWords(lines) {
  const box = $("#words");
  box.replaceChildren();
  for (const line of lines) {
    const words = line.words;
    if (!words.length) continue;
    const top = Math.min(...words.map((w) => w.y));
    const bottom = Math.max(...words.map((w) => w.y + w.h));
    const left = Math.min(...words.map((w) => w.x));
    const height = Math.max(8, bottom - top);
    const div = h("div", { class: "line" });
    Object.assign(div.style, { left: `${left}px`, top: `${top}px`, height: `${height}px` });
    words.forEach((w, i) => {
      const next = words[i + 1];
      const span = h("span", { text: next && w.space ? `${w.text} ` : w.text });
      span.style.fontSize = `${height * 0.86}px`;
      span.style.lineHeight = `${height}px`;
      span.style.position = "absolute";
      span.style.left = `${w.x - left}px`;
      span.style.top = "0px";
      span.dataset.target = String(next ? Math.max(w.w, next.x - w.x) : w.w);
      div.append(span);
    });
    box.append(div);
  }
  for (const span of box.querySelectorAll(".line span")) {
    const natural = span.getBoundingClientRect().width;
    if (natural > 0) span.style.transform = `scaleX(${Number(span.dataset.target) / natural})`;
  }
}

function selectedText() {
  const sel = window.getSelection();
  const text = sel ? sel.toString().trim() : "";
  return text || (result ? result.text : "");
}

// ---- the action bar ------------------------------------------------------------------------

function note(text) { return h("span", { class: "note", text }); }
function closeButton() { return button("Close", null, () => call("close"), false); }
function button(label, iconName, onclick, primary = false, title = null) {
  return h("button", { class: `btn ${primary ? "primary" : ""}`, title, onclick: (e) => { e.stopPropagation(); onclick(); } },
    iconName && icon(iconName), h("span", { text: label }));
}

function vertoramaButton() {
  return button("Vertorama", "tall", startVertorama, false,
    "Scroll this area to the end and capture all of it as one tall image");
}

async function startVertorama() {
  const r = region;
  const res = await call("vertorama", r.x, r.y, r.w, r.h);
  if (res && res.error) showBar([note(res.error), closeButton()]);
}

function actions(res) {
  const items = [button("Copy text", "copy", copyAndClose, true)];
  for (const [kind, value] of res.findings.slice(0, 3)) {
    if (kind === "link") {
      const host = value.replace(/^https?:\/\//, "").replace(/^www\./, "").split(/[/?#]/)[0];
      items.push(button(`Open ${host}`, "link", () => call("open", "link", value), false, value));
    } else if (kind === "email") {
      items.push(button(`Email ${value}`, "mail", () => call("open", "email", value), false, value));
    } else if (kind === "phone") {
      items.push(button(`Copy ${value}`, "phone", () => copyAndClose(value), false, value));
    }
  }
  items.push(button("Search", "search", () => call("open", "search", selectedText().slice(0, 300))));
  items.push(h("span", { class: "sep" }));
  if (canScroll) items.push(vertoramaButton());
  items.push(button("Show text", "eye", toggleShow));
  items.push(button("Edit", "edit", openEditor));
  return items;
}

function toggleShow() {
  document.body.classList.toggle("showtext");
  const on_ = document.body.classList.contains("showtext");
  for (const b of document.querySelectorAll("#bar .btn span")) {
    if (b.textContent === "Show text" || b.textContent === "Hide text") b.textContent = on_ ? "Hide text" : "Show text";
  }
}

async function copyAndClose(text) {
  await call("copy", typeof text === "string" ? text : selectedText());
  const bar = $("#bar");
  bar.replaceChildren(note("Copied"));
  setTimeout(() => call("close"), 450);
}

function openEditor() {
  const area = h("textarea", { spellcheck: "false" });
  area.value = selectedText();
  const bar = $("#bar");
  bar.classList.add("editing");
  bar.replaceChildren(area, h("div", { class: "row" },
    button("Cancel", null, () => { bar.classList.remove("editing"); showBar(actions(result)); }),
    button("Copy", "copy", () => copyAndClose(area.value), true)));
  placeBar();
  area.focus();
}

function showBar(children) {
  const bar = $("#bar");
  bar.classList.remove("editing");
  bar.replaceChildren(...children.filter(Boolean));
  bar.hidden = false;
  placeBar();
}

function closeBar() {
  const bar = $("#bar");
  bar.hidden = true;
  bar.classList.remove("editing");
  bar.replaceChildren();
}

/* Below the selection if there's room, otherwise above it, kept on screen. */
function placeBar() {
  if (!region) return;
  const bar = $("#bar");
  const bw = bar.offsetWidth, bh = bar.offsetHeight, gap = 10;
  let top = region.y + region.h + gap;
  if (top + bh > innerHeight - 12) top = region.y - bh - gap;
  if (top < 12) top = Math.min(innerHeight - bh - 12, region.y + gap);
  const left = Math.min(Math.max(12, region.x), innerWidth - bw - 12);
  Object.assign(bar.style, { left: `${left}px`, top: `${top}px` });
}

// ---- keys -----------------------------------------------------------------------------------

document.addEventListener("keydown", (e) => {
  const editing = $("#bar").classList.contains("editing");
  if (e.key === "Escape") {
    e.preventDefault();
    if (editing) showBar(actions(result)); else call("close");
  } else if (e.key === "Enter" && !editing && result && result.text) {
    e.preventDefault();
    copyAndClose();
  } else if ((e.ctrlKey && e.key.toLowerCase() === "c") && !editing && result && result.text) {
    e.preventDefault();
    copyAndClose();
  }
});

// ---- start ------------------------------------------------------------------------------------

(async () => {
  const first = await call("ready");
  canScroll = Boolean(first && first.vertorama);
  if (first && first.shot) showShot(first.shot);
})();
