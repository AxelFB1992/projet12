"""Point d'entrée en ligne de commande du générateur d'activités.

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


def commande_backfill(args: argparse.Namespace) -> int:
    salaries = charger_salaries(FICHIER_RH, FICHIER_SPORT)
    log.info("%d salariés chargés depuis les fichiers RH", len(salaries))

    with connexion_app() as conn:
        deja = compter_par_source(conn, "backfill")
        if deja:
            # Le rôle app_writer ne peut pas supprimer de lignes (sécurité) :
            # on refuse plutôt que de créer des doublons.
            log.error(
                "%d activités d'historique existent déjà. Pour regénérer, "
                "remets la base à zéro (docker compose down -v).", deja,
            )
            return 1

        activites = generer_historique(
            salaries,
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


def commande_live(args: argparse.Namespace) -> int:
    salaries = charger_salaries(FICHIER_RH, FICHIER_SPORT)
    rng = random.Random()

    with connexion_app() as conn:
        while True:
            activites = generer_live(salaries, args.n, datetime.now(TZ), rng)
            inserer_activites(conn, activites)
            for a in activites:
                distance = f"{a.distance_m / 1000:.1f} km" if a.distance_m else "-"
                log.info("🏃 Salarié %s : %s, %s", a.id_salarie, a.type_activite, distance)
            if args.intervalle <= 0:
                return 0
            time.sleep(args.intervalle)   # mode boucle : Ctrl+C pour arrêter


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m projet12.generation",
        description="Génère des activités sportives simulées (façon Strava).",
    )
    sous = parser.add_subparsers(dest="commande", required=True)

    p_backfill = sous.add_parser("backfill", help="Historique des 12 derniers mois")
    p_backfill.add_argument("--jours", type=int, default=365, help="Durée de l'historique (défaut : 365)")
    p_backfill.add_argument("--graine", type=int, default=42, help="Graine aléatoire, pour un résultat reproductible (défaut : 42)")
    p_backfill.add_argument("--taux-anomalies", type=float, default=0.0, help="Part d'activités volontairement erronées, ex. 0.01 (défaut : 0)")
    p_backfill.set_defaults(func=commande_backfill)

    p_live = sous.add_parser("live", help="Activités qui viennent de se terminer")
    p_live.add_argument("--n", type=int, default=1, help="Nombre d'activités par envoi (défaut : 1)")
    p_live.add_argument("--intervalle", type=int, default=0, help="Secondes entre deux envois ; 0 = un seul envoi (défaut : 0)")
    p_live.set_defaults(func=commande_live)

    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        log.info("Arrêt demandé")
        return 0


if __name__ == "__main__":
    sys.exit(main())
