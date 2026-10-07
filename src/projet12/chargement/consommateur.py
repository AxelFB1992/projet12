"""Consommateur Redpanda -> entrepôt (dwh.raw.activites).

Lit TOUT le topic (historique + live) par lots et le charge dans l'entrepôt.
Ordre de validation : 1) transaction Postgres, 2) position Kafka.
En cas d'arrêt entre les deux, le lot est relu au redémarrage ; grâce à
l'upsert, cela ne crée aucun doublon (traitement idempotent).
"""

import logging
import signal
from datetime import UTC, datetime

from confluent_kafka import Consumer

from projet12.chargement.entrepot import (
    charger_lot,
    evenement_vers_ligne,
    preparer_table,
)
from projet12.config import connexion_dwh

log = logging.getLogger("chargement")

TAILLE_LOT = 500


def consommer(bootstrap: str, topic: str) -> None:
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": "dwh-loader",
        # Premier démarrage : on lit le topic depuis le DÉBUT (tout l'historique)
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([topic])

    en_cours = True

    def arreter(*_):
        nonlocal en_cours
        en_cours = False

    signal.signal(signal.SIGINT, arreter)
    signal.signal(signal.SIGTERM, arreter)

    total = 0
    with connexion_dwh() as conn:
        preparer_table(conn)
        log.info("En écoute sur %s (%s), chargement dans dwh.raw.activites", topic, bootstrap)
        try:
            while en_cours:
                messages = consumer.consume(num_messages=TAILLE_LOT, timeout=1.0)
                if not messages:
                    continue
                debut = datetime.now(UTC)

                # Dédoublonnage dans le lot : si une même activité apparaît deux fois,
                # on garde la version la plus récente (la dernière lue)
                lignes = {}
                for msg in messages:
                    if msg.error():
                        log.error("Erreur Kafka : %s", msg.error())
                        continue
                    ligne = evenement_vers_ligne(msg.value())
                    if ligne:
                        lignes[ligne[0]] = ligne

                if lignes:
                    try:
                        charger_lot(conn, list(lignes.values()), debut)
                    except Exception:
                        conn.rollback()
                        log.exception("Échec du chargement : arrêt sans valider la position Kafka")
                        raise
                    total += len(lignes)
                    log.info("📥 %d activité(s) chargée(s) (total de la session : %d)", len(lignes), total)

                consumer.commit(asynchronous=False)   # après la base, jamais avant
        finally:
            consumer.close()
            log.info("Arrêt : %d activité(s) chargée(s) pendant la session", total)
