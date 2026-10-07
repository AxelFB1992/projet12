"""Consommateur Redpanda -> Slack.

Lit le topic des activités en continu et publie un message Slack pour chaque
nouvelle activité "live".

Garantie de livraison : le message Kafka n'est validé (commit) qu'APRÈS l'envoi
Slack réussi. En cas d'arrêt brutal entre les deux, l'activité serait renvoyée
au redémarrage (doublon possible, mais jamais de perte) : "at-least-once".
"""

import logging
import signal
import time
from pathlib import Path

import httpx
import pandas as pd
from confluent_kafka import Consumer, KafkaError

from projet12.slack.messages import traiter_evenement

log = logging.getLogger("slack")


def charger_noms(fichier_rh: Path) -> dict[int, str]:
    """{id_salarie: "Prénom Nom"}, lu dans le fichier RH (colonnes nom/prénom seulement)."""
    rh = pd.read_excel(fichier_rh, usecols=["ID salarié", "Nom", "Prénom"])
    return {
        int(id_): f"{prenom} {nom}"
        for id_, nom, prenom in zip(rh["ID salarié"], rh["Nom"], rh["Prénom"])
    }


def envoyer_slack(client: httpx.Client, url: str, texte: str, tentatives: int = 3) -> None:
    """Envoie un message au webhook, avec quelques nouvelles tentatives en cas d'échec."""
    for tentative in range(1, tentatives + 1):
        try:
            reponse = client.post(url, json={"text": texte})
            if reponse.status_code == 429:   # trop de messages : Slack indique quand réessayer
                attente = int(reponse.headers.get("Retry-After", "1"))
                log.warning("Limite Slack atteinte, nouvel essai dans %s s", attente)
                time.sleep(attente)
                continue
            reponse.raise_for_status()
            return
        except httpx.HTTPError as erreur:
            # On n'affiche pas le message d'erreur complet : il contient l'URL secrète
            code = getattr(getattr(erreur, "response", None), "status_code", "-")
            log.warning("Échec d'envoi Slack (tentative %d/%d) : %s, code HTTP %s",
                        tentative, tentatives, type(erreur).__name__, code)
            time.sleep(2 ** tentative)
    raise RuntimeError("Slack injoignable après plusieurs tentatives")


def consommer(
    bootstrap: str,
    topic: str,
    noms: dict[int, str],
    webhook_url: str | None,
    dry_run: bool = False,
) -> None:
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        # Groupe de consommateurs : Redpanda retient pour lui la position de lecture
        "group.id": "slack-notifier",
        # Premier démarrage : on part de la FIN du topic (pas de messages pour l'historique)
        "auto.offset.reset": "latest",
        # On valide nous-mêmes, seulement après l'envoi Slack
        "enable.auto.commit": False,
    })
    consumer.subscribe([topic])

    # Arrêt propre sur Ctrl+C ou "docker stop"
    en_cours = True

    def arreter(*_):
        nonlocal en_cours
        en_cours = False

    signal.signal(signal.SIGINT, arreter)
    signal.signal(signal.SIGTERM, arreter)

    log.info("En écoute sur %s (%s)%s", topic, bootstrap, " [dry-run]" if dry_run else "")
    publies = ignores = 0
    with httpx.Client(timeout=10) as client:
        try:
            while en_cours:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.error("Erreur Kafka : %s", msg.error())
                    continue

                texte = traiter_evenement(msg.value(), noms)
                if texte is None:
                    ignores += 1
                else:
                    if dry_run:
                        log.info("[dry-run] %s", texte)
                    else:
                        envoyer_slack(client, webhook_url, texte)
                        log.info("📣 %s", texte)
                    publies += 1
                consumer.commit(message=msg, asynchronous=False)
        finally:
            consumer.close()
            log.info("Arrêt : %d message(s) publié(s), %d ignoré(s)", publies, ignores)
