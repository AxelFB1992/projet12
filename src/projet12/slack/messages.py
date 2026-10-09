"""Construction des messages Slack à partir d'un événement d'activité.

Module « pur » : pas de réseau, pas de Kafka. Il transforme un message JSON
reçu de Redpanda en texte Slack (ou None si l'activité ne doit pas être publiée).
"""

import json
import random
from datetime import datetime

# Seules les activités "live" sont publiées : l'historique (backfill) est ignoré.
SOURCES_PUBLIEES = {"live", "strava"}
# __op = "c" : nouvelle insertion. On ignore le snapshot ("r"), les mises à jour, etc.
OPERATIONS_PUBLIEES = {"c"}

# Messages par type d'activité : {nom} = "Prénom Nom", {distance} = "10,8 km", {duree} = "46 min"
MODELES_DISTANCE = {
    "Course à pied": ["Bravo {nom} ! Tu viens de courir {distance} en {duree} ! Quelle énergie !"],
    "Randonnée": ["Magnifique {nom} ! Une randonnée de {distance} terminée en {duree} !"],
    "Vélo": ["Belle sortie {nom} ! {distance} à vélo en {duree}"],
    "Natation": ["Splash ! {nom} vient de nager {distance} en {duree}"],
    "Marche": ["Bien joué {nom} ! {distance} de marche en {duree}"],
    "Voile": ["Bon vent {nom} ! {distance} de navigation en {duree}"],
    "Équitation": ["Au galop {nom} ! {distance} à cheval en {duree}"],
}
# Messages pour les spors avec des distances, sans que celui-ci ne soit précisé. Utilisé aléatoirement avec le modèle précédent.
MODELE_DISTANCE_DEFAUT = "Bravo {nom} ! {distance} {de_sport} en {duree} !"
# Mêmes messages, mais sans la notion de distance 
MODELE_SANS_DISTANCE = "Bravo {nom} ! {duree} {de_sport}, quelle séance !"

# Transforme les intitulés des sports dans distance avec la bonne formulation
def de_sport(sport: str) -> str:
    """
    # Mêmes messages, mais sans la notion de distance 
    'tennis' -> 'de tennis' ; 'escalade' -> "d'escalade" (élision devant une voyelle)."""
    sport = sport.lower()
    return f"d'{sport}" if sport[0] in "aeéèêiouyh" else f"de {sport}"

# Lorsqu'il y a plus de 1000m, on exprime la distance en Kilomètre. Sinon on rajoute simplement 'm'
def formater_distance(metres: int) -> str:
    """
    # Lorsqu'il y a plus de 1000m, on exprime la distance en Kilomètre. Sinon on rajoute simplement 'm'
    10879 -> '10,9 km' ; 800 -> '800 m'."""
    if metres < 1000:
        return f"{metres} m"
    return f"{metres / 1000:.1f} km".replace(".", ",")

# Même chose pour la durée, en fonction de son ordre de grandeur, soit on la formate en heures, soit on la garde en minutes
def formater_duree(secondes: int) -> str:
    """
    Même chose pour la durée, en fonction de son ordre de grandeur, soit on la formate en heures, soit on la garde en minutes
    2760 -> '46 min' ; 3900 -> '1 h 05'."""
    minutes = round(secondes / 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"

# Fonction simple qui permet simplement de déterminer si l'évenement doit être publié sur Slack
# Si il s'agit de l'historique (backfille) alors il ne faut pas le publier et on retourne false. Sinon True.
def doit_etre_publie(evenement: dict) -> bool:
    """
    # Fonction simple qui permet simplement de déterminer si l'évenement doit être publié sur Slack
    # Si il s'agit de l'historique (backfille) alors il ne faut pas le publier et on retourne false. Sinon True.
    """
    return (
        evenement.get("__op") in OPERATIONS_PUBLIEES
        and evenement.get("source") in SOURCES_PUBLIEES
    )

# Cette méthode utilise, entre autre, les 3 méthodes précedentes (formater_duree, de_sport, formater_distance) pour formatter un message en texte
def construire_message(evenement: dict, noms: dict[int, str], rng: random.Random | None = None) -> str:
    """
    Cette méthode utilise, entre autre, les 3 méthodes précedentes (formater_duree, de_sport, formater_distance) pour formatter un message en texte
    Construit le texte Slack d'une activité."""
    #
    rng = rng or random.Random()
    # On récupère toutes les caractères de l'évenement dans son dictionnaire
    # Son dictionnaire correspond au message JSON que nous avions structurer par balise au niveau du générateur
    nom = noms.get(evenement["id_salarie"], "Un collègue")
    sport = evenement["type_activite"]
    # On utilise les méthode fromisoformat de datetime pour transformer les date en datetime
    debut = datetime.fromisoformat(evenement["date_debut"])
    fin = datetime.fromisoformat(evenement["date_fin"])
    duree = formater_duree(int((fin - debut).total_seconds()))

    distance_m = evenement.get("distance_m")
    if distance_m:
        # On choisit aléatoirement en une phrase personnalisé et une phrase non personnalisée.
        modele = rng.choice(MODELES_DISTANCE.get(sport, [MODELE_DISTANCE_DEFAUT]))
        # Quel que soit le modèle retenu, on remplace les {} de la phrase par les vraies valeurs grâce à la méthode format.
        texte = modele.format(nom=nom, de_sport=de_sport(sport),
                              distance=formater_distance(distance_m), duree=duree)
    else:
        # De même pour les modèles sans distance
        texte = MODELE_SANS_DISTANCE.format(nom=nom, de_sport=de_sport(sport), duree=duree)
    # Si il y a un commentaire dans le message JSON, on le rajoute
    if evenement.get("commentaire"):
        texte += f' ("{evenement["commentaire"]}")'
    return texte

# La méthode principale appelée par consommateur.py/consommer pour formatter le message
def traiter_evenement(valeur: bytes | None, noms: dict[int, str]) -> str | None:
    """
    La méthode principale appelée par consommateur.py/consommer pour formatter le message :
    Message Redpanda brut -> texte Slack, ou None s'il ne faut rien publier.
    """
    # Si il n'y a pas de message dans l'evenement reçu de Redpanda, on retourne None
    if valeur is None:          # message vide (tombstone) : rien à faire
        return None
    # Sinon on le depile grâce à json.loads...
    evenement = json.loads(valeur)
    # Si il ne doit pas être publié, on ne retourne rien (Attention, cette condition n'a rien à voir avec dry-run)
    # En effet, un message dry-run ne retourne pas rien, car il a, à la base, les caractértistiques pour être publié
    if not doit_etre_publie(evenement):
        return None
    # ... Et on le formatte en le retournant grâce à la méthode construire_message (voir précedemment)
    return construire_message(evenement, noms)
