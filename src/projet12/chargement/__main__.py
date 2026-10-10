"""Lance le consommateur de chargement vers l'entrepôt.

    uv run python -m projet12.chargement
"""

import logging
import sys

from projet12.chargement.consommateur import consommer
from projet12.config import KAFKA_BOOTSTRAP, TOPIC_ACTIVITES


def main() -> int:
    # On paramètre le logger de la même manière que pour consommateur.py, afin d'afficher le minimum d'information
    # On pourra récuperer ces logs grâce aux commandes docker compose logs
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Et on lance la méthode consommer qui, comme pour slack, tourne et charge les lots de messages en continu tant qu'on ne l'interromps pas
    consommer(KAFKA_BOOTSTRAP, TOPIC_ACTIVITES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
