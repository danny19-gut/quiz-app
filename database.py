"""Accès à la base SQLite + logique du chronomètre côté serveur.

Principe : le serveur est l'unique source de vérité pour le temps.
Chaque question a une durée ; quand elle est écoulée, la question suivante
démarre automatiquement (même si l'étudiant a fermé l'onglet).
"""
import json
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "qcm.db")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        schema = f.read()
    with connect() as conn:
        conn.executescript(schema)
        # Migration : anciennes bases créées avant l'ajout de code / titre / chapitres
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(quizzes)")}
        for col in ("code", "titre", "chapitres"):
            if col not in cols:
                conn.execute(f"ALTER TABLE quizzes ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


# ---------------------------------------------------------------- étudiants
def normalize(text):
    """Minuscules, sans accents, espaces simplifiés : 'Éric  Dupont' == 'eric dupont'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().casefold()


def create_student(nom, prenom, niveau, matricule):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO students (nom, prenom, niveau, matricule, created_at) VALUES (?,?,?,?,?)",
            (nom, prenom, niveau, matricule, time.time()),
        )
        return cur.lastrowid


def find_student_by_matricule(matricule):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM students WHERE matricule = ?", (matricule,)
        ).fetchone()


def get_student(student_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


# -------------------------------------------------------------------- quiz
def create_quiz(student_id, code, titre, chapitres, questions):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO quizzes (student_id, ue, code, titre, chapitres, created_at) VALUES (?,?,?,?,?,?)",
            (student_id, f"{code} · {titre}", code, titre, chapitres, time.time()),
        )
        quiz_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO questions
               (quiz_id, position, enonce, options, correct, explication, difficulte, duree)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (quiz_id, i, q["enonce"], json.dumps(q["options"], ensure_ascii=False),
                 q["correct"], q["explication"], q["difficulte"], q["duree"])
                for i, q in enumerate(questions)
            ],
        )
        return quiz_id


def get_quiz(quiz_id):
    with connect() as conn:
        return conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()


def previous_enonces(student_id, ue, limit=60):
    """Énoncés déjà posés à cet étudiant sur cette UE (pour que la nouvelle vague soit différente)."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT q.enonce, z.ue FROM questions q
               JOIN quizzes z ON z.id = q.quiz_id
               WHERE z.student_id = ? ORDER BY q.id DESC LIMIT 400""",
            (student_id,),
        ).fetchall()
    target = normalize(ue)
    return [r["enonce"] for r in rows if normalize(r["ue"]) == target][:limit]


def _sync(conn, quiz_id):
    """Fait avancer le quiz selon l'horloge : toute question dont le temps est écoulé est passée."""
    quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None or quiz["status"] != "en_cours" or quiz["question_started_at"] is None:
        return quiz
    durees = [r["duree"] for r in conn.execute(
        "SELECT duree FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,))]
    idx, started, now = quiz["current_index"], quiz["question_started_at"], time.time()
    while idx < len(durees) and now >= started + durees[idx]:
        started += durees[idx]  # la suivante démarre pile quand la précédente se termine
        idx += 1
    if idx >= len(durees):
        conn.execute(
            "UPDATE quizzes SET status='termine', current_index=?, finished_at=? WHERE id=?",
            (len(durees), started, quiz_id))
    else:
        conn.execute(
            "UPDATE quizzes SET current_index=?, question_started_at=? WHERE id=?",
            (idx, started, quiz_id))
    return conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()


def start_quiz(quiz_id):
    with connect() as conn:
        conn.execute(
            "UPDATE quizzes SET question_started_at = ? WHERE id = ? AND question_started_at IS NULL",
            (time.time(), quiz_id))


def quiz_state(quiz_id):
    """État courant envoyé au navigateur. Ne contient JAMAIS la bonne réponse."""
    with connect() as conn:
        quiz = _sync(conn, quiz_id)
        qs = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)).fetchall()
        base = {"ue": quiz["ue"], "total": len(qs), "plan": [q["difficulte"] for q in qs]}
        if quiz["status"] == "termine":
            return {**base, "status": "termine"}
        if quiz["question_started_at"] is None:
            return {**base, "status": "pret"}
        idx = quiz["current_index"]
        q = qs[idx]
        remaining = max(0.0, quiz["question_started_at"] + q["duree"] - time.time())
        return {
            **base, "status": "en_cours", "index": idx, "duree": q["duree"],
            "remaining": round(remaining, 2), "difficulte": q["difficulte"],
            "enonce": q["enonce"], "options": json.loads(q["options"]), "chosen": q["chosen"],
        }


def select_answer(quiz_id, index, choice):
    """Enregistre (ou modifie) la réponse de la question en cours. Refusé si le temps est écoulé."""
    with connect() as conn:
        quiz = _sync(conn, quiz_id)
        if quiz["status"] != "en_cours" or quiz["question_started_at"] is None:
            return False
        if quiz["current_index"] != index:
            return False
        conn.execute(
            "UPDATE questions SET chosen = ? WHERE quiz_id = ? AND position = ?",
            (choice, quiz_id, index))
        return True


def quiz_result(quiz_id):
    with connect() as conn:
        quiz = _sync(conn, quiz_id)
        if quiz["status"] != "termine":
            return None
        rows = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)).fetchall()
    items, bonnes, fausses, sans = [], 0, 0, 0
    for r in rows:
        if r["chosen"] is None:
            etat, sans = "none", sans + 1
        elif r["chosen"] == r["correct"]:
            etat, bonnes = "ok", bonnes + 1
        else:
            etat, fausses = "ko", fausses + 1
        items.append({
            "position": r["position"], "enonce": r["enonce"], "options": json.loads(r["options"]),
            "correct": r["correct"], "chosen": r["chosen"], "explication": r["explication"],
            "difficulte": r["difficulte"], "etat": etat,
        })
    return {
        "ue": quiz["ue"], "total": len(rows), "bonnes": bonnes, "fausses": fausses,
        "sans_reponse": sans, "ratees": fausses + sans, "items": items,
    }


def list_quizzes(student_id):
    with connect() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM quizzes WHERE student_id = ? ORDER BY id DESC", (student_id,))]
        out = []
        for qid in ids:
            quiz = _sync(conn, qid)
            score = conn.execute(
                "SELECT COUNT(*) FROM questions WHERE quiz_id=? AND chosen = correct", (qid,)
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM questions WHERE quiz_id=?", (qid,)).fetchone()[0]
            out.append({"id": qid, "ue": quiz["ue"], "status": quiz["status"],
                        "code": quiz["code"], "titre": quiz["titre"], "chapitres": quiz["chapitres"],
                        "created_at": quiz["created_at"], "score": score, "total": total})
        return out
