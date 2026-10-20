"""Serveur Flask : pages HTML + API JSON.

Lancer :  python app.py   puis ouvrir http://localhost:5000
"""
import os
import re
import secrets
import sqlite3
import threading
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session

load_dotenv()

import ai_service  # noqa: E402  (après load_dotenv pour lire .env)
import database as db  # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 14

db.init_db()

NIVEAUX = ["Licence 1", "Licence 2", "Licence 3", "Master 1", "Master 2", "Doctorat"]
# Premier chiffre attendu dans le code de l'UE selon le niveau (Licence 2 -> 2xx). Master/Doctorat : libre.
CHIFFRE_NIVEAU = {"Licence 1": "1", "Licence 2": "2", "Licence 3": "3"}
CODE_UE = re.compile(r"^([A-Za-z]{2,6})?\s*(\d{3})$")

_generating = set()          # étudiants dont une vague est en cours de génération
_generating_lock = threading.Lock()


# ------------------------------------------------------------------ outils
def clean(value, max_len=80):
    return " ".join(str(value or "").split())[:max_len]


def current_student():
    sid = session.get("student_id")
    return db.get_student(sid) if sid else None


@app.context_processor
def inject_student():
    return {"student": current_student(), "niveaux": NIVEAUX}


def page_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        student = current_student()
        if not student:
            return redirect("/")
        return view(student, *args, **kwargs)
    return wrapper


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        student = current_student()
        if not student:
            return jsonify(error="Session expirée. Reconnectez-vous."), 401
        return view(student, *args, **kwargs)
    return wrapper


def owned_quiz(student, quiz_id):
    quiz = db.get_quiz(quiz_id)
    return quiz if quiz and quiz["student_id"] == student["id"] else None


def read_identity(data):
    identity = {
        "nom": clean(data.get("nom")),
        "prenom": clean(data.get("prenom")),
        "niveau": clean(data.get("niveau")),
        "matricule": clean(data.get("matricule"), 30).replace(" ", "").upper(),
    }
    if not all(identity.values()):
        return None, "Renseignez les quatre champs : nom, prénom, niveau et matricule."
    if identity["niveau"] not in NIVEAUX:
        return None, "Choisissez un niveau dans la liste."
    return identity, None


# ------------------------------------------------------------------- pages
@app.get("/")
def home():
    if current_student():
        return redirect("/ue")
    return render_template("index.html")


@app.get("/ue")
@page_login_required
def ue_page(student):
    return render_template("ue.html")


@app.get("/quiz/<int:quiz_id>")
@page_login_required
def quiz_page(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return redirect("/ue")
    return render_template("quiz.html", quiz_id=quiz_id)


@app.get("/resultat/<int:quiz_id>")
@page_login_required
def result_page(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return redirect("/ue")
    return render_template("resultat.html", quiz_id=quiz_id)


# --------------------------------------------------------- API : comptes
@app.post("/api/register")
def register():
    identity, error = read_identity(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    try:
        student_id = db.create_student(**identity)
    except sqlite3.IntegrityError:
        return jsonify(error="Ce matricule est déjà inscrit. Utilisez l'onglet « Connexion »."), 409
    session.permanent = True
    session["student_id"] = student_id
    return jsonify(ok=True)


@app.post("/api/login")
def login():
    identity, error = read_identity(request.get_json(silent=True) or {})
    if error:
        return jsonify(error=error), 400
    student = db.find_student_by_matricule(identity["matricule"])
    same = student and all(
        db.normalize(student[k]) == db.normalize(identity[k]) for k in ("nom", "prenom", "niveau")
    )
    if not same:
        return jsonify(error="Aucun compte ne correspond à ces informations. "
                             "Saisissez exactement les mêmes qu'à l'inscription."), 401
    session.permanent = True
    session["student_id"] = student["id"]
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@api_login_required
def me(student):
    return jsonify(
        prenom=student["prenom"], nom=student["nom"], niveau=student["niveau"],
        quizzes=db.list_quizzes(student["id"]),
    )


# ------------------------------------------------------------ API : quiz
@app.post("/api/quiz")
@api_login_required
def create_quiz(student):
    data = request.get_json(silent=True) or {}
    code_brut = clean(data.get("code"), 20)
    titre = clean(data.get("titre"), 120)
    chapitres = clean(data.get("chapitres"), 600)

    m = CODE_UE.match(code_brut)
    if not m:
        return jsonify(error="Code de l'UE invalide : trois chiffres, avec ou sans lettres (ex. 231 ou INF 231)."), 400
    lettres, chiffres = (m.group(1) or "").upper(), m.group(2)
    attendu = CHIFFRE_NIVEAU.get(student["niveau"])
    if attendu and chiffres[0] != attendu:
        return jsonify(error=f"En {student['niveau']}, le code de l'UE commence par {attendu} (ex. {attendu}31)."), 400
    code = f"{lettres} {chiffres}".strip()
    if len(titre) < 3:
        return jsonify(error="Indiquez le titre de l'UE."), 400
    if len(chapitres) < 3:
        return jsonify(error="Indiquez le chapitre à étudier."), 400

    with _generating_lock:
        if student["id"] in _generating:
            return jsonify(error="Une génération est déjà en cours pour votre compte."), 429
        _generating.add(student["id"])
    try:
        avoid = db.previous_enonces(student["id"], f"{code} · {titre}")
        questions = ai_service.generate_wave(code, titre, student["niveau"], chapitres, avoid)
        quiz_id = db.create_quiz(student["id"], code, titre, chapitres, questions)
    except ai_service.GenerationError as exc:
        return jsonify(error=str(exc)), 502
    finally:
        with _generating_lock:
            _generating.discard(student["id"])
    return jsonify(id=quiz_id)


@app.post("/api/quiz/<int:quiz_id>/start")
@api_login_required
def start_quiz(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return jsonify(error="QCM introuvable."), 404
    db.start_quiz(quiz_id)
    return jsonify(db.quiz_state(quiz_id))


@app.get("/api/quiz/<int:quiz_id>/state")
@api_login_required
def quiz_state(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return jsonify(error="QCM introuvable."), 404
    return jsonify(db.quiz_state(quiz_id))


@app.post("/api/quiz/<int:quiz_id>/select")
@api_login_required
def select(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return jsonify(error="QCM introuvable."), 404
    data = request.get_json(silent=True) or {}
    try:
        index, choice = int(data["index"]), int(data["choice"])
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Requête invalide."), 400
    if not 0 <= choice <= 3:
        return jsonify(error="Réponse invalide."), 400
    if not db.select_answer(quiz_id, index, choice):
        return jsonify(error="Le temps de cette question est écoulé."), 409
    return jsonify(ok=True)


@app.get("/api/quiz/<int:quiz_id>/result")
@api_login_required
def result(student, quiz_id):
    if not owned_quiz(student, quiz_id):
        return jsonify(error="QCM introuvable."), 404
    res = db.quiz_result(quiz_id)
    if res is None:
        return jsonify(error="Le QCM n'est pas terminé."), 409
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False, threaded=True)
