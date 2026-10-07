"""Calcule les distances domicile-travail avec l'API Google Routes.

    uv run python -m projet12.geo            # seulement les distances manquantes ou périmées
    uv run python -m projet12.geo --force    # recalcule tout
"""

import argparse
import logging
import sys

import httpx

from projet12.config import ADRESSE_ENTREPRISE, cle_google, connexion_dwh
from projet12.geo.distances import (
    calculer,
    enregistrer,
    maintenant,
    preparer_table,
    trajets_a_calculer,
)

log = logging.getLogger("geo")

# Seuils de la note de cadrage, utilisés ici pour un simple APERÇU.
# La règle officielle est appliquée dans dbt à partir de la table de paramètres.
SEUILS_APERCU_M = {"WALK": 15_000, "BICYCLE": 25_000}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # n'affiche pas les URL appelées
    parser = argparse.ArgumentParser(prog="python -m projet12.geo",
                                     description="Distances domicile-travail (Google Routes API).")
    parser.add_argument("--force", action="store_true", help="Recalcule toutes les distances")
    args = parser.parse_args()

    debut = maintenant()
    with connexion_dwh() as conn:
        preparer_table(conn)
        trajets, en_cache = trajets_a_calculer(conn, forcer=args.force)
        log.info("%d trajet(s) à calculer, %d déjà en cache", len(trajets), en_cache)
        if not trajets:
            return 0

        with httpx.Client(timeout=30) as client:
            lignes = calculer(client, cle_google(), trajets, ADRESSE_ENTREPRISE)
        enregistrer(conn, lignes, debut)

    statuts = {}
    for ligne in lignes:
        statuts[ligne[5]] = statuts.get(ligne[5], 0) + 1
    log.info("✅ %d distance(s) enregistrée(s) : %s", len(lignes), statuts)

    suspects = [l for l in lignes if l[3] and l[3] > SEUILS_APERCU_M[l[2]]]
    log.info("Aperçu : %d déclaration(s) au-delà des seuils (15 km à pied, 25 km à vélo)", len(suspects))
    for id_salarie, _, mode, distance_m, _, _ in sorted(suspects, key=lambda l: -l[3]):
        log.info("   salarié %s : %.1f km en %s", id_salarie, distance_m / 1000, mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
