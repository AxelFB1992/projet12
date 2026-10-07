"""Charge les fichiers RH et sport dans dwh.raw.

    uv run python -m projet12.ingestion
"""

import logging
import sys

from projet12.config import FICHIER_RH, FICHIER_SPORT, connexion_dwh
from projet12.ingestion.referentiels import SALARIES, SPORTS, charger

log = logging.getLogger("ingestion")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with connexion_dwh() as conn:
        for fichier, ref in [(FICHIER_RH, SALARIES), (FICHIER_SPORT, SPORTS)]:
            try:
                nb = charger(conn, fichier, ref)
                log.info("✅ %s : %d lignes chargées depuis %s", ref.table, nb, fichier.name)
            except Exception as erreur:  # noqa: BLE001 : point d'entrée, toute erreur = code 1
                log.error("❌ %s : échec, données précédentes conservées (%s)", ref.table, erreur)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
