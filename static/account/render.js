// Renderers shared by several views. Text only via textContent (through el()).
import { el, formatPhone, partsNote, statusBadge, timeEl } from "./common.js";

/** Display name for the other person in a message. */
export function personName(msg) {
  return msg.contact_name || formatPhone(msg.other_number);
}

/** Heading level elements need focusable headings for route focus. */
export function viewHeading(text, id) {
  return el("h1", { text, attrs: { id, tabindex: "-1" } });
}

/** One row in a compact message list (Overview). */
export function messageItem(msg) {
  const out = msg.direction === "out";
  const who = el("div", { class: "msg-who" }, [
    el("span", { class: "visually-hidden", text: out ? "You texted" : "Reply from" }),
    el("span", { text: personName(msg) }),
    !msg.contact_id ? el("span", { class: "badge badge-unknown", text: "Not saved" }) : null,
    !out && !msg.is_read ? el("span", { class: "badge badge-new", text: "New" }) : null,
  ]);
  return el("li", { class: "msg-item" }, [
    el("span", {
      class: `dir-icon ${out ? "dir-out" : "dir-in"}`,
      attrs: { "aria-hidden": "true", title: out ? "You sent" : "Reply" },
      text: out ? "↗" : "↙",
    }),
    el("div", {}, [who, el("div", { class: "msg-text", text: msg.text })]),
    el("div", { class: "msg-meta" }, [timeEl(msg.created_at), out ? statusBadge(msg.status) : null, partsNote(msg)]),
  ]);
}
