// Contacts tab: search, add, edit, delete.
import { api, debounce, el, emptyState, errorState, formatPhone, loadingState, timeEl, toast } from "./common.js";
import { confirmDialog, openContactForm } from "./dialogs.js";
import { viewHeading } from "./render.js";

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function contactCard(c, { onEdit, onDelete }) {
  return el("li", { class: "card contact-card" }, [
    el("div", { class: "name-row" }, [
      el("a", { class: "name", href: `#messages?contact=${c.id}`, text: c.name, attrs: { "aria-label": `${c.name}: view messages` } }),
      c.opted_out ? el("span", { class: "badge badge-optout", text: "Opted out", attrs: { title: "This person replied STOP, so Dial-a-Text won't text them." } }) : null,
    ]),
    el("div", { class: "phone", text: formatPhone(c.phone) }),
    c.aliases.length
      ? el("ul", { class: "tags", attrs: { "aria-label": `Other names for ${c.name}` } }, c.aliases.map((a) => el("li", { class: "tag", text: a })))
      : null,
    el("div", { class: "counts" }, [
      `${plural(c.sent_count, "text", "texts")} sent · ${plural(c.received_count, "reply", "replies")}`,
      el("br"),
      "Last message: ",
      timeEl(c.last_activity),
    ]),
    el("div", { class: "btn-row" }, [
      el("button", { class: "btn btn-secondary btn-small", type: "button", text: "Edit", attrs: { "aria-label": `Edit ${c.name}` }, on: { click: onEdit } }),
      el("button", { class: "btn btn-ghost btn-small", type: "button", text: "Delete", attrs: { "aria-label": `Delete ${c.name}` }, on: { click: onDelete } }),
    ]),
  ]);
}

export async function render(root) {
  const search = el("input", { type: "search", id: "contact-search", autocomplete: "off", attrs: { "aria-describedby": "contact-search-hint" } });
  const addBtn = el("button", { class: "btn", type: "button", text: "+ Add contact" });
  const list = el("div", { attrs: { "aria-live": "polite", "aria-busy": "false" } });

  root.replaceChildren(
    el("div", { class: "section-head" }, [viewHeading("Contacts", "contacts-title"), addBtn]),
    el("p", { class: "muted", text: "These are the people you can text by saying their name on the phone." }),
    el("div", { class: "field" }, [
      el("label", { attrs: { for: "contact-search" }, text: "Search contacts" }),
      el("span", { class: "hint", attrs: { id: "contact-search-hint" }, text: "Search by name, other name or number" }),
      search,
    ]),
    list,
  );

  async function load() {
    const q = search.value.trim();
    list.setAttribute("aria-busy", "true");
    if (!list.firstChild) list.replaceChildren(loadingState("Loading contacts…"));
    let items;
    try {
      ({ items } = await api(`/api/contacts${q ? `?q=${encodeURIComponent(q)}` : ""}`));
    } catch (err) {
      list.replaceChildren(errorState(err.message, load));
      return;
    } finally {
      list.setAttribute("aria-busy", "false");
    }
    if (!items.length) {
      list.replaceChildren(q
        ? emptyState(`No contacts match "${q}"`, "Try a different name or number.")
        : emptyState("No contacts yet", "Add the people you text most, like Mum or a friend."));
      return;
    }
    list.replaceChildren(
      el("p", { class: "muted", text: q ? `${plural(items.length, "contact", "contacts")} found` : plural(items.length, "contact", "contacts") }),
      el("ul", { class: "contact-list" }, items.map((c) => contactCard(c, {
        onEdit: async () => {
          const saved = await openContactForm({ contact: c });
          if (saved) { toast(`Saved ${saved.name}`); load(); }
        },
        onDelete: async () => {
          const ok = await confirmDialog({
            title: `Delete ${c.name}?`,
            body: `${c.name} will be removed from your contacts. Your messages with them will be kept.`,
            confirmLabel: "Delete contact",
            danger: true,
          });
          if (!ok) return;
          try {
            await api(`/api/contacts/${c.id}`, { method: "DELETE" });
            toast(`Deleted ${c.name}`);
            load();
          } catch (err) {
            toast(err.message);
          }
        },
      }))),
    );
  }

  addBtn.addEventListener("click", async () => {
    const saved = await openContactForm();
    if (saved) { toast(`Added ${saved.name}`); load(); }
  });
  search.addEventListener("input", debounce(load, 250));
  await load();
}
