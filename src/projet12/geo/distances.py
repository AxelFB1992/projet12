"""Calcul (avec cache) des distances domicile-travail des salariés au trajet sportif.

Ce module calcule des FAITS (distance, durée). La RÈGLE métier (15 km à pied,
25 km à vélo) est appliquée plus loin, dans dbt, à partir d'une table de
paramètres : changer un seuil ne nécessite donc pas de rappeler l'API.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import psycopg

from projet12.geo.routes import TAILLE_LOT, calculer_lot

# Mode déclaré dans le fichier RH -> mode de calcul de l'API Google
MODES_API = {
    "Marche/running": "WALK",
    "Vélo/Trottinette/Autres": "BICYCLE",   # approximation pour la trottinette
}

DDL = """
CREATE TABLE IF NOT EXISTS geo.distances_domicile_travail (
    id_salarie   INTEGER PRIMARY KEY,
    adresse      TEXT NOT NULL,       -- adresse utilisée pour le calcul
    mode_api     TEXT NOT NULL,       -- WALK ou BICYCLE
    distance_m   INTEGER,
    duree_s      INTEGER,
    statut       TEXT NOT NULL,       -- ROUTE_EXISTS, ROUTE_NOT_FOUND, ERREUR_...
    calcule_le   TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class Trajet:
    id_salarie: int
    adresse: str
    mode_api: str


def trajets_a_calculer(conn: psycopg.Connection, forcer: bool = False) -> tuple[list[Trajet], int]:
    """Salariés au trajet sportif dont la distance est absente ou périmée
    (adresse ou mode changé). Renvoie (à calculer, nombre déjà en cache)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id_salarie, adresse, moyen_deplacement FROM raw.salaries "
            "WHERE moyen_deplacement = ANY(%s) ORDER BY id_salarie",
            (list(MODES_API),),
        )
        sportifs = [Trajet(i, a, MODES_API[m]) for i, a, m in cur.fetchall()]
        cur.execute("SELECT id_salarie, adresse, mode_api FROM geo.distances_domicile_travail "
                    "WHERE statut = 'ROUTE_EXISTS'")
        en_cache = {Trajet(*ligne) for ligne in cur.fetchall()}

    if forcer:
        return sportifs, 0
    a_calculer = [t for t in sportifs if t not in en_cache]
    return a_calculer, len(sportifs) - len(a_calculer)


def calculer(client: httpx.Client, cle: str, trajets: list[Trajet], destination: str) -> list[tuple]:
    """Appelle l'API par lots, mode par mode. Renvoie les lignes à enregistrer."""
    lignes = []
    for mode in sorted({t.mode_api for t in trajets}):
        du_mode = [t for t in trajets if t.mode_api == mode]
        for i in range(0, len(du_mode), TAILLE_LOT):
            lot = du_mode[i:i + TAILLE_LOT]
            # ", France" aide le géocodage des adresses incomplètes (sans code postal...)
            resultats = calculer_lot(client, cle, [f"{t.adresse}, France" for t in lot], destination, mode)
            for t, r in zip(lot, resultats):
                lignes.append((t.id_salarie, t.adresse, t.mode_api, r["distance_m"], r["duree_s"], r["statut"]))
    return lignes


def enregistrer(conn: psycopg.Connection, lignes: list[tuple], debut: datetime) -> None:
    """Upsert des distances + trace dans monitoring.pipeline_runs (une transaction)."""
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO geo.distances_domicile_travail
                   (id_salarie, adresse, mode_api, distance_m, duree_s, statut)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_salarie) DO UPDATE SET
                   adresse = EXCLUDED.adresse, mode_api = EXCLUDED.mode_api,
                   distance_m = EXCLUDED.distance_m, duree_s = EXCLUDED.duree_s,
                   statut = EXCLUDED.statut, calcule_le = now()""",
            lignes,
        )
        cur.execute(
            """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes)
               VALUES ('geo_distances', %s, now(), 'succes', %s)""",
            (debut, len(lignes)),
        )
    conn.commit()


def preparer_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def maintenant() -> datetime:
    return datetime.now(UTC)
