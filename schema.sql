-- Schéma de la base de données (SQLite). Créé automatiquement au premier lancement.

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL,
    prenom      TEXT NOT NULL,
    niveau      TEXT NOT NULL,
    matricule   TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);

-- Un quiz = une "vague" de 40 questions générées pour un étudiant et une UE.
CREATE TABLE IF NOT EXISTS quizzes (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id           INTEGER NOT NULL REFERENCES students(id),
    ue                   TEXT NOT NULL,                      -- affichage : 'INF 231 · Titre'
    code                 TEXT NOT NULL DEFAULT '',           -- code de l'UE (ex. INF 231)
    titre                TEXT NOT NULL DEFAULT '',           -- intitulé de l'UE
    chapitres            TEXT NOT NULL DEFAULT '',           -- chapitre(s) à étudier
    status               TEXT NOT NULL DEFAULT 'en_cours',   -- 'en_cours' | 'termine'
    current_index        INTEGER NOT NULL DEFAULT 0,
    question_started_at  REAL,                               -- NULL tant que l'étudiant n'a pas cliqué sur "Commencer"
    created_at           REAL NOT NULL,
    finished_at          REAL
);

CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id      INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,          -- 0 à 39
    enonce       TEXT NOT NULL,
    options      TEXT NOT NULL,             -- JSON : liste de 4 propositions
    correct      INTEGER NOT NULL,          -- index (0-3) de la bonne réponse
    explication  TEXT,
    difficulte   TEXT NOT NULL,             -- 'moyen' | 'difficile' | 'extreme'
    duree        INTEGER NOT NULL,          -- temps alloué en secondes
    chosen       INTEGER,                   -- réponse de l'étudiant (NULL = pas de réponse)
    UNIQUE (quiz_id, position)
);

CREATE INDEX IF NOT EXISTS idx_quizzes_student ON quizzes(student_id);
CREATE INDEX IF NOT EXISTS idx_questions_quiz  ON questions(quiz_id);
