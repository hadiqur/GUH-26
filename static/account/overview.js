// Overview tab: greeting, your details, recent messages.
import { api, el, emptyState, errorState, formatDay, formatPhone, loadingState, londonHour } from "./common.js";
import { state } from "./state.js";
import { messageItem, viewHeading } from "./render.js";

const SERVICES = { sms: "SMS text message", whatsapp: "WhatsApp" };

function greeting() {
  const h = londonHour();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function detailsCard(me) {
  const row = (label, value) => [el("dt", { text: label }), el("dd", { text: value })];
  return el("div", { class: "card" }, [
    el("h2", { text: "Your details" }),
    el("dl", { class: "details" }, [
      ...row("Name", me.name || "Not set"),
      ...row("Phone", formatPhone(me.phone)),
      ...row("Texts sent by", SERVICES[me.preferred_service] || me.preferred_service),
      ...row("Member since", me.created_at ? formatDay(me.created_at) : "Today"),
    ]),
  ]);
}

async function recentCard() {
  const body = el("div", {}, [loadingState("Loading messages…")]);
  const card = el("div", { class: "card" }, [
    el("div", { class: "section-head" }, [el("h2", { text: "Latest messages" }), el("a", { href: "#messages", text: "See all messages" })]),
    body,
  ]);
  const load = async () => {
    body.replaceChildren(loadingState("Loading messages…"));
    try {
      const { items } = await api("/api/messages?limit=5");
      body.replaceChildren(items.length
        ? el("ul", { class: "msg-list" }, items.map(messageItem))
        : emptyState("No messages yet", "Call the number at the top of the page and say who to text."));
    } catch (err) {
      body.replaceChildren(errorState(err.message, load));
    }
  };
  load();
  return card;
}

export async function render(root) {
  const me = state.me;
  root.replaceChildren(
    viewHeading(`${greeting()}${me.name ? `, ${me.name}` : ""}`, "overview-title"),
    el("p", { class: "muted", text: "Here's what's been happening with your texts." }),
    el("div", { class: "grid grid-2" }, [detailsCard(me), await recentCard()]),
  );
}
