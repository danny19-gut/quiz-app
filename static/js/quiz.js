(() => {
  const QID = document.body.dataset.quizId;
  const $q = {
    briefing: $("#briefing"), question: $("#question"), strip: $("#strip"),
    count: $("#q-count"), level: $("#q-level"), timer: $("#timer"), timerText: $("#timer-text"),
    bar: $("#bar-fill"), text: $("#q-text"), opts: $("#opts"), saved: $("#saved"),
  };
  let state = null, deadline = 0, raf = 0, busy = false, shownIndex = -1;

  const fmt = (s) => { s = Math.ceil(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      state = await api(`/api/quiz/${QID}/state`);
      render();
    } catch (err) {
      toast(err.message, "error");
      setTimeout(refresh, 2000);
    } finally { busy = false; }
  }

  function paintStrip() {
    const now = state.status === "en_cours" ? state.index : -1;
    buildStrip($q.strip, state.plan, (lvl, i) =>
      lvl + (state.status === "pret" ? "" : i < now ? " done" : i === now ? " now" : ""));
  }

  function render() {
    cancelAnimationFrame(raf);
    if (state.status === "termine") { location.replace(`/resultat/${QID}`); return; }
    paintStrip();
    if (state.status === "pret") {
      $q.question.hidden = true;
      $q.briefing.hidden = false;
      $("#b-title").textContent = `QCM « ${state.ue} » prêt`;
      return;
    }
    $q.briefing.hidden = true;
    $q.question.hidden = false;
    if (state.index !== shownIndex) paintQuestion();
    markChosen();
    deadline = performance.now() + Math.max(state.remaining, 0.25) * 1000;
    raf = requestAnimationFrame(tick);
  }

  function paintQuestion() {
    shownIndex = state.index;
    $q.question.dataset.level = state.difficulte;
    $q.count.textContent = `Question ${state.index + 1} / ${state.total}`;
    $q.level.textContent = LEVEL_LABELS[state.difficulte];
    richText($q.text, state.enonce);
    $q.opts.textContent = "";
    state.options.forEach((label, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "opt";
      b.setAttribute("role", "radio");
      const key = document.createElement("span");
      key.className = "key";
      key.textContent = LETTERS[i];
      const txt = document.createElement("span");
      richText(txt, label);
      b.append(key, txt);
      b.addEventListener("click", () => choose(i));
      $q.opts.appendChild(b);
    });
    $q.saved.textContent = "Choisissez une réponse (touches A à D du clavier).";
  }

  function markChosen() {
    [...$q.opts.children].forEach((b, i) => {
      const on = state.chosen === i;
      b.classList.toggle("sel", on);
      b.setAttribute("aria-checked", on);
    });
    if (state.chosen !== null && state.chosen !== undefined) {
      $q.saved.textContent = "Réponse enregistrée. Vous pouvez la modifier jusqu'à la fin du temps.";
    }
  }

  function tick() {
    const left = (deadline - performance.now()) / 1000;
    if (left <= 0) { paintTimer(0); refresh(); return; }
    paintTimer(left);
    raf = requestAnimationFrame(tick);
  }

  function paintTimer(left) {
    $q.timerText.textContent = fmt(left);
    $q.bar.style.transform = `scaleX(${Math.min(1, left / state.duree)})`;
    $q.timer.classList.toggle("low", left <= Math.min(10, state.duree * 0.2));
  }

  async function choose(i) {
    if (!state || state.status !== "en_cours") return;
    state.chosen = i;
    markChosen();
    try {
      await api(`/api/quiz/${QID}/select`, { method: "POST", body: { index: state.index, choice: i } });
    } catch (err) {
      if (err.status === 409) refresh(); else toast(err.message, "error");
    }
  }

  document.addEventListener("keydown", (e) => {
    const i = LETTERS.indexOf(e.key.toUpperCase());
    if (i >= 0 && !$q.question.hidden && e.key.length === 1) choose(i);
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && state) refresh(); });

  $("#begin").addEventListener("click", async () => {
    $("#begin").disabled = true;
    try {
      state = await api(`/api/quiz/${QID}/start`, { method: "POST" });
      render();
    } catch (err) {
      toast(err.message, "error");
      $("#begin").disabled = false;
    }
  });

  refresh();
})();
