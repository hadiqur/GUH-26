// Shared helpers for the Dial-a-Text account pages.
// Rule: user-supplied text (names, messages) is only ever set via textContent.

/** Build an element. props: {class, text, attrs, on: {event: fn}, ...dom props}. */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "attrs") for (const [a, v] of Object.entries(value)) { if (v !== undefined && v !== null && v !== false) node.setAttribute(a, v === true ? "" : String(v)); }
    else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node[key] = value;
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ---------- API ----------

export class ApiError extends Error {
  constructor(message, status, field) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

function errorMessage(body, status) {
  const d = body && body.detail;
  if (d && typeof d === "object" && !Array.isArray(d) && d.message) return [d.message, d.field];
  if (typeof d === "string") return [d, null];
  if (Array.isArray(d) && d.length) return ["Please check the form and try again.", d[0].loc ? d[0].loc[d[0].loc.length - 1] : null];
  if (status >= 500) return ["Something went wrong on our side. Please try again in a moment.", null];
  return ["Something went wrong. Please try again.", null];
}

export async function api(path, { method = "GET", body, redirectOn401 = true } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach Dial-a-Text. Check your internet connection and try again.", 0, null);
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (res.status === 401 && redirectOn401) {
    location.href = "/account/login";
    throw new ApiError("Please log in.", 401, null);
  }
  if (!res.ok) {
    const [msg, field] = errorMessage(data, res.status);
    throw new ApiError(msg, res.status, field);
  }
  return data;
}

// ---------- Phone numbers ----------

/** "+447700900123" -> "07700 900123" for UK numbers; others unchanged. */
export function formatPhone(e164) {
  if (!e164) return "";
  if (/^\+44\d{10}$/.test(e164)) {
    const national = "0" + e164.slice(3);
    return national.slice(0, 5) + " " + national.slice(5);
  }
  return e164;
}

// ---------- Times (always Europe/London) ----------

const TZ = "Europe/London";
const exactFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});
const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const hourFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });
const ymdFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

export const exactTime = (iso) => exactFmt.format(new Date(iso));
export const formatDay = (iso) => dayFmt.format(new Date(iso));
export const londonHour = () => Number(hourFmt.format(new Date()));
/** YYYY-MM-DD for a date in London. */
export const londonYmd = (d = new Date()) => ymdFmt.format(d);

export function relativeTime(iso) {
  const then = new Date(iso);
  const secs = Math.round((Date.now() - then.getTime()) / 1000);
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24 && londonYmd(then) === londonYmd()) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const yesterday = londonYmd(new Date(Date.now() - 86400000));
  if (londonYmd(then) === yesterday) return `yesterday, ${timeFmt.format(then)}`;
  const days = Math.floor(secs / 86400);
  if (days < 7) return `${days < 2 ? 2 : days} days ago`;
  return shortFmt.format(then);
}

/** <time> element showing "2 min ago" with the exact London time on hover. */
export function timeEl(iso) {
  if (!iso) return el("span", { class: "muted", text: "never" });
  const exact = exactTime(iso);
  return el("time", { attrs: { datetime: iso, title: exact, "aria-label": `${relativeTime(iso)}, ${exact}` }, dataset: { rel: iso }, text: relativeTime(iso) });
}

// Keep relative times fresh.
setInterval(() => {
  for (const t of document.querySelectorAll("time[data-rel]")) {
    const rel = relativeTime(t.dataset.rel);
    if (t.textContent !== rel) {
      t.textContent = rel;
      t.setAttribute("aria-label", `${rel}, ${t.title}`);
    }
  }
}, 30000);

// ---------- Small UI bits ----------

export function statusBadge(status) {
  const labels = { queued: "Queued", sent: "Sent", delivered: "Delivered", failed: "Failed" };
  return el("span", { class: `badge badge-${status}`, text: labels[status] || status });
}

export function partsNote(msg) {
  const bits = [];
  if (msg.parts > 1) bits.push(`${msg.parts} parts`);
  if (msg.encoding === "Unicode") bits.push("Unicode");
  return bits.length ? el("span", { class: "muted small", text: bits.join(", ") }) : null;
}

export function loadingState(text = "Loading…") {
  return el("div", { class: "state", attrs: { role: "status" } }, [el("span", { class: "spinner", attrs: { "aria-hidden": "true" } }), text]);
}

export function emptyState(title, body) {
  return el("div", { class: "state" }, [el("strong", { text: title }), body ? el("span", { text: body }) : null]);
}

export function errorState(message, onRetry) {
  return el("div", { class: "state error", attrs: { role: "alert" } }, [
    el("strong", { text: "Sorry, that didn't load." }),
    el("p", { text: message }),
    onRetry ? el("button", { class: "btn btn-secondary", type: "button", text: "Try again", on: { click: onRetry } }) : null,
  ]);
}

export function toast(message, { action, onAction, timeout = 7000 } = {}) {
  const region = document.getElementById("toasts");
  if (!region) return;
  const node = el("div", { class: "toast" }, [el("span", { text: message })]);
  if (action) node.append(el("button", { type: "button", text: action, on: { click: () => { onAction?.(); node.remove(); } } }));
  region.append(node);
  setTimeout(() => node.remove(), timeout);
}

/** Show a field error under an input and mark it invalid. */
export function setFieldError(input, errorNode, message) {
  if (message) {
    input.setAttribute("aria-invalid", "true");
    errorNode.textContent = message;
  } else {
    input.removeAttribute("aria-invalid");
    errorNode.textContent = "";
  }
}

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
