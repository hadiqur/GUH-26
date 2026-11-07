import { api, formatPhone, setFieldError } from "./common.js";

const $ = (id) => document.getElementById(id);
const steps = { phone: $("step-phone"), details: $("step-details"), code: $("step-code") };
const formError = $("form-error");
const inputs = {
  phone: [$("phone"), $("phone-error")],
  name: [$("name"), $("name-error")],
  code: [$("code"), $("code-error")],
};

let phone = "";
let details = null; // {name, preferred_service} for new users

function show(step) {
  for (const [key, node] of Object.entries(steps)) node.hidden = key !== step;
  const first = steps[step].querySelector("input:not([disabled])");
  first?.focus();
}

function clearErrors() {
  formError.textContent = "";
  for (const [input, err] of Object.values(inputs)) setFieldError(input, err, "");
}

function showError(err, fallbackField) {
  const field = inputs[err.field] ? err.field : fallbackField;
  if (field && inputs[field] && !inputs[field][0].closest("form").hidden) {
    setFieldError(inputs[field][0], inputs[field][1], err.message);
    inputs[field][0].focus();
  } else {
    formError.textContent = err.message;
    formError.focus();
  }
}

async function busy(form, fn) {
  const btn = form.querySelector('button[type="submit"]');
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Please wait…";
  try { await fn(); } finally { btn.disabled = false; btn.textContent = label; }
}

async function requestCode() {
  const body = { phone, ...(details || {}) };
  const res = await api("/api/auth/request-code", { method: "POST", body, redirectOn401: false });
  if (res.status === "needs_details") {
    $("details-phone").textContent = formatPhone(phone) || phone;
    show("details");
    return;
  }
  $("code-phone").textContent = formatPhone(phone) || phone;
  $("code").value = "";
  show("code");
}

steps.phone.addEventListener("submit", (e) => {
  e.preventDefault();
  clearErrors();
  phone = $("phone").value.trim();
  details = null;
  if (!phone) return showError({ message: "Please enter your mobile number.", field: "phone" });
  busy(steps.phone, () => requestCode().catch((err) => showError(err, "phone")));
});

steps.details.addEventListener("submit", (e) => {
  e.preventDefault();
  clearErrors();
  const name = $("name").value.trim();
  if (!name) return showError({ message: "Please enter your name.", field: "name" });
  const service = steps.details.querySelector('input[name="preferred_service"]:checked')?.value || "sms";
  details = { name, preferred_service: service };
  busy(steps.details, () => requestCode().catch((err) => showError(err, "name")));
});

steps.code.addEventListener("submit", (e) => {
  e.preventDefault();
  clearErrors();
  const code = $("code").value.replace(/\s/g, "");
  if (!/^\d{6}$/.test(code)) return showError({ message: "Please enter the 6 digits from the text.", field: "code" });
  busy(steps.code, async () => {
    try {
      await api("/api/auth/verify", { method: "POST", body: { phone, code }, redirectOn401: false });
      location.href = "/account";
    } catch (err) {
      showError(err, "code");
    }
  });
});

$("resend").addEventListener("click", async () => {
  clearErrors();
  try {
    await requestCode();
    formError.className = "alert alert-ok";
    formError.textContent = "We've sent a new code.";
    setTimeout(() => { formError.className = "alert alert-error"; }, 4000);
  } catch (err) {
    showError(err);
  }
});

for (const btn of document.querySelectorAll('[data-action="change-number"]')) {
  btn.addEventListener("click", () => { clearErrors(); show("phone"); });
}

$("demo-btn").addEventListener("click", async () => {
  clearErrors();
  try {
    await api("/api/auth/demo", { method: "POST", redirectOn401: false });
    location.href = "/account";
  } catch (err) {
    showError(err);
  }
});

api("/api/auth/config", { redirectOn401: false })
  .then((cfg) => {
    $("demo-card").hidden = !cfg.demo_mode;
    $("demo-code-hint").hidden = !cfg.demo_mode;
  })
  .catch(() => {});

$("phone").focus();
