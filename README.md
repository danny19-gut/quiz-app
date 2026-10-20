# Examen blanc — site de QCM générés par IA

## 1. Lancer le site (5 étapes)

```
1) cd qcm-app
2) python -m venv venv && source venv/bin/activate      (Windows : venv\Scripts\activate)
3) pip install -r requirements.txt
4) copier .env.example en .env  puis y mettre votre clé ANTHROPIC_API_KEY
   SANS CLÉ, LE SITE REFUSE DE GÉNÉRER (message d'erreur clair) : il n'invente plus de questions.
   Pour tester seulement l'interface : ajouter AI_MODE=mock dans .env (questions factices « [DÉMO] »)
5) python app.py      →  http://localhost:5000
```

## 2. Structure

```
qcm-app/
├── app.py            Serveur Flask : pages + API JSON
├── database.py       Accès SQLite + chronomètre côté serveur
├── ai_service.py     Appels à l'IA : génère les 40 questions
├── schema.sql        Tables : students, quizzes, questions
├── qcm.db            Base créée automatiquement au 1er lancement
├── .env              Clé API (ne jamais partager)
├── templates/        index (inscription/connexion) · ue · quiz · resultat
└── static/
    ├── css/style.css Design responsive, mode clair/sombre automatique
    └── js/           api.js · auth.js · ue.js · quiz.js · resultat.js
```

## 3. Parcours de l'étudiant

```
Inscription / Connexion ──► Code + titre de l'UE ──► Génération (30-60 s) ──► Briefing
 nom, prénom, niveau,        + chapitre à étudier     3 appels IA en           │
 matricule                   (ex. INF 231)            parallèle                ▼
                                                                  40 questions chronométrées
                                                                          │
                                       Résultat : trouvées / ratées ◄─────┘
                                                  puis correction détaillée
```

## 4. Les 40 questions et leur temps

| Niveau                | Nombre | Temps par question |
|-----------------------|--------|--------------------|
| Moyen                 | 10     | 1 min              |
| Difficile             | 15     | 1 min 30           |
| Extrêmement difficile | 15     | 2 min              |

Modifiable dans `LEVELS` (fichier `ai_service.py`).

## 5. Le chronomètre (point clé)

```
Navigateur                          Serveur (source de vérité)
──────────                          ──────────────────────────
clic "Commencer"  ───────────────►  enregistre l'heure de départ
affiche la question + compte à rebours
clic sur une réponse ────────────►  enregistre le choix (modifiable)
temps = 0 : demande l'état ──────►  heure écoulée ? passe à la question suivante
affiche la question suivante  ◄──── (la bonne réponse n'est JAMAIS envoyée avant la fin)
```

- Réponse modifiable tant que le temps n'est pas fini ; on ne peut pas passer avant.
- Pas de réponse = question suivante automatique, comptée « sans réponse ».
- Actualiser la page ou fermer l'onglet ne remet pas le temps à zéro.
- Impossible de répondre après le temps (le serveur refuse).

## 5 bis. Le formulaire d'UE

- Code : trois chiffres, avec ou sans lettres (« 231 » ou « INF 231 »).
  En Licence 1 le code commence par 1, en Licence 2 par 2, en Licence 3 par 3.
- Titre de l'UE et chapitre à étudier : obligatoires. L'IA écrit les 40 questions
  uniquement sur ce chapitre.

## 6. Une nouvelle vague à chaque fois

Chaque clic sur « Générer » appelle l'IA : nouveau QCM de 40 questions. Les questions
déjà posées à l'étudiant sur la même UE sont transmises à l'IA pour qu'elle ne les répète pas.

## 7. Reconnexion

Même nom, prénom, niveau et matricule qu'à l'inscription (majuscules et accents ignorés).
Le matricule est unique. L'historique de tous les QCM est conservé dans `qcm.db`.

## 8. Mise en ligne

`gunicorn -w 4 -t 180 app:app` (le délai de 180 s couvre la génération des questions).
Définir SECRET_KEY dans `.env` et passer en HTTPS.
