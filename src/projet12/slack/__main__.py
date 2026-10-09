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

# Crée ou récupuère le logger nommé "Slack"/ C'est juste une autre moyen que le print d'afficher des logs / Rien à voir avec l'application Slack
log = logging.getLogger("slack")


def main() -> int:
    """
    La méthode main réalise les actions suivantes :
        - Configurer le logger pour afficher les logs (info, warnings, errors)
        - Parser la commande passée en paramètres et récupérer les arguments.
        - Récuperer les paramètres d'environnement (webhook)
        - Tester les arguments (--dry-run) et paramètres d'environnements (webhook)
        - Lancer la méthode consommateur.py/consommer(bootstrap, topic, noms_salaries, webhook, dry_run) qui tourne en continu.
    Une fois que la méthode consommateur.py/consommer sera arrivé à son terme, le script main.py arrêtera son execution.
    """
    # Les deux lignes ci-dessous configurent l'affichage des logs
    # Celle-ci indique le niveau minimale d'information pour les logs (pas de message de DEBUG)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Celle-ci gère un paramètre de sécurité : httpx journalise l'URL de chaque requête, donc l'URL secrète du webhook
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Le parseur de la commande passé en paramètre lors de l'appel de l'application slack et donc de la méthode main.py
    parser = argparse.ArgumentParser(prog="python -m projet12.slack",
                                     description="Publie les nouvelles activités dans Slack.")
    # Ajoute un paramètre POSSIBLe (pas forcement utilisé) pour l'appel de l'application Slack
    parser.add_argument("--dry-run", action="store_true", help="Affiche les messages sans les envoyer")
    args = parser.parse_args()

    webhook = os.getenv("SLACK_WEBHOOK_URL")
    # Si il n'y a ni argument avec le webhook (slack) si argument --dry-run, on arrête là en affichant un message d'erreur.
    if not webhook and not args.dry_run:
        log.error("SLACK_WEBHOOK_URL manquant dans le .env (ou utilise --dry-run)")
        return 1

    # Un message doit être consommé quant bien même le paramètre 'dry-run' est renseigné, c'est juste qu'il n'écrira pas dans slack
    consommer(
        # Il peut y avoir plusieurs Brokers pour un serveur Kafka. Chaque broker a normalement une adresse IP et l'interface commune
        # à tous les brokers est normalement l'addresse de premier contact (commune à tous) aussi connu sous le nomd de bootstrap server
        bootstrap=os.getenv("KAFKA_BOOTSTRAP", "localhost:19092"),
        # Ici la variable TOPIC_ACTIVITES n'existe pas, donc c'est la valeur par défaut ("app.public.activites") qui va être appliqué
        topic=os.getenv("TOPIC_ACTIVITES", "app.public.activites"),
        noms=charger_noms(FICHIER_RH),
        webhook_url=webhook,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
