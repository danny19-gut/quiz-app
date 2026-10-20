(() => {
  const QID = document.body.dataset.quizId;

  function renderCorrection(items) {
    const list = $("#corr-list");
    list.textContent = "";
    items.forEach((it) => {
      const li = document.createElement("li");
      li.className = it.etat;
      li.dataset.etat = it.etat;

      const head = document.createElement("div");
      head.className = "head";
      const left = document.createElement("span");
      left.textContent = `Question ${it.position + 1} · ${LEVEL_LABELS[it.difficulte]}`;
      const right = document.createElement("strong");
      right.textContent = it.etat === "ok" ? "Trouvée" : it.etat === "ko" ? "Ratée" : "Sans réponse";
      head.append(left, right);

      const q = document.createElement("div");
      q.className = "q";
      richText(q, it.enonce);

      const ul = document.createElement("ul");
      it.options.forEach((opt, i) => {
        const o = document.createElement("li");
        const label = document.createElement("span");
        richText(label, `${LETTERS[i]}. ${opt}`);
        o.appendChild(label);
        if (i === it.correct) {
          o.classList.add("right");
          const t = document.createElement("span");
          t.className = "tag";
          t.textContent = "Bonne réponse";
          o.appendChild(t);
        } else if (i === it.chosen) {
          o.classList.add("wrong");
          const t = document.createElement("span");
          t.className = "tag";
          t.textContent = "Votre réponse";
          o.appendChild(t);
        }
        ul.appendChild(o);
      });

      const expl = document.createElement("p");
      expl.className = "expl";
      richText(expl, it.explication || "");

      li.append(head, q, ul);
      if (it.explication) li.appendChild(expl);
      list.appendChild(li);
    });
  }

  async function load() {
    let r;
    try {
      r = await api(`/api/quiz/${QID}/result`);
    } catch (err) {
      if (err.status === 409) { location.replace(`/quiz/${QID}`); return; }
      toast(err.message, "error");
      return;
    }
    $("#r-ue").textContent = `UE ${r.ue}`;
    $("#r-score").textContent = r.bonnes;
    $("#r-total").textContent = `/ ${r.total}`;
    $("#r-ok").textContent = r.bonnes;
    $("#r-ko").textContent = r.fausses;
    $("#r-none").textContent = r.sans_reponse;
    buildStrip($("#r-strip"), r.items.map((i) => i.etat), (etat) => etat);
    renderCorrection(r.items);
    $("#summary").hidden = false;

    $("#show-corr").addEventListener("click", () => {
      $("#correction").hidden = false;
      $("#correction").scrollIntoView({ behavior: "smooth" });
    });
    document.querySelectorAll(".filters button").forEach((b) => {
      b.addEventListener("click", () => {
        document.querySelectorAll(".filters button").forEach((x) => x.classList.toggle("on", x === b));
        document.querySelectorAll("#corr-list > li").forEach((li) => {
          const f = b.dataset.f;
          li.hidden = f !== "all" && (f === "ok" ? li.dataset.etat !== "ok" : li.dataset.etat === "ok");
        });
      });
    });
  }
  load();
})();
