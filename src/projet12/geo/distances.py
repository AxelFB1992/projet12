"""Calcul (avec cache) des distances domicile-travail des salariés au trajet sportif.

Ce module calcule des FAITS (distance, durée). La RÈGLE métier (15 km à pied,
25 km à vélo) est appliquée plus loin, dans dbt, à partir d'une table de
paramètres : changer un seuil ne nécessite donc pas de rappeler l'API.

Ce module contient 3 méthodes permettant chacune de réaliser une action différentes :
    - trajets_a_calculer : permet de retourner les listes des trajets à calculer en fonction des salariés qui ont déclaré un moyen de transport
        sportif pour venir au travail
    - calculer : permet de calculer les distances domiciles-travail des trajets de la liste retournées par la méthode précedente. Cette méthode
        ne fait pas directement appel à l'API google mais délègue cela à la méthode calculer_lot de routes.py
    - enregistrer : permet d'écrire l'intégralité des résultats obtenus (informations de trajets + résultats du calcul) obtenues par la méthode
        précedente dans la base de données geo.distances_domicile_travail

Une autre méthode eest là pour préparer la table geo.distances_domicile_travail si elle n'existe pas et retourner l'heure courante.

Ce module est donc l'interface entre la base de données raw.salaries qui stocke les informations sur les salariés dont la distance domicile travail
et l'API Google qui prend en paramètre les informations qu'on lui donne en dur selon un protocole bien précis (d'où le pré-traitement) d'une part
et d'autre part, dans l'autre sens, le résultat donné par l'API Google et la base de données geo.distances_domicile_travail dans laquelle
il faut écrire les resultats obtenus ainsi que les informations du trajet

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

# On crée une classe spécifique pour calculer le trajet 
# Celle-ci ne prend pas l'adresse de la société en paramètre car elle est commune pour tous les trajets de tous les salariés
@dataclass(frozen=True)
class Trajet:
    id_salarie: int
    adresse: str
    mode_api: str # correspond au moyen de déplacement : WALK ou BICYCLE

# Retourne une liste de Trajets (salarié, adresse et mode) à (re)calculer ainsi que le nombre de trajets déjà calculés en base (pour sporifs)
def trajets_a_calculer(conn: psycopg.Connection, forcer: bool = False) -> tuple[list[Trajet], int]:
    """Salariés au trajet sportif dont la distance est absente ou périmée
    (adresse ou mode changé). Renvoie (à calculer, nombre déjà en cache)."""
    with conn.cursor() as cur:
        # On liste tous les salaries pour lesquels le moyen de déplacement est contenu dans list(MODES_API) (voir ci-dessus)
        cur.execute(
            "SELECT id_salarie, adresse, moyen_deplacement FROM raw.salaries "
            "WHERE moyen_deplacement = ANY(%s) ORDER BY id_salarie",
            (list(MODES_API),),
        )
        # Avec la requête, on récupère donc toutes les informations des salariés "sportifs" avec lesquelles on crée des Trajets
        sportifs = [Trajet(i, a, MODES_API[m]) for i, a, m in cur.fetchall()]
        # On liste les salariés pour lesquels la route (Trajet) a déjà calculée et est presénte dans la table en cache dans le répertoire géo
        cur.execute("SELECT id_salarie, adresse, mode_api FROM geo.distances_domicile_travail "
                    "WHERE statut = 'ROUTE_EXISTS'")
        # De la même manière, on construit une liste de Trajets avec ceux qui ont déjà été calculés
        en_cache = {Trajet(*ligne) for ligne in cur.fetchall()}

    # Si le booléen passé en paramètre est à 1, alors on doit forcer le recalcul des distances pour tous les trajets sportifs (donc 0 en cache)
    if forcer:
        return sportifs, 0
    # Sinon, on ne recalcule les distances que pour les trajets sportifs qui ne sont pas déjà en cache
    a_calculer = [t for t in sportifs if t not in en_cache]
    # On retourne la liste de trajet à calculer et la différence entre tous les trajets sportifs et ceux qui sont à calculer
    # C'est à dire les trajets sportifs à ne pas recalculer
    return a_calculer, len(sportifs) - len(a_calculer)

# Pour la liste de trajets à calculer (retournée par la méthode ci-dessus), on effectue le calcul des distance réelles par l'API de google
def calculer(client: httpx.Client, cle: str, trajets: list[Trajet], destination: str) -> list[tuple]:
    """Appelle l'API par lots, mode par mode. Renvoie les lignes à enregistrer."""
    lignes = []
    # Pour tous 2 modes de transport prévu (t.mode-api) ordonné dans un certain ordre
    for mode in sorted({t.mode_api for t in trajets}):
        # On liste tous les trajets correspondant au mode courant
        du_mode = [t for t in trajets if t.mode_api == mode]
        # Pour tous les trajets du mode courant, en augmentant i par la taille du lot pour passer au prochain mode à la prochaine itération
        for i in range(0, len(du_mode), TAILLE_LOT):
            # On ne récupère que les trajets qui correspondent au mode courant
            lot = du_mode[i:i + TAILLE_LOT]
            # On utilise la méthode calculer_lot pour calculer les distances par lot de trajets
            # On passe la clé API en paramètre ainsi que le client pour pouvoir se connecter à l'API dans 
            # ", France" aide le géocodage des adresses incomplètes (sans code postal...) calculer_lot
            resultats = calculer_lot(client, cle, [f"{t.adresse}, France" for t in lot], destination, mode)
            # On parcourt les résultats en les parcourant par tuple grâce à la méthode zip qui associe chaque trajet(lot) à chaqye distance (résultat)
            for t, r in zip(lot, resultats):
                # On ajoute à la liste 'lignes' les résultats du calcul avec les informations des trajets et les résultats du calcul
                lignes.append((t.id_salarie, t.adresse, t.mode_api, r["distance_m"], r["duree_s"], r["statut"]))
    return lignes

# Permet d'enregistrer les distances calculées (sous forme de liste de tuples) dans la base de données dwh
def enregistrer(conn: psycopg.Connection, lignes: list[tuple], debut: datetime) -> None:
    """Upsert des distances + trace dans monitoring.pipeline_runs (une transaction)."""
    # Toujours avec un curseur pour executer les instructions 
    with conn.cursor() as cur:
        # On execute plusieurs insertions dans la base de données correspondant au résultat de la méthode ci-dessus à savoir un groupe 
        # de lignes avec les informations du trajet plus des informations retournées par l'API google lors du calcul de distance
        cur.executemany(
            """INSERT INTO geo.distances_domicile_travail
                   (id_salarie, adresse, mode_api, distance_m, duree_s, statut)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id_salarie) DO UPDATE SET
                   adresse = EXCLUDED.adresse, mode_api = EXCLUDED.mode_api,
                   distance_m = EXCLUDED.distance_m, duree_s = EXCLUDED.duree_s,
                   statut = EXCLUDED.statut, calcule_le = now()""",
            # Les pourcentages ci-dessus vont être remplacés par les différents champs de chaque élément de la liste
            lignes,
        )
        # Comme pour les autres écritures sur la base de données dwh, on laisse une trâce de ce que l'on a fait dans monitoring.pipeline_runs
        cur.execute(
            """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes)
               VALUES ('geo_distances', %s, now(), 'succes', %s)""",
            (debut, len(lignes)),
        )
    conn.commit()

# Une méthode qui permet de creer la table geo.distances_domicile_travail si elle n'existe pas
def preparer_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
