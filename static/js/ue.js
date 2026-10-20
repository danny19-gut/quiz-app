(() => {
  const form = $("#ue-form");
  const errorBox = $("#ue-error");
  const STEPS = [
    "Analyse de l'UE…",
    "Rédaction des questions de niveau moyen…",
    "Rédaction des questions difficiles…",
    "Rédaction des questions extrêmement difficiles…",
    "Vérification des réponses et des corrections…",
  ];

  function fmtDate(ts) {
    return new Date(ts * 1000).toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  async function load() {
    const me = await api("/api/me");
    const list = $("#history");
    if (me.quizzes.length) {
      list.textContent = "";
      me.quizzes.forEach((q) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = q.status === "termine" ? `/resultat/${q.id}` : `/quiz/${q.id}`;
        const left = document.createElement("span");
        const title = document.createElement("strong");
        title.textContent = q.ue;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = fmtDate(q.created_at);
        left.append(title, meta);
        const pill = document.createElement("span");
        pill.className = "pill" + (q.status === "termine" ? "" : " run");
        pill.textContent = q.status === "termine" ? `${q.score} / ${q.total}` : "Reprendre";
        a.append(left, pill);
        li.appendChild(a);
        list.appendChild(li);
      });
    }
    const seen = new Map();
    me.quizzes.forEach((q) => { if (q.code && !seen.has(q.ue)) seen.set(q.ue, q); });
    const chips = $("#chips");
    if (seen.size) {
      chips.hidden = false;
      [...seen.values()].slice(0, 5).forEach((q) => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = q.code;
        b.title = q.titre;
        b.addEventListener("click", () => {
          $("#code").value = q.code;
          $("#titre").value = q.titre;
          $("#chapitres").value = q.chapitres;
        });
        chips.appendChild(b);
      });
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.hidden = true;
    const btn = $("#go");
    btn.disabled = true;
    $("#overlay").hidden = false;
    let step = 0;
    const timer = setInterval(() => {
      step = Math.min(step + 1, STEPS.length - 1);
      $("#overlay-step").textContent = STEPS[step];
    }, 9000);
    try {
      const { id } = await api("/api/quiz", {
        method: "POST",
        body: { code: $("#code").value, titre: $("#titre").value, chapitres: $("#chapitres").value },
      });
      location.href = `/quiz/${id}`;
    } catch (err) {
      clearInterval(timer);
      $("#overlay").hidden = true;
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      btn.disabled = false;
    }
  });

  load().catch((err) => toast(err.message, "error"));
})();
