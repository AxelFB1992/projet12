"""Lance le consommateur Slack.

Exemples :
    uv run python -m projet12.slack            # publie dans Slack
    uv run python -m projet12.slack --dry-run  # affiche les messages sans les envoyer
"""

import argparse
import logging
import os
import sys

from projet12.config import FICHIER_RH
from projet12.slack.consommateur import charger_noms, consommer

log = logging.getLogger("slack")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Sécurité : httpx journalise l'URL de chaque requête, donc l'URL secrète du webhook
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="python -m projet12.slack",
                                     description="Publie les nouvelles activités dans Slack.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les messages sans les envoyer")
    args = parser.parse_args()

    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook and not args.dry_run:
        log.error("SLACK_WEBHOOK_URL manquant dans le .env (ou utilise --dry-run)")
        return 1

    consommer(
        bootstrap=os.getenv("KAFKA_BOOTSTRAP", "localhost:19092"),
        topic=os.getenv("TOPIC_ACTIVITES", "app.public.activites"),
        noms=charger_noms(FICHIER_RH),
        webhook_url=webhook,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
