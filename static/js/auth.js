(() => {
  let mode = "register";
  const form = $("#auth-form");
  const tabs = document.querySelectorAll("[data-mode]");
  const errorBox = $("#auth-error");

  function setMode(next) {
    mode = next;
    tabs.forEach((t) => {
      const on = t.dataset.mode === next;
      t.classList.toggle("on", on);
      t.setAttribute("aria-selected", on);
    });
    $("#submit").textContent = next === "register" ? "Créer mon compte" : "Me connecter";
    $("#auth-hint").textContent = next === "register"
      ? "Votre matricule est unique : il sert à retrouver vos QCM."
      : "Saisissez exactement les mêmes informations qu'à l'inscription.";
    errorBox.hidden = true;
  }
  tabs.forEach((t) => t.addEventListener("click", () => setMode(t.dataset.mode)));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;
    const btn = $("#submit");
    btn.disabled = true;
    try {
      await api("/api/" + mode, { method: "POST", body: Object.fromEntries(new FormData(form)) });
      location.href = "/ue";
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      btn.disabled = false;
    }
  });
})();
