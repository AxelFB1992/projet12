"""Consommateur Redpanda -> Slack.

Lit le topic des activités en continu et publie un message Slack pour chaque nouvelle activité "live".

Garantie de livraison : le message Kafka n'est validé (commit) qu'APRÈS l'envoi Slack réussi (sauf si l'option 'dry-run' est activé) 
En cas d'arrêt brutal entre les deux, l'activité serait renvoyée au redémarrage (doublon possible, mais jamais de perte) : "at-least-once".
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

# Comme on l'avait vu, cette méthode permet de charger les noms des salariés dans les fichier excel (temporaire)
# A terme, cette méthode disparatra car on ira cherché les noms directements dans le datawarehouse. 
# Les fichiers RH sont chargés grâce à la variable FICHIER_RH de config.py depuis le méthode main() de ce repertoire (slack)
def charger_noms(fichier_rh: Path) -> dict[int, str]:
    """{id_salarie: "Prénom Nom"}, lu dans le fichier RH (colonnes nom/prénom seulement)."""
    rh = pd.read_excel(fichier_rh, usecols=["ID salarié", "Nom", "Prénom"])
    # Comme indiqué en signature, cette méthode retourne un dictionnaire de tuples (identifiant, prenom/nom) pour chaque salairé
    return {
        int(id_): f"{prenom} {nom}"
        for id_, nom, prenom in zip(rh["ID salarié"], rh["Nom"], rh["Prénom"])
    }

# Envoie le message au client httpx (ici Slackà) avec un nombre de tentative en cas d'echecs
def envoyer_slack(client: httpx.Client, url: str, texte: str, tentatives: int = 3) -> None:
    """Envoie un message au webhook, avec quelques nouvelles tentatives en cas d'échec."""
    for tentative in range(1, tentatives + 1):
        try:
            reponse = client.post(url, json={"text": texte})
            # Si on obtient ce message d'erreur...
            if reponse.status_code == 429:   # trop de messages : Slack indique quand réessayer
                attente = int(reponse.headers.get("Retry-After", "1"))
                #... On attend, avant de recommencer
                log.warning("Limite Slack atteinte, nouvel essai dans %s s", attente)
                time.sleep(attente)
                continue
            reponse.raise_for_status()
            # Sinon on s'arrête et on retourne... Rien
            return
        except httpx.HTTPError as erreur:
            # On n'affiche pas le message d'erreur complet : il contient l'URL secrète
            # On récupère seulement le code d'erreur qui nous interresse
            code = getattr(getattr(erreur, "response", None), "status_code", "-")
            log.warning("Échec d'envoi Slack (tentative %d/%d) : %s, code HTTP %s",
                        tentative, tentatives, type(erreur).__name__, code)
            # On on essaie une nouvelle fois
            time.sleep(2 ** tentative)
    raise RuntimeError("Slack injoignable après plusieurs tentatives")


def consommer(bootstrap: str,topic: str,noms: dict[int, str],webhook_url: str | None,dry_run: bool = False,) -> None:
    """ Cette méthode a deux fonctions : 
    - Traiter le message : transformer un message JSON provenant du serveur RedPanda en message slack (Message.py/traiter_evenement)
    - Envoyer le message transformé en format textuel à Slack (consommateur.py/envoyer_slack)
    Ce sont ces deux fonctions que l'on englobe dans la fonction "Consommer" : Lire le message, le transformer et l'envoyer quelque part
    """
    # Consumer est une classe de la librairie confluent_kafka qui permet de lire les message depuis un serveur bootstrap
    consumer = Consumer({
        # Serveur bootstrap = serveur Redpanda --> localhost:19092
        "bootstrap.servers": bootstrap,
        # Groupe de consommateurs : Redpanda retient pour lui la position de lecture
        "group.id": "slack-notifier",
        # Premier démarrage : on part de la FIN du topic (pas de messages pour l'historique)
        "auto.offset.reset": "latest",
        # On valide nous-mêmes, seulement après l'envoi Slack
        "enable.auto.commit": False,
    })
    # Ensuite, on fait souscrire le consommateur au topic (sujet) passé en paramètre et pas à tous les topics gérés par RedPanda.
    consumer.subscribe([topic])

    # Arrêt propre sur Ctrl+C ou "docker stop"
    en_cours = True
    # Fonction qui permet d'arrêter proprement la boucle en passant la variable #en-cours à False / utilisée juste en dessous !
    def arreter(*_):
        # Type non local doit faire référence à une variable de la méthode englobante (directement accesible)
        nonlocal en_cours
        en_cours = False

    # Si il y a un signal SIGINT ou SIGTERM, dans les deux cas, il faut utiliser la fonction arrêter 
    signal.signal(signal.SIGINT, arreter)
    signal.signal(signal.SIGTERM, arreter)

    # Cette boucle ecoute en continu sur le topic et le serveur passés en paramètre 
    # Si le booléen dry-run est vraie, on se contente d'afficher le message transformé dans le terminal
    # Sinon on l'affiche et on et on l'envoit à Slack
    log.info("En écoute sur %s (%s)%s", topic, bootstrap, " [dry-run]" if dry_run else "")
    publies = ignores = 0
    # Le client va être passé en paramètre à envoyer_slack(...) si dry-run est à faux, sinon il ne servira à rien
    with httpx.Client(timeout=10) as client:
        try:
            # Tant qu'on a pas demandé d'arrêter la boucle
            while en_cours:
                # On lit un message...
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.error("Erreur Kafka : %s", msg.error())
                    continue
                # ... Et on le transmet à cette fonction qui va le formatter correctement et enregistrer le resultat sous 'texte'
                texte = traiter_evenement(msg.value(), noms)
                # Si le retour de la méthode est vide, on incrémente seulement le compteur des messages ignorés
                if texte is None:
                    ignores += 1
                else:
                # Sinon on fait le traitement normal à savoir
                # Soit on fait juste un affichage dans le terminal
                # Soit on l'affiche dans le terminal et on l'envoit à Slack
                    if dry_run:
                        log.info("[dry-run] %s", texte)
                    else:
                        envoyer_slack(client, webhook_url, texte)
                        log.info("📣 %s", texte)
                    publies += 1
                # On commite le message le message en signalant qu'on la lu, pour dépalcer le curseur du consommateur
                # Car il peut y avoir plusieurs consommateurs avec des curseurs positionnées à différents endroits
                consumer.commit(message=msg, asynchronous=False)
        # Lorsqu'on sort de la boucle while et donc du try, on execute cette instrcution
        finally:
            consumer.close()
            log.info("Arrêt : %d message(s) publié(s), %d ignoré(s)", publies, ignores)
