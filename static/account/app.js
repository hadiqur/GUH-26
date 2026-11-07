// Dial-a-Text account page: header, tab routing (#overview, #messages, ...).
import { api, formatPhone, errorState, loadingState } from "./common.js";
import { state } from "./state.js";
import * as overview from "./overview.js";
import * as messages from "./messages.js";
import * as contacts from "./contacts.js";

const views = { overview, messages, contacts };
const titles = { overview: "Overview", messages: "Messages", contacts: "Contacts", settings: "Settings" };
let firstRoute = true;

function parseHash() {
  const raw = location.hash.slice(1) || "overview";
  const [name, qs] = raw.split("?");
  return { name: views[name] ? name : "overview", params: new URLSearchParams(qs || "") };
}

async function route() {
  const { name, params } = parseHash();
  state.view = name;
  for (const a of document.querySelectorAll(".tabs a")) {
    if (a.dataset.tab === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  for (const section of document.querySelectorAll("main > section")) section.hidden = section.dataset.view !== name;
  document.title = `${titles[name]} · Dial-a-Text`;

  const root = document.getElementById(`view-${name}`);
  try {
    await views[name].render(root, params);
  } catch (err) {
    root.replaceChildren(errorState(err.message, route));
  }
  // Move focus to the new view's heading for keyboard and screen reader users.
  if (!firstRoute) root.querySelector("h1")?.focus({ preventScroll: false });
  firstRoute = false;
}

function renderHeader() {
  const link = document.getElementById("service-number");
  const number = state.me.service_number;
  if (number) {
    link.href = `tel:${number}`;
    link.textContent = formatPhone(number);
  } else {
    link.removeAttribute("href");
    link.textContent = "Number coming soon";
  }
}

document.getElementById("logout").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } finally { location.href = "/account/login"; }
});

window.addEventListener("hashchange", route);

async function start() {
  const main = document.getElementById("view-overview");
  main.hidden = false;
  main.replaceChildren(loadingState("Loading your account…"));
  try {
    state.me = await api("/api/me");
  } catch (err) {
    main.replaceChildren(errorState(err.message, start));
    return;
  }
  renderHeader();
  await route();
}

start();
