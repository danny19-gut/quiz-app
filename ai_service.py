"""Génération des QCM par l'IA (API Anthropic).

Une "vague" = 40 questions : 10 moyennes, 15 difficiles, 15 extrêmement difficiles.
Les 3 niveaux sont demandés en parallèle (3 appels simultanés) pour gagner du temps.
Mettre AI_MODE=mock dans .env pour tester le site sans clé API.
"""
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor

from database import normalize


class GenerationError(Exception):
    pass


MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# Durées : moyen 1 min, extrêmement difficile 2 min, difficile entre les deux.
LEVELS = {
    "moyen": {
        "count": 10, "duree": 60, "label": "Moyen",
        "desc": "notions bien comprises, application directe, définitions précises, raisonnement en 1 à 2 étapes",
    },
    "difficile": {
        "count": 15, "duree": 90, "label": "Difficile",
        "desc": "raisonnement en plusieurs étapes, cas pratiques, pièges classiques, comparaison de notions proches",
    },
    "extreme": {
        "count": 15, "duree": 120, "label": "Extrêmement difficile",
        "desc": ("synthèse de plusieurs chapitres, cas limites, analyse approfondie ou calcul soutenu, "
                 "propositions fausses très plausibles ; niveau d'un partiel redoutable"),
    },
}
ORDER = ["moyen", "difficile", "extreme"]

ANGLES = [
    "définitions et propriétés formelles", "cas pratiques et mises en situation",
    "erreurs fréquentes des étudiants", "raisonnement logique et démonstration",
    "analyse de code, de schéma ou de calcul", "comparaison de notions proches",
    "applications concrètes", "cas limites et exceptions", "vocabulaire et notation précise",
]

SYSTEM = (
    "Tu es un enseignant universitaire expérimenté qui rédige des QCM d'examen en français. "
    "Tes questions sont exactes, sans ambiguïté, avec une seule bonne réponse. "
    "Tu réponds UNIQUEMENT avec un tableau JSON valide, sans texte avant ou après, sans balises markdown."
)


def _prompt(code, titre, niveau, chapitres, level, count, avoid):
    cfg = LEVELS[level]
    angles = ", ".join(random.sample(ANGLES, 4))
    lines = [
        f"Unité d'enseignement : {code} — {titre}",
        f"Niveau des étudiants : {niveau}",
        f"Chapitre(s) à étudier : {chapitres}",
        "",
        "Toutes les questions doivent porter EXCLUSIVEMENT sur ce(s) chapitre(s), dans le cadre de cette UE. "
        "Aucune question hors sujet ni trop générale.",
        f"Rédige {count} questions à choix multiples de difficulté « {cfg['label']} » : {cfg['desc']}.",
        f"Chaque question doit pouvoir être résolue en moins de {cfg['duree']} secondes.",
        f"Pour varier cette vague, privilégie ces angles : {angles}.",
        "Couvre des notions différentes du chapitre ; aucune question ne doit en recouper une autre.",
        "Chaque question a exactement 4 propositions, dont une seule correcte. "
        "Les mauvaises propositions doivent être plausibles et de longueur comparable.",
        "",
        'Format : [{"enonce": "...", "options": ["...", "...", "...", "..."], '
        '"bonne_reponse": 0, "explication": "1 à 3 phrases justifiant la bonne réponse"}, ...]',
        "« bonne_reponse » est l'index (0 à 3) de la bonne proposition.",
    ]
    if avoid:
        lines += ["", "Questions déjà posées à cet étudiant, à NE PAS reprendre ni reformuler :"]
        lines += [f"- {a[:140]}" for a in avoid[:40]]
    return "\n".join(lines)


def _parse(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("pas de tableau JSON")
    return json.loads(text[start:end + 1])


def _valid(item):
    """Retourne une question propre (options mélangées) ou None."""
    try:
        enonce = str(item["enonce"]).strip()
        options = [str(o).strip() for o in item["options"]]
        correct = int(item["bonne_reponse"])
        explication = str(item.get("explication", "")).strip()
    except (KeyError, TypeError, ValueError):
        return None
    if not enonce or len(options) != 4 or not all(options) or len(set(options)) != 4:
        return None
    if not 0 <= correct <= 3:
        return None
    bonne = options[correct]
    random.shuffle(options)  # évite que la bonne réponse soit toujours à la même place
    return {"enonce": enonce, "options": options, "correct": options.index(bonne),
            "explication": explication}


def _call_api(prompt):
    try:
        import anthropic  # import tardif : inutile en mode mock
    except ImportError as exc:
        raise GenerationError("Le module « anthropic » n'est pas installé : pip install -r requirements.txt") from exc

    client = anthropic.Anthropic(timeout=150.0, max_retries=1)  # lit ANTHROPIC_API_KEY
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise GenerationError("Clé API refusée : vérifiez ANTHROPIC_API_KEY dans le fichier .env.") from exc
    except anthropic.NotFoundError as exc:
        raise GenerationError(f"Modèle introuvable ({MODEL}) : vérifiez ANTHROPIC_MODEL dans .env.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise GenerationError("Accès refusé par l'API : vérifiez votre compte et vos crédits.") from exc
    return "".join(b.text for b in resp.content if b.type == "text")


def _generate_level(level, code, titre, niveau, chapitres, avoid):
    cfg, found, seen = LEVELS[level], [], {normalize(a) for a in avoid}
    for attempt in range(3):
        missing = cfg["count"] - len(found)
        if missing <= 0:
            break
        try:
            raw = _call_api(_prompt(code, titre, niveau, chapitres, level, missing + (2 if attempt == 0 else 1),
                                    avoid + [q["enonce"] for q in found]))
            items = _parse(raw)
        except GenerationError:
            raise  # clé invalide, module manquant... inutile de réessayer
        except Exception as exc:  # réseau, JSON invalide, quota...
            if attempt == 2:
                raise GenerationError(f"Échec de la génération ({cfg['label']}) : {exc}") from exc
            continue
        for item in items:
            q = _valid(item)
            if q and normalize(q["enonce"]) not in seen:
                seen.add(normalize(q["enonce"]))
                found.append({**q, "difficulte": level, "duree": cfg["duree"]})
    if len(found) < cfg["count"]:
        raise GenerationError(f"Pas assez de questions valides ({cfg['label']}). Réessayez.")
    return found[:cfg["count"]]


def _mock_level(level, ue):
    cfg, out = LEVELS[level], []
    for i in range(cfg["count"]):
        options = [f"Proposition {c}" for c in "ABCD"]
        random.shuffle(options)
        out.append({
            "enonce": f"[DÉMO — niveau {cfg['label']}] Question {i + 1} sur {ue} ? (n° {random.randint(100, 999)})",
            "options": options, "correct": options.index("Proposition A"),
            "explication": "Mode démonstration : la bonne réponse est toujours « Proposition A ».",
            "difficulte": level, "duree": cfg["duree"],
        })
    return out


def generate_wave(code, titre, niveau, chapitres, avoid):
    """Retourne 40 questions ordonnées : moyen → difficile → extrême."""
    if os.getenv("AI_MODE", "").lower() == "mock":  # uniquement si demandé explicitement
        return [q for lvl in ORDER for q in _mock_level(lvl, f"{code} {titre}")]
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise GenerationError(
            "Aucune clé API : ajoutez ANTHROPIC_API_KEY dans le fichier .env, puis relancez le site.")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {lvl: pool.submit(_generate_level, lvl, code, titre, niveau, chapitres, avoid)
                   for lvl in ORDER}
        return [q for lvl in ORDER for q in futures[lvl].result()]
