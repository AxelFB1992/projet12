"""Charge les fichiers RH et sport dans dwh.raw.
    C'est le point d'entrée qui correspond à la commande
    uv run python -m projet12.ingestion
"""

import logging
import sys

# Les chemins des fichiers des données RH et sportives sont toujours dans le fichier projet12.config
from projet12.config import FICHIER_RH, FICHIER_SPORT, connexion_dwh
# On récuppère les référentiels écrits dans referentiels.py qui nous donne toutes les informations à récuperer et les structures de tables
from projet12.ingestion.referentiels import SALARIES, SPORTS, charger

# Comme toujours, on crée un logger qui va nous permette de récuperer les informations d'execution
log = logging.getLogger("ingestion")


def main() -> int:
    """
    Cette méthode réaliser les tâches suivantes : 
        - Se connecter correctement à la base de données dwh à l'aide de la méthode connexion_dwh()
        - Parcourir tous les fichiers à charger dans la base données et les charger au moyen de la méthode référentiels.py/charger
        - Configurer le logger et afficher les messages de succès et/ou d'erreurs
    """
    # On définit ce logger au niveau maximum d'information (au dessus il y a WARNING et ERROR
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # On utilise la méthode connexion_dwh pour renvoyer un connecteur à la base données dwh correctement paramétré avec les bons rôle et accès
    with connexion_dwh() as conn:
        # Pour tous les fichiers (donc les deux) et pour les deux référentiels (informations à inscrire dans les tables, au bon format)
        for fichier, ref in [(FICHIER_RH, SALARIES), (FICHIER_SPORT, SPORTS)]:
            try:
                # On utilise la méthode référentiels.py/charger pour charger le fichier à l'aide du bon référentiel (donc de la bonne table)
                nb = charger(conn, fichier, ref)
                log.info("✅ %s : %d lignes chargées depuis %s", ref.table, nb, fichier.name)
            except Exception as erreur:  # noqa: BLE001 : point d'entrée, toute erreur = code 1
                log.error("❌ %s : échec, données précédentes conservées (%s)", ref.table, erreur)
                return 1
    # Si tout s'est bien passé et qu'on a réussi à inserer tous les fichiers dans la base dwh à l'aide des référentiels, on retourne 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
