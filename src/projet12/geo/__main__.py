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

# On crée un logger intitulé geo, toujours pour afficher et les logs et qu'un autre outils puisse les récuperer facilement
log = logging.getLogger("geo")

# Seuils de la note de cadrage, utilisés ici pour un simple APERÇU (on affiche cela à la fin du calcul des distances, via les logs).
# La règle officielle est appliquée dans dbt à partir de la table de paramètres.
# Au dela de 15 km pour de la marche, et au déla de 25 km pour du vélo, c'est incohérent
SEUILS_APERCU_M = {"WALK": 15_000, "BICYCLE": 25_000}


def main() -> int:
    # On configure le logger au plus bas niveau (toutes les informations sont affichées)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # n'affiche pas les URL appelées
    # Un parseur de commande, comme pour toutes les interfaces main.py afin d'interpreter la commande et ses arguments passés en paramètre
    parser = argparse.ArgumentParser(prog="python -m projet12.geo",
                                     description="Distances domicile-travail (Google Routes API).")
    # Le seul argument que cette interface peut prendre en compte est "--force" permettant de forceer le recalcul des distances
    # mêmes si celles-ci ont déjà été calculées dans la base de données geo.distances_domicile_travail, distances.py trajets_a_calculer 
    # va les intégrer dans les trajets à calculer si --force (booleen forcer dans la méthode)
    parser.add_argument("--force", action="store_true", help="Recalcule toutes les distances")
    # Le modèle a été définie, parse_args() permet de l'appliquer sur la vraie commande passée en paramètre
    args = parser.parse_args()
    # On avait fait une fonction spéciale pour début auparavant (maintenant()) mais pas vraiment nécessaire au final
    debut = datetime.now(UTC)
    # On se ressert encore de connexion_dwh pour se connecter à la base dwh en vu de l'écriture des résultats
    with connexion_dwh() as conn:
        # On crée la table qui va recevoir les résultats (geo.distances_domicile_travail) si jamais elle n'existe pas
        preparer_table(conn)
        # On récupère les trajets à calculer ainsi que le nombre de trajets pour lesquels la distance est déjà calculé 
        trajets, en_cache = trajets_a_calculer(conn, forcer=args.force)
        # On inscrit dans les logs le nombre de trajets à calculer et ceux déjà en cache
        log.info("%d trajet(s) à calculer, %d déjà en cache", len(trajets), en_cache)
        if not trajets:
            return 0
        # On utilise un client de protocole httpx (sans message d'erreur) pour faire la requête auprès de l'API (via calculer/calculer_par_lot)
        with httpx.Client(timeout=30) as client:
            lignes = calculer(client, cle_google(), trajets, ADRESSE_ENTREPRISE)
        # Si aucune erreur n'a été levé et que le programme n'a pas été interrompu, alors le résultat est valide et on peut l'écrire
        enregistrer(conn, lignes, debut)

    # On stocke les différents statuts de la réponse pour chacun des éléments 
    statuts = {}
    # Ces deux lignes permettent de compter le nombre de trajets par statut (à gauche le statut du dictionnaire, à droite le nombre associé)
    for ligne in lignes:
        statuts[ligne[5]] = statuts.get(ligne[5], 0) + 1

    # On affiche dans les logs le nombre de distances enregistrées
    log.info("✅ %d distance(s) enregistrée(s) : %s", len(lignes), statuts)

    # Et, dans le cadre d'un petit aperçu, on va récupérer les distances suspectes par rapport à ce qui a été renseigné par le salariés
    # Pour information l[2] correspond au moyen de déplacement de l'individu pointé par la ligne l.
    suspects = [l for l in lignes if l[3] and l[3] > SEUILS_APERCU_M[l[2]]]
    # Et on affiche le nombre de distances suspectes dans les logs...
    log.info("Aperçu : %d déclaration(s) au-delà des seuils (15 km à pied, 25 km à vélo)", len(suspects))
    for id_salarie, _, mode, distance_m, _, _ in sorted(suspects, key=lambda l: -l[3]):
        # Puis on affiche ensuite les informations sur chacun des salariés suspect, dans l'ordre decroissant des distances (du + grand au + petit)
        log.info("   salarié %s : %.1f km en %s", id_salarie, distance_m / 1000, mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
