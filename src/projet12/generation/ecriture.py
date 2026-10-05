"""Écriture des activités dans la base source 'app'."""

import psycopg

from projet12.generation.generateur import Activite

COLONNES = (
    "id_salarie", "date_debut", "type_activite", "distance_m",
    "date_fin", "commentaire", "source",
)


def inserer_activites(conn: psycopg.Connection, activites: list[Activite]) -> int:
    """Insère les activités en une seule transaction, avec COPY
    (beaucoup plus rapide que des INSERT ligne par ligne)."""
    requete = f"COPY activites ({', '.join(COLONNES)}) FROM STDIN"
    with conn.cursor() as cur, cur.copy(requete) as copy:
        for a in activites:
            copy.write_row((
                a.id_salarie, a.date_debut, a.type_activite, a.distance_m,
                a.date_fin, a.commentaire, a.source,
            ))
    conn.commit()
    return len(activites)


def compter_par_source(conn: psycopg.Connection, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM activites WHERE source = %s", (source,))
        return cur.fetchone()[0]
