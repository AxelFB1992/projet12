"""Configuration commune à tous les scripts du projet.

Les valeurs viennent des variables d'environnement, chargées depuis le fichier
.env à la racine du projet. Aucun secret n'est écrit dans le code.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# Racine du projet : src/projet12/config.py -> remonter de 2 niveaux
RACINE = Path(__file__).resolve().parents[2]
load_dotenv(RACINE / ".env")

# Fichiers sources (modifiable par variable d'environnement, utile dans Docker)
DOSSIER_DONNEES = Path(os.getenv("DOSSIER_DONNEES", RACINE / "data" / "raw"))
FICHIER_RH = DOSSIER_DONNEES / "donnees_rh.xlsx"
FICHIER_SPORT = DOSSIER_DONNEES / "donnees_sportives.xlsx"

# Fuseau horaire de l'entreprise (Lattes)
FUSEAU = "Europe/Paris"


def _variable_obligatoire(nom: str) -> str:
    """Lit une variable d'environnement et échoue clairement si elle manque."""
    valeur = os.getenv(nom)
    if not valeur:
        raise RuntimeError(
            f"Variable d'environnement manquante : {nom}. "
            "Vérifie ton fichier .env (modèle : .env.example)."
        )
    return valeur


def connexion_app() -> psycopg.Connection:
    """Connexion à la base source 'app' avec le rôle app_writer
    (lecture + insertion uniquement sur la table activites)."""
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname="app",
        user="app_writer",
        password=_variable_obligatoire("APP_WRITER_PASSWORD"),
    )
