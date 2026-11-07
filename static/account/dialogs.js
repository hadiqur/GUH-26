// Modal dialogs: confirm, and the add/edit contact form.
import { api, el, setFieldError } from "./common.js";

function openDialog(content, labelId) {
  const dialog = el("dialog", { attrs: { "aria-labelledby": labelId } }, [el("div", { class: "dialog-body" }, content)]);
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.showModal();
  return dialog;
}

/** Resolves true if confirmed. */
export function confirmDialog({ title, body, confirmLabel = "Yes", danger = false }) {
  return new Promise((resolve) => {
    let result = false;
    const cancel = el("button", { class: "btn btn-secondary", type: "button", text: "Cancel" });
    const ok = el("button", { class: `btn ${danger ? "btn-danger" : ""}`, type: "button", text: confirmLabel });
    const dialog = openDialog(
      [el("h2", { text: title, attrs: { id: "confirm-title" } }), el("p", { text: body }), el("div", { class: "btn-row" }, [ok, cancel])],
      "confirm-title",
    );
    cancel.addEventListener("click", () => dialog.close());
    ok.addEventListener("click", () => { result = true; dialog.close(); });
    dialog.addEventListener("close", () => resolve(result));
    cancel.focus();
  });
}

/**
 * Add or edit a contact.
 * contact: existing contact to edit, or null. prefill: {name, phone} for new.
 * Resolves with the saved contact, or null if cancelled.
 */
export function openContactForm({ contact = null, prefill = {} } = {}) {
  return new Promise((resolve) => {
    let saved = null;
    let aliases = [...(contact?.aliases || [])];
    const editing = Boolean(contact);

    const field = (id, label, input, hint, control = input) => {
      const error = el("span", { class: "field-error", attrs: { id: `${id}-error` } });
      input.id = id;
      input.setAttribute("aria-describedby", [hint ? `${id}-hint` : null, `${id}-error`].filter(Boolean).join(" "));
      return {
        node: el("div", { class: "field" }, [el("label", { attrs: { for: id }, text: label }), hint ? el("span", { class: "hint", attrs: { id: `${id}-hint` }, text: hint }) : null, control, error]),
        input,
        error,
      };
    };

    const name = field("cf-name", "Name", el("input", { type: "text", autocomplete: "off", value: contact?.name || prefill.name || "" }),
      "What you call them, e.g. Mum or Sarah (Work)");
    const phone = field("cf-phone", "Mobile number", el("input", { type: "tel", inputMode: "tel", autocomplete: "off", value: contact?.phone || prefill.phone || "" }),
      "For example, 07700 900123");

    // Aliases as tags
    const tagList = el("ul", { class: "tags", attrs: { "aria-label": "Other names" } });
    const aliasInput = el("input", { type: "text", autocomplete: "off" });
    const addAliasBtn = el("button", { class: "btn btn-secondary", type: "button", text: "Add" });
    const alias = field("cf-alias", "Other names (optional)", aliasInput,
      "Other names you might say on the phone, like Mom or Mam. Press Enter after each.",
      el("div", { class: "tag-input-row" }, [aliasInput, addAliasBtn]));
    alias.node.append(tagList);

    const renderTags = () => {
      tagList.replaceChildren(...aliases.map((a, i) => el("li", { class: "tag" }, [
        el("span", { text: a }),
        el("button", {
          type: "button", text: "×",
          attrs: { "aria-label": `Remove ${a}` },
          on: { click: () => { aliases.splice(i, 1); renderTags(); aliasInput.focus(); } },
        }),
      ])));
    };
    const addAlias = () => {
      const parts = aliasInput.value.split(",").map((s) => s.trim()).filter(Boolean);
      for (const p of parts) if (!aliases.some((a) => a.toLowerCase() === p.toLowerCase())) aliases.push(p);
      aliasInput.value = "";
      renderTags();
    };
    aliasInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addAlias(); }
    });
    addAliasBtn.addEventListener("click", () => { addAlias(); aliasInput.focus(); });
    renderTags();

    const formError = el("div", { class: "alert alert-error", attrs: { role: "alert" } });
    const save = el("button", { class: "btn", type: "submit", text: editing ? "Save changes" : "Save contact" });
    const cancel = el("button", { class: "btn btn-secondary", type: "button", text: "Cancel" });
    const title = el("h2", { attrs: { id: "cf-title" }, text: editing ? `Edit ${contact.name}` : "Add a contact" });
    const form = el("form", { attrs: { novalidate: true } }, [title, formError, name.node, phone.node, alias.node, el("div", { class: "btn-row" }, [save, cancel])]);
    const dialog = openDialog([form], "cf-title");

    const fields = { name, phone, aliases: alias };
    cancel.addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (aliasInput.value.trim()) addAlias();
      formError.textContent = "";
      for (const f of Object.values(fields)) setFieldError(f.input, f.error, "");
      const body = { name: name.input.value.trim(), phone: phone.input.value.trim(), aliases };
      if (!body.name) { setFieldError(name.input, name.error, "Please enter a name."); name.input.focus(); return; }
      if (!body.phone) { setFieldError(phone.input, phone.error, "Please enter their mobile number."); phone.input.focus(); return; }
      save.disabled = true;
      try {
        saved = editing
          ? await api(`/api/contacts/${contact.id}`, { method: "PATCH", body })
          : await api("/api/contacts", { method: "POST", body });
        dialog.close();
      } catch (err) {
        const f = fields[err.field];
        if (f) { setFieldError(f.input, f.error, err.message); f.input.focus(); }
        else formError.textContent = err.message;
      } finally {
        save.disabled = false;
      }
    });
    dialog.addEventListener("close", () => resolve(saved));
    name.input.focus();
  });
}
