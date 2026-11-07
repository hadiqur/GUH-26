// Messages tab: flat log of every text, newest first, paginated.
import { api, el, emptyState, errorState, loadingState, partsNote, statusBadge, timeEl } from "./common.js";
import { personName, viewHeading } from "./render.js";

const PAGE_SIZE = 25;

function logRow(msg) {
  const out = msg.direction === "out";
  return el("tr", {}, [
    el("td", { class: "nowrap", attrs: { "data-label": "When" } }, [timeEl(msg.created_at)]),
    el("td", { attrs: { "data-label": "Who" } }, [
      el("strong", { text: personName(msg) }),
      !msg.contact_id ? el("div", {}, [el("span", { class: "badge badge-unknown", text: "Not saved" })]) : null,
    ]),
    el("td", { class: "nowrap", attrs: { "data-label": "Direction" }, text: out ? "You sent" : "Reply" }),
    el("td", { class: "text-cell", attrs: { "data-label": "Message" } }, [
      el("div", { text: msg.text }),
      partsNote(msg),
    ]),
    el("td", { attrs: { "data-label": "Status" } }, [out ? statusBadge(msg.status) : el("span", { class: "muted", text: "Received" })]),
  ]);
}

export async function render(root, params) {
  const contactId = params.get("contact");
  const filters = new URLSearchParams();
  if (contactId) filters.set("contact_id", contactId);

  const cursors = [null]; // cursor for each page we've visited
  let page = 0;

  const results = el("div", {}, [loadingState("Loading messages…")]);
  const head = [viewHeading("Messages", "messages-title")];
  if (contactId) {
    const label = el("span", { text: "Showing messages with one person." });
    head.push(el("div", { class: "alert" }, [label, " ", el("a", { href: "#messages", text: "Show everyone" })]));
    api(`/api/contacts/${encodeURIComponent(contactId)}`)
      .then((c) => { label.textContent = `Showing messages with ${c.name}.`; })
      .catch(() => { label.textContent = "That contact couldn't be found."; });
  }
  root.replaceChildren(...head, results);

  async function load() {
    results.replaceChildren(loadingState("Loading messages…"));
    const q = new URLSearchParams(filters);
    q.set("limit", String(PAGE_SIZE));
    if (cursors[page]) q.set("cursor", cursors[page]);
    let data;
    try {
      data = await api(`/api/messages?${q}`);
    } catch (err) {
      results.replaceChildren(errorState(err.message, load));
      return;
    }
    if (!data.items.length) {
      results.replaceChildren(emptyState("No messages here yet", "Texts you send by phone, and the replies you get, will appear here."));
      return;
    }
    cursors[page + 1] = data.next_cursor;
    const start = page * PAGE_SIZE + 1;
    const end = start + data.items.length - 1;

    const table = el("table", { class: "log" }, [
      el("caption", { class: "visually-hidden", text: "Your messages, newest first" }),
      el("thead", {}, [el("tr", {}, ["When", "Who", "Direction", "Message", "Status"].map((h) => el("th", { attrs: { scope: "col" }, text: h })))]),
      el("tbody", {}, data.items.map(logRow)),
    ]);
    const newer = el("button", { class: "btn btn-secondary", type: "button", text: "← Newer", disabled: page === 0 });
    const older = el("button", { class: "btn btn-secondary", type: "button", text: "Older →", disabled: !data.next_cursor });
    newer.addEventListener("click", () => { page -= 1; load(); });
    older.addEventListener("click", () => { page += 1; load(); });

    results.replaceChildren(
      el("div", { class: "table-wrap" }, [table]),
      el("div", { class: "pager" }, [
        el("p", { class: "muted", attrs: { "aria-live": "polite" }, text: `Showing ${start}–${end} of ${data.total}` }),
        el("div", { class: "btn-row" }, [newer, older]),
      ]),
    );
  }

  await load();
}
