// Utilitaires communs à toutes les pages.
async function api(path, options = {}) {
  const res = await fetch(path, {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* réponse vide */ }
  if (res.status === 401 && !location.pathname.startsWith("/api") && location.pathname !== "/") {
    location.href = "/";
  }
  if (!res.ok) {
    const err = new Error(data.error || "Erreur réseau. Réessayez.");
    err.status = res.status;
    throw err;
  }
  return data;
}

const $ = (sel, root = document) => root.querySelector(sel);

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = message;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

// Écrit un texte en transformant `code` (entre accents graves) en <code>, sans innerHTML.
function richText(el, text) {
  el.textContent = "";
  text.split("`").forEach((part, i) => {
    if (i % 2 && part) {
      const c = document.createElement("code");
      c.textContent = part;
      el.appendChild(c);
    } else {
      el.appendChild(document.createTextNode(part));
    }
  });
}

const LEVEL_LABELS = { moyen: "Moyen", difficile: "Difficile", extreme: "Extrêmement difficile" };
const LETTERS = ["A", "B", "C", "D"];

// Bande de segments : un par question.
function buildStrip(container, plan, classFor) {
  container.textContent = "";
  plan.forEach((level, i) => {
    const s = document.createElement("span");
    s.className = "seg " + classFor(level, i);
    container.appendChild(s);
  });
}

document.addEventListener("click", async (e) => {
  if (e.target.id === "logout") {
    await api("/api/logout", { method: "POST" });
    location.href = "/";
  }
});
