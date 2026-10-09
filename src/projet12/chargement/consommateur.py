"""Consommateur Redpanda -> entrepôt (dwh.raw.activites).

Lit TOUT le topic Redpanda (historique + live) par lots et le charge dans l'entrepôt.
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
    # A l'instar de la méthode consommer de slack, on creer un consommateur avec des paramètre différents
    #     - Le groupe de consommateur (cluster de lecture) concerne un autre ensemble de données : dwh-loader
    #     - On lit le contenu du topic depuis le début (Tous les messages) au premier démarrage, pas seulement ceux de la fin
    #     - Le boostrap reste le même, c'est le seul broker (serveur) de messages qui reçoit et distribue des messages
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": "dwh-loader",
        # Premier démarrage : on lit le topic depuis le DÉBUT (tout l'historique)
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })

    # Et on fait souscrire ce consommateur à notre topic (app.public.activites dans config.py)
    consumer.subscribe([topic])

    en_cours = True

    # Exactement la même logique que pour la consommation slack
    def arreter(*_):
        nonlocal en_cours
        en_cours = False

    signal.signal(signal.SIGINT, arreter)
    signal.signal(signal.SIGTERM, arreter)

    total = 0
    # la méthode connexion-dwh est une méthode de config.py qui permet de se connecter à la base données dwh sur le postgres conteneurisé
    with connexion_dwh() as conn:
        # Préparer table permet de préparer la table prévue par 'conn' avec un curseur de lecture 
        preparer_table(conn)
        # On affiche les information de connections préferentiellement dans le log de chargement, pour garder une trace
        log.info("En écoute sur %s (%s), chargement dans dwh.raw.activites", topic, bootstrap)
        try:
            while en_cours:
                # On lit les message en lot en fonction de la taille du lot renseigné (500), pas besoin de faire un par un ici.
                messages = consumer.consume(num_messages=TAILLE_LOT, timeout=1.0)
                # Si il n'y a rien de le lot, on passe au tour de boucle suivant sans effectuer les traitelent ci-dessous
                # --> Le consommateur ne s'arrête jamais, lui non plus (pour l'instant)
                if not messages:
                    continue
                debut = datetime.now(UTC)

                # Dédoublonnage dans le lot : si une même activité apparaît deux fois,
                # on garde la version la plus récente (la dernière lue)
                lignes = {}
                # On traite les messages les uns après les autres
                for msg in messages:
                    # Si jamais il y a une erreur sur un message, on le signale et on passe au message suivant
                    if msg.error():
                        log.error("Erreur Kafka : %s", msg.error())
                        continue
                    # Si le message est bon, il faut le préparer pour le charger dans le datawarehouse
                    # Contrairement à SLack où il était mis en forme pour être affiché, il doit ici être mis en forme pour être stocké
                    # Par conséquent, la méthode entrepot.py/evenement_vers_ligne retourne un tuple (sql ?) prêt à être stocké
                    ligne = evenement_vers_ligne(msg.value())
                    # Si la ligne n'est pas nulle, on la charge à la position de l'identifiant renseigné dans le tuple (ligne[0])
                    if ligne:
                        lignes[ligne[0]] = ligne
                # Lorsque tous les messages ont été traités (500 max), on passe au chargement par lot dans la base de données
                if lignes:
                    try:
                        # On utilise la méthode charger-lot pour inscrire les messages traités par lot dans la base de données
                        # Ces messages viennent de l'historique du topic RedPanda et non d'une base données
                        # Ils sont traités par lot de 500 au maximum
                        charger_lot(conn, list(lignes.values()), debut)
                    except Exception:
                        conn.rollback()
                        log.exception("Échec du chargement : arrêt sans valider la position Kafka")
                        raise
                    # Calcul le total des lignes chargés depuis le début de la session et du processus consommateur de chargement
                    total += len(lignes)
                    log.info("📥 %d activité(s) chargée(s) (total de la session : %d)", len(lignes), total)
                # Pour sauvegarder la position du consommateur avant l'arrêt
                consumer.commit(asynchronous=False)   # après la base, jamais avant
        finally:
            consumer.close()
            log.info("Arrêt : %d activité(s) chargée(s) pendant la session", total)
