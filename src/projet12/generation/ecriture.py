"""Écriture des activités dans la base source 'app'."""

import psycopg

from projet12.generation.generateur import Activite

COLONNES = (
    "id_salarie", "date_debut", "type_activite", "distance_m",
    "date_fin", "commentaire", "source",
)

#Dans la mesure ou les méthodes principales du script generateur.py ne retourne que des listes d'activités, il faut bien les écrire !
def inserer_activites(conn: psycopg.Connection, activites: list[Activite]) -> int:
    """Insère les activités en une seule transaction, avec COPY
    (beaucoup plus rapide que des INSERT ligne par ligne)."""
    # On prépare la requête d'écrire avec ce qui va être ajoutés (',') concaténés au colonnes
    requete = f"COPY activites ({', '.join(COLONNES)}) FROM STDIN"
    # On attend d'avoir ajouté les différentes lignes correspondant aux activités dans copy avant d'ecrire le contenu complet du curseur avec commit
    # Le curseur est généré à partir de l'objet de connection qui contient déjà les paramètre de connection (psycopg.Connection
    with conn.cursor() as cur, cur.copy(requete) as copy:
        for a in activites:
            copy.write_row((
                a.id_salarie, a.date_debut, a.type_activite, a.distance_m,
                a.date_fin, a.commentaire, a.source,
            ))
    conn.commit()
    # Retourne le nombre d'activités commités en tant que validation
    return len(activites)

# Compter le nombre d'activités présente qui appartiennent soit à l'historique ('backfill') soit à la génération en direct ('live')
def compter_par_source(conn: psycopg.Connection, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM activites WHERE source = %s", (source,))
        return cur.fetchone()[0]
