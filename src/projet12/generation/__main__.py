"""Point d'entrée en ligne de commande du générateur d'activités.

Contient deux méthodes principales commande_backfill et commande_live correspondant aux deux commandes que l'on pourra taper dans le terminal :
-uv run python -m projet12.generation backfil
-uv run python -m projet12.generation live

Ces deux commandes commencent par appeler la méthode main() qui se charge de transformer les commandes en objet et de déterminer laquelle des deux méthodes va être appelé

Exemples :
    uv run python -m projet12.generation backfill
    uv run python -m projet12.generation backfill --graine 42 --taux-anomalies 0.01
    uv run python -m projet12.generation live --n 3
    uv run python -m projet12.generation live --n 1 --intervalle 30
"""

import argparse
import logging
import random
import sys
import time
from collections import Counter
from datetime import datetime

from projet12.config import FICHIER_RH, FICHIER_SPORT, connexion_app
from projet12.generation.ecriture import compter_par_source, inserer_activites
from projet12.generation.generateur import (
    TZ,
    charger_salaries,
    generer_historique,
    generer_live,
)

log = logging.getLogger("generation")

#-----------------------------------Commande Backfill : génération de l'historique------------------------------------------
# Permet de générer un historique grâce à la méthode 'generer_historique' de generateur.py et de l'écrire dans la base de données grâce à inserer_activites de ecriture.py
def commande_backfill(args: argparse.Namespace) -> int:
    """
    Cette méthode réalise dans l'ordre les actions suivantes :
    - Se connecter à la base de données
    - Vérifier si il y a déjà un historique
    - Si il n'y en a pas, en générer un via la méthode 'generer_historique' de generateur.py
    - L'écrire dans la base de données grâce à inserer_activites de ecriture.py
    - Résumer les données générées en faisant une synthèse par salarié
    """
    salaries = charger_salaries(FICHIER_RH, FICHIER_SPORT)
    log.info("%d salariés chargés depuis les fichiers RH", len(salaries))

    # On se connecte à la base de données grâce à la méthode connexion_app() du fichier config.py qui retourne un objet de type connexion (conn)
    with connexion_app() as conn:
        deja = compter_par_source(conn, "backfill")
        # Si il y a déjà une ligne correspondant à l'historique, cela veut dire que celui ci a déjà été ecrit et on arrête le processus ici
        if deja:
            # Le rôle app_writer ne peut pas supprimer de lignes (sécurité) :
            # on refuse plutôt que de créer des doublons.
            log.error(
                "%d activités d'historique existent déjà. Pour regénérer, "
                "remets la base à zéro (docker compose down -v).", deja,
            )
            return 1

        # La liste des activités retournées par la méthode generer_historique (voir generateur.py)
        activites = generer_historique(
            salaries,
            #Ici se trouve la date de fin : C'est bien la date à laquelle on génère l'historique (ce qui est normal)
            fin=datetime.now(TZ),
            jours=args.jours,
            graine=args.graine,
            taux_anomalies=args.taux_anomalies,
        )
        inserer_activites(conn, activites)

    # Petit résumé, utile pour vérifier la cohérence de la simulation
    par_salarie = Counter(a.id_salarie for a in activites)
    seuil = 15
    log.info("✅ %d activités insérées sur %d jours", len(activites), args.jours)
    log.info(
        "   %d salariés ont au moins une activité, dont %d avec %d activités ou plus",
        len(par_salarie), sum(1 for n in par_salarie.values() if n >= seuil), seuil,
    )
    for type_activite, nb in Counter(a.type_activite for a in activites).most_common():
        log.info("   %-16s %5d", type_activite, nb)
    return 0

#-----------------------------------Commande Live : génération d'activité en direct------------------------------------------
# Permet de générer quelques activités à la méthode 'generer_live' de generateur.py et de l'écrire dans la base de données grâce à inserer_activites de ecriture.py
def commande_live(args: argparse.Namespace) -> int:
    """
    Cette méthode réalise dans l'ordre les actions suivantes :
    - Se connecter à la base de données
    - Générer autant d'activités que le nombre demandés en paramètres (args.n)
    - L'écrire dans la base de données grâce à inserer_activites de ecriture.py
    - Afficher les informations des activités avec : l'id du salarié, le type d'activité et la distance si tel est le cas
    - Boucler sur la génération live des activités si l'argument "--intervalle" a été renseigné
    """

    # On charge les informations de toutes les salariés via la méthode charger_salaries de generateur.py
    salaries = charger_salaries(FICHIER_RH, FICHIER_SPORT)
    rng = random.Random()

    with connexion_app() as conn:
        while True:
            # On génère un nombre d'activité définies par l'argument args.n
            activites = generer_live(salaries, args.n, datetime.now(TZ), rng)
            # On écrit ces activités dans la base de données
            inserer_activites(conn, activites)
            # Et on affiche un petit récapitulatif pour chacune des activités
            for a in activites:
                distance = f"{a.distance_m / 1000:.1f} km" if a.distance_m else "-"
                log.info("🏃 Salarié %s : %s, %s", a.id_salarie, a.type_activite, distance)
            if args.intervalle <= 0:
                return 0
            time.sleep(args.intervalle)   # mode boucle : Ctrl+C pour arrêter

#-----------------------------------Méthode MAIN-------------------------------------------------------------------------------
# Permet de déterminer quelle commande a été tapé dans le terminal et d'executer celle-ci grâce aux deux méthodes définies précedemment
def main() -> int:
    """
    Cette méthode réalise dans l'ordre les actions suivantes :
    - Genère un parseur principal permetannt d'analyser les commandes écrites dans le terminal :
        - Il découpera automatiquement la partie principale de la commande ("python -m projet12.generation") et la met de côté en tant que 'prog'
        - Il générera une description associé (si le programme correspond bien à python -m projet12.generation)
    - Génère un sous-parseurs afin d'analyser les sous commandes passés en paramètre (obligatoire) de la commande principale (backfill/live)
    - Génère deux sous-parseurs à partir du précédent :
        - Un qui permettra de recevoir et d'analyser les arguments de la commande "backfill"
        - Un qui permettra de recevoir et d'analyser les arguments de la commande "live"
    - Effectuer l'analyse et l'aiguillage de la ligne de commande et de renvoyer un objet Namespace (args) contenant les traitements (méthode) à appliquer
    - Execute la méthode adéquate en fonction de ce qui a été renseigné en ligne de commande grâce à args.func(args) qui associe des mots à des méthodes
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Parseur principal, de premier niveau : se charge de reconnaître la commande python -m projet12.generation (seule commande que notre application peut executer)
    parser = argparse.ArgumentParser(
        prog="python -m projet12.generation",
        description="Génère des activités sportives simulées (façon Strava).",
    )

    # Parseur secondaire : permet de reconnaitre la commande de deuxième niveau et de savoir quelle méthode executer : backfill ou live. 
    sous = parser.add_subparsers(dest="commande", required=True)

    # Parseurs tertiaires : pour chacune des deux méthodes possibles (backfill ou live), permet d'analyser et de stocker les arguments pour les passer en paramètre des méthodes

    # Parseur tertiaire pour reconnaitre les arguments de la commande backfill et de la passer en paramètre de la méthode associée
    p_backfill = sous.add_parser("backfill", help="Historique des 12 derniers mois")
    p_backfill.add_argument("--jours", type=int, default=365, help="Durée de l'historique (défaut : 365)")
    p_backfill.add_argument("--graine", type=int, default=42, help="Graine aléatoire, pour un résultat reproductible (défaut : 42)")
    p_backfill.add_argument("--taux-anomalies", type=float, default=0.0, help="Part d'activités volontairement erronées, ex. 0.01 (défaut : 0)")
    p_backfill.set_defaults(func=commande_backfill)

    # Parseur tertiaire pour reconnaitre les arguments de la commande backfill et de la passer en paramètre de la méthode associée
    p_live = sous.add_parser("live", help="Activités qui viennent de se terminer")
    p_live.add_argument("--n", type=int, default=1, help="Nombre d'activités par envoi (défaut : 1)")
    p_live.add_argument("--intervalle", type=int, default=0, help="Secondes entre deux envois ; 0 = un seul envoi (défaut : 0)")
    p_live.set_defaults(func=commande_live)

    # Analyse et aiguille la commande grâce au parseur principal ainsi qu'à tous ses parseurs secondaires
    args = parser.parse_args()
    try:
        # Appel la fonction associée à la sous-commande : commande_backfill ou commande_live
        return args.func(args)
    # S'arrête lorsque l'utilisateur interrpompt le principal à l'aide du clavier (dans le cas d'une boucle live)
    except KeyboardInterrupt:
        log.info("Arrêt demandé")
        return 0


if __name__ == "__main__":
    sys.exit(main())
