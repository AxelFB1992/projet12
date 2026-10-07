"""Lance le consommateur de chargement vers l'entrepôt.

    uv run python -m projet12.chargement
"""

import logging
import sys

from projet12.chargement.consommateur import consommer
from projet12.config import KAFKA_BOOTSTRAP, TOPIC_ACTIVITES


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    consommer(KAFKA_BOOTSTRAP, TOPIC_ACTIVITES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
