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

# On crée une classe qui va nous permettre de structure les informations pour l'ingestion des fichiers dans la vase de données dwh
@dataclass(frozen=True)
class Referentiel:
    etape: str                       # nom de l'étape dans monitoring.pipeline_runs
    table: str                       # table cible (schéma raw)
    colonnes: dict[str, str]         # colonne Excel -> colonne SQL : les intitulés à modifier
    colonnes_date: tuple[str, ...]   # colonnes SQL à convertir en date
    ddl: str                         # l'instruction SQL permettant la création de la table si celle-ci n'existe pas


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
    # Certaines colonnes vont être rajoutées pour correspond à la structure des tables raw, à savoir
    #     -fichier source : qui directement inscrit en dur dans la méthode charger en tant que "fichier-source"
    #     -charge_le qui permet de donner la date à laquelle les données ont été ingérés : now() donne l'heure courante.
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
    # Certaines colonnes vont être rajoutées pour correspond à la structure des tables raw, à savoir
    #     -fichier source : qui directement inscrit en dur dans la méthode charger en tant que "fichier-source"
    #     -charge_le qui permet de donner la date à laquelle les données ont été ingérés : now() donne l'heure courante.
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

# Regarde si la structure des données du fichier RH correspond à ce que l'on attend (ce qui est prévu dans le referentiel correspondant
# Quel que soit le type d'anomalie rencontré : 
#     - Une colonne manquante
#     - Un fichier vide (de données)
#     - Un idienfiant salarié null
#     - Une valeur en doublon constaté sur l'identifiant salarié
# Une exeception de type FichierInvalide (définie ci-dessus) sera levée
# Sinon un data frame sera crée, contenant les valeurs des différents lignes et colonnes, et retourné
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
    # On récupère toutes les informations du fichier et on le stocke dans un dataframe en renommant les colonnes comme dans le référentiel
    df = df[list(ref.colonnes)].rename(columns=ref.colonnes)
    # Pour les colonnes dates prévues dans le référentiel, on applique un traitement afin de les convertir en DateTime
    for col in ref.colonnes_date:
        df[col] = pd.to_datetime(df[col]).dt.date
    return df

# Cette méthode permet de transformer un dataframe "propre" vers un ensemble de ligne, en rajoutant le nom du fichier source comme colonne
def vers_lignes(df: pd.DataFrame, fichier: Path) -> list[tuple]:
    """DataFrame -> liste de tuples prêts pour l'insertion (NaN -> NULL)."""
    # On nettoie le dataframe reçu de la fonction précedente en transformant les valeurs vides par des valeurs None (interpretables en NULL)
    propre = df.astype(object).where(df.notna(), None)
    # On transforme le dataframe en un ensemble de lignes à ingérer, avec une colonne en plus fichier.name qui correspond à 'fichier_source'
    return [(*ligne, fichier.name) for ligne in propre.itertuples(index=False)]

# La méthode principale qui permet de charger un fichier dans la base de données dwh en utilisant les autres méthodes de nettoyage et validation
def charger(conn: psycopg.Connection, fichier: Path, ref: Referentiel) -> int:
    """Charge un référentiel et trace l'exécution dans monitoring.pipeline_runs."""
    debut = datetime.now(UTC)
    try:
        # On commence par créer le dataframe en lisant le fichier et en transformant les colonnes comme celles souhaitées dans le référentiel
        df = lire_et_valider(fichier, ref)
        # Une fois le dataframe crée, on le nettoie une dernière fois ("NaN" en None) et on le transforme en un ensemble de lignes à insérer
        lignes = vers_lignes(df, fichier)
        # On récupère les colonnes du référentiel + la colonne qu'on a rajouté comme valeur (fichier.name) dans l'ensemble de lignes
        colonnes = [*ref.colonnes.values(), "fichier_source"]
        # On va insérer l'ensemble des lignes en même temps grâce à la méthode executemany du curseur
        with conn.cursor() as cur:
            cur.execute(ref.ddl)
            # Instruction très importante : vide la table avant de la remplir complètement -> C'est un remplacement total de la table ref.table
            cur.execute(f"TRUNCATE {ref.table}")
            # Les INSERT vont être executé dans la même transaction que le TRUNCATE de telle sorte que si une erreur se produit pendant l'insertion
            # alors rien ne sera modifiée et la dernière version de la table propre (avant le TRUNCATE) sera restaurée
            cur.executemany(
                f"INSERT INTO {ref.table} ({', '.join(colonnes)}) "
                f"VALUES ({', '.join(['%s'] * len(colonnes))})",
                lignes,
            )
            # la méthode tracer permet d'inserer dans la table monitoring.pipeline_runs de dwh les informations d'insertions dans les tables raw
            _tracer(cur, ref.etape, debut, "succes", len(lignes), fichier.name)
        # On commit les modifications puis on retourne le nombre de lignes insérées
        conn.commit()
        return len(lignes)
    except Exception as erreur:
        # Si jamais il y a une exception qui est levé au cours de l'insertion, on annule tout ce que l'on a fait
        conn.rollback()   # la table garde son contenu précédent
        with conn.cursor() as cur:
            # Dans ce cas, on va également "tracer" cet echec dans la table de monitoring (monitoring.pipeline_runs)
            _tracer(cur, ref.etape, debut, "echec", None, str(erreur)[:500])
        conn.commit()
        raise

# Cette méthode permet de tracer l'execution des certaines actions dans la table dwh avec des informations complémentaires (début,fin,etc)
def _tracer(cur, etape, debut, statut, nb_lignes, message) -> None:
    # On utilise le même curseur que celui qui a servir pour l'opération sur la table principale
    cur.execute(
        """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes, message)
           VALUES (%s, %s, now(), %s, %s, %s)""",
        (etape, debut, statut, nb_lignes, message),
    )
