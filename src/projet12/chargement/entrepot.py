"""Écriture des activités dans l'entrepôt (dwh.raw.activites) et suivi du chargement."""

import json
from datetime import UTC, datetime

import psycopg

# Table brute (dwh.raw.activites) : même contenu que la source (app.public.activities) + métadonnées de capture (cree_le, operation, capture_le, charge_le)
# Volontairement permissive (pas de contraintes métier) : on garde la donnée telle qu'elle arrive, les contrôles qualité sont faits ensuite par Soda.
DDL_ACTIVITES = """
CREATE TABLE IF NOT EXISTS raw.activites (
    id_activite    BIGINT PRIMARY KEY,
    id_salarie     INTEGER,
    date_debut     TIMESTAMPTZ,
    type_activite  TEXT,
    distance_m     INTEGER,
    date_fin       TIMESTAMPTZ,
    commentaire    TEXT,
    source         TEXT,
    cree_le        TIMESTAMPTZ,
    operation      TEXT,          -- r = snapshot, c = insertion, u = mise à jour
    capture_le     TIMESTAMPTZ,   -- instant du commit dans la base source
    charge_le      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

COLONNES = (
    "id_activite", "id_salarie", "date_debut", "type_activite", "distance_m",
    "date_fin", "commentaire", "source", "cree_le", "operation", "capture_le",
)

# Upsert : un message reçu deux fois met à jour la même ligne -> jamais de doublon
UPSERT = f"""
INSERT INTO raw.activites ({", ".join(COLONNES)})
VALUES ({", ".join(["%s"] * len(COLONNES))})
ON CONFLICT (id_activite) DO UPDATE SET
    {", ".join(f"{c} = EXCLUDED.{c}" for c in COLONNES[1:])},
    charge_le = now()
"""

# Retourne une date au bon format
def _date(texte: str | None) -> datetime | None:
    """Retourne une date au bon format"""
    return datetime.fromisoformat(texte) if texte else None

# Transforme un message RedPanda brut (au format JSON) en un vrai message texte
def evenement_vers_ligne(valeur: bytes | None) -> tuple | None:
    """Message Redpanda brut -> ligne à insérer, ou None s'il n'y a rien à charger."""
    if valeur is None:            # message vide (tombstone)
        return None
    e = json.loads(valeur)
    ts = e.get("__source_ts_ms")
    # Ici est formaté le tuple qui sera inséré tel quel dans la base de données (il n'est pas inséré pour l'instant)
    return (
        e["id_activite"], e.get("id_salarie"), _date(e.get("date_debut")),
        e.get("type_activite"), e.get("distance_m"), _date(e.get("date_fin")),
        e.get("commentaire"), e.get("source"), _date(e.get("cree_le")),
        e.get("__op"), datetime.fromtimestamp(ts / 1000, UTC) if ts else None,
    )

# Crée la table si jamais elle n'existe pas : DDL_ACTIVITES est l'instruction de création (voir ci-dessus)
def preparer_table(conn: psycopg.Connection) -> None:
    """ Crée la table si jamais elle n'existe pas : DDL_ACTIVITES est l'instruction de création (voir ci-dessus)
    """
    # Le curseur ppermet d'exexcuter les instructions sur la bonne base
    with conn.cursor() as cur:
        cur.execute(DDL_ACTIVITES)
    # On commit la base de données une fois que les traitements ont été effectuées
    conn.commit()

# Permet d'écrire dans la base de données un lot de lignes (correspondant au lot de messages chargé d'un topic)
def charger_lot(conn: psycopg.Connection, lignes: list[tuple], debut: datetime) -> None:
    """Upsert d'un lot + trace dans monitoring.pipeline_runs, dans UNE transaction."""
    # Toujours avec le curseur va executer les instructions sur la bonne base, on va insérer les lignes par lot 
    with conn.cursor() as cur:
        # Le upsert semble être inserte qui se transforme en update si il y a un conflit sur un champs précis (ici id_activite)
        cur.executemany(UPSERT, lignes)
        # On va également inserer une ligne dans la table monitoring.pipeline_runs qui permet de visualiser le pipeline des donées
        # Cette table va également recevoir des infos de la partie ingestion ainsi que celle de la validation des distances (geo)
        cur.execute(
            """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes)
               VALUES ('chargement_activites', %s, now(), 'succes', %s)""",
            (debut, len(lignes)),
        )
    # On commit la base de données une fois que les traitements ont été effectuées
    conn.commit()
