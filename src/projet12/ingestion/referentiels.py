"""Ingestion des référentiels RH et sport (Excel) dans l'entrepôt : dwh.raw.

Principe « raw » : les données sont chargées TELLES QUELLES (y compris "Runing"
ou les adresses mal formatées). Le nettoyage est fait ensuite par dbt (staging).

Chaque exécution remplace entièrement la table (TRUNCATE + INSERT dans une seule
transaction) : le script est rejouable à volonté, par exemple quand les RH
envoient une nouvelle version du fichier.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import psycopg


@dataclass(frozen=True)
class Referentiel:
    etape: str                       # nom de l'étape dans monitoring.pipeline_runs
    table: str                       # table cible (schéma raw)
    colonnes: dict[str, str]         # colonne Excel -> colonne SQL
    colonnes_date: tuple[str, ...]   # colonnes SQL à convertir en date
    ddl: str


SALARIES = Referentiel(
    etape="ingestion_rh",
    table="raw.salaries",
    colonnes={
        "ID salarié": "id_salarie", "Nom": "nom", "Prénom": "prenom",
        "Date de naissance": "date_naissance", "BU": "bu",
        "Date d'embauche": "date_embauche", "Salaire brut": "salaire_brut",
        "Type de contrat": "type_contrat", "Nombre de jours de CP": "jours_cp",
        "Adresse du domicile": "adresse", "Moyen de déplacement": "moyen_deplacement",
    },
    colonnes_date=("date_naissance", "date_embauche"),
    ddl="""
        CREATE TABLE IF NOT EXISTS raw.salaries (
            id_salarie        INTEGER PRIMARY KEY,
            nom               TEXT,
            prenom            TEXT,
            date_naissance    DATE,
            bu                TEXT,
            date_embauche     DATE,
            salaire_brut      INTEGER,
            type_contrat      TEXT,
            jours_cp          INTEGER,
            adresse           TEXT,
            moyen_deplacement TEXT,
            fichier_source    TEXT,
            charge_le         TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
)

SPORTS = Referentiel(
    etape="ingestion_sport",
    table="raw.sports",
    colonnes={"ID salarié": "id_salarie", "Pratique d'un sport": "pratique_sport"},
    colonnes_date=(),
    ddl="""
        CREATE TABLE IF NOT EXISTS raw.sports (
            id_salarie      INTEGER PRIMARY KEY,
            pratique_sport  TEXT,
            fichier_source  TEXT,
            charge_le       TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
)


class FichierInvalide(Exception):
    """Le fichier n'a pas la structure attendue : on refuse de le charger."""


def lire_et_valider(fichier: Path, ref: Referentiel) -> pd.DataFrame:
    """Lit l'Excel et vérifie sa STRUCTURE (pas la qualité des valeurs : c'est Soda).
    Un fichier mal formé ne doit jamais écraser des données correctes."""
    df = pd.read_excel(fichier)
    manquantes = set(ref.colonnes) - set(df.columns)
    if manquantes:
        raise FichierInvalide(f"{fichier.name} : colonnes manquantes {sorted(manquantes)}")
    if df.empty:
        raise FichierInvalide(f"{fichier.name} : fichier vide")
    ids = df["ID salarié"]
    if ids.isna().any():
        raise FichierInvalide(f"{fichier.name} : identifiants salariés vides")
    if ids.duplicated().any():
        doublons = sorted(ids[ids.duplicated()].unique().tolist())
        raise FichierInvalide(f"{fichier.name} : identifiants en double {doublons}")

    df = df[list(ref.colonnes)].rename(columns=ref.colonnes)
    for col in ref.colonnes_date:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df


def vers_lignes(df: pd.DataFrame, fichier: Path) -> list[tuple]:
    """DataFrame -> liste de tuples prêts pour l'insertion (NaN -> NULL)."""
    propre = df.astype(object).where(df.notna(), None)
    return [(*ligne, fichier.name) for ligne in propre.itertuples(index=False)]


def charger(conn: psycopg.Connection, fichier: Path, ref: Referentiel) -> int:
    """Charge un référentiel et trace l'exécution dans monitoring.pipeline_runs."""
    debut = datetime.now(UTC)
    try:
        df = lire_et_valider(fichier, ref)
        lignes = vers_lignes(df, fichier)
        colonnes = [*ref.colonnes.values(), "fichier_source"]
        with conn.cursor() as cur:
            cur.execute(ref.ddl)
            cur.execute(f"TRUNCATE {ref.table}")
            cur.executemany(
                f"INSERT INTO {ref.table} ({', '.join(colonnes)}) "
                f"VALUES ({', '.join(['%s'] * len(colonnes))})",
                lignes,
            )
            _tracer(cur, ref.etape, debut, "succes", len(lignes), fichier.name)
        conn.commit()
        return len(lignes)
    except Exception as erreur:
        conn.rollback()   # la table garde son contenu précédent
        with conn.cursor() as cur:
            _tracer(cur, ref.etape, debut, "echec", None, str(erreur)[:500])
        conn.commit()
        raise


def _tracer(cur, etape, debut, statut, nb_lignes, message) -> None:
    cur.execute(
        """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes, message)
           VALUES (%s, %s, now(), %s, %s, %s)""",
        (etape, debut, statut, nb_lignes, message),
    )
