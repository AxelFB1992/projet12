"""Contrôles de qualité des données (Soda Core).

Usage :
    uv run --env-file .env python -m projet12.qualite              # tous les contrôles
    uv run --env-file .env python -m projet12.qualite --seulement raw

Code de sortie : 0 si aucun échec (les avertissements sont acceptés), 1 sinon.
Kestra s'en servira pour arrêter le pipeline avant de publier des chiffres faux.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

from projet12.config import connexion_dwh
from projet12.qualite.controles import CONTROLES, enregistrer, lancer_scan

log = logging.getLogger("qualite")

SYMBOLES = {"pass": "✅", "warn": "⚠️ ", "fail": "❌", "erreur": "💥"}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("soda").setLevel(logging.WARNING)   # Soda est très bavard

    parser = argparse.ArgumentParser(prog="python -m projet12.qualite",
                                     description="Contrôles de qualité des données (Soda).")
    parser.add_argument("--seulement", choices=list(CONTROLES),
                        help="Ne lancer qu'un fichier de contrôles")
    args = parser.parse_args()

    a_lancer = {args.seulement: CONTROLES[args.seulement]} if args.seulement else CONTROLES
    debut = datetime.now(UTC)
    resultats, erreurs = [], []
    for fichier, data_source in a_lancer.items():
        log.info("🔎 Contrôles %s (%s)", fichier, data_source)
        res, err = lancer_scan(fichier, data_source)
        for r in res:
            if r.resultat != "pass":
                log.warning("   %s %s.%s : %s (valeur : %s)", SYMBOLES.get(r.resultat, "?"),
                            r.data_source, r.table_verifiee, r.controle, r.valeur)
        for e in err:
            log.error("   💥 %s", e)
        log.info("   %d contrôle(s), %d OK", len(res), sum(r.resultat == "pass" for r in res))
        resultats += res
        erreurs += err

    with connexion_dwh() as conn:
        statut = enregistrer(conn, resultats, erreurs, debut, datetime.now(UTC))
    return 0 if statut == "succes" else 1


if __name__ == "__main__":
    sys.exit(main())
