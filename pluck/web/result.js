"use strict";

/* Vertorama result window: shows the tall capture and passes the
 * buttons to Python. */

const pending = new Map();
let nextId = 1;
function call(cmd, ...args) {
  const id = nextId++;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    window.webkit.messageHandlers.pluck.postMessage({ id, cmd, args });
  });
}
window.Pluck = {
  resolve(id, result) { const r = pending.get(id); pending.delete(id); if (r) r(result); },
  emit() {},
};

const $ = (s) => document.querySelector(s);

const ICONS = {
  save: '<path d="M12 4v11m0 0-4-4m4 4 4-4"/><path d="M5 19h14"/>',
  pdf: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/>',
  copy: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
  text: '<path d="M5 6h14M5 10h14M5 14h9M5 18h6"/>',
};

function button(label, iconName, onclick, primary = false) {
  const b = document.createElement("button");
  b.className = `btn ${primary ? "primary" : ""}`;
  const t = document.createElement("template");
  t.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[iconName]}</svg>`;
  const span = document.createElement("span");
  span.textContent = label;
  b.append(t.content.firstChild, span);
  b.addEventListener("click", async () => {
    if (b.disabled) return;
    b.disabled = true;
    try { await onclick(span); } finally { b.disabled = false; }
  });
  return b;
}

function status(text, path) {
  const el = $("#status");
  el.replaceChildren(document.createTextNode(text));
  if (path) {
    const a = document.createElement("a");
    a.textContent = "Show in folder";
    a.addEventListener("click", () => call("show", path));
    el.append(a);
  }
  el.hidden = false;
}

const REASONS = {
  end: "",
  stopped: "Stopped when the mouse moved.",
  limit: "Stopped at the size limit.",
  lost: "Stopped where the content jumped and couldn't be matched.",
};

async function busy(span, working, work) {
  const label = span.textContent;
  span.textContent = working;
  try { return await work(); } finally { span.textContent = label; }
}

(async () => {
  const info = await call("ready");
  $("#shot").src = info.url;
  $("#size").textContent = `${info.width.toLocaleString()} × ${info.height.toLocaleString()} px`;
  if (REASONS[info.reason]) status(REASONS[info.reason]);

  $("#actions").append(
    button("Save image", "save", async () => {
      const r = await call("save_image");
      if (r.error) status(r.error); else status(`Saved to ${r.folder}.`, r.path);
    }, true),
    button("Save PDF", "pdf", (span) => busy(span, "Making PDF…", async () => {
      const r = await call("save_pdf");
      if (r.error) status(`Couldn't make the PDF: ${r.error}`);
      else status(`Saved a searchable PDF to ${r.folder}.`, r.path);
    })),
    button("Copy image", "copy", async () => {
      const r = await call("copy_image");
      status(r && r.error ? r.error : "Image copied.");
    }),
    button("Copy text", "text", (span) => busy(span, "Reading…", async () => {
      const r = await call("copy_text");
      if (r.error) status(r.error);
      else status(r.chars ? `Copied ${r.chars.toLocaleString()} characters of text.` : "No text found.");
    })),
  );
})();

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") call("close");
});
