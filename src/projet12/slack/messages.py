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
    "Course à pied": ["Bravo {nom} ! Tu viens de courir {distance} en {duree} ! Quelle énergie ! 🔥🏅"],
    "Randonnée": ["Magnifique {nom} ! Une randonnée de {distance} terminée en {duree} ! 🌄"],
    "Vélo": ["Belle sortie {nom} ! {distance} à vélo en {duree} 🚴"],
    "Natation": ["Splash ! {nom} vient de nager {distance} en {duree} 🏊"],
    "Marche": ["Bien joué {nom} ! {distance} de marche en {duree} 🚶"],
    "Voile": ["Bon vent {nom} ! {distance} de navigation en {duree} ⛵"],
    "Équitation": ["Au galop {nom} ! {distance} à cheval en {duree} 🐎"],
}
MODELE_DISTANCE_DEFAUT = "Bravo {nom} ! {distance} {de_sport} en {duree} ! 💪"
MODELE_SANS_DISTANCE = "Bravo {nom} ! {duree} {de_sport}, quelle séance ! 💪"


def de_sport(sport: str) -> str:
    """'tennis' -> 'de tennis' ; 'escalade' -> "d'escalade" (élision devant une voyelle)."""
    sport = sport.lower()
    return f"d'{sport}" if sport[0] in "aeéèêiouyh" else f"de {sport}"


def formater_distance(metres: int) -> str:
    """10879 -> '10,9 km' ; 800 -> '800 m'."""
    if metres < 1000:
        return f"{metres} m"
    return f"{metres / 1000:.1f} km".replace(".", ",")


def formater_duree(secondes: int) -> str:
    """2760 -> '46 min' ; 3900 -> '1 h 05'."""
    minutes = round(secondes / 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d}"


def doit_etre_publie(evenement: dict) -> bool:
    return (
        evenement.get("__op") in OPERATIONS_PUBLIEES
        and evenement.get("source") in SOURCES_PUBLIEES
    )


def construire_message(evenement: dict, noms: dict[int, str], rng: random.Random | None = None) -> str:
    """Construit le texte Slack d'une activité."""
    rng = rng or random.Random()
    nom = noms.get(evenement["id_salarie"], "Un collègue")
    sport = evenement["type_activite"]
    debut = datetime.fromisoformat(evenement["date_debut"])
    fin = datetime.fromisoformat(evenement["date_fin"])
    duree = formater_duree(int((fin - debut).total_seconds()))

    distance_m = evenement.get("distance_m")
    if distance_m:
        modele = rng.choice(MODELES_DISTANCE.get(sport, [MODELE_DISTANCE_DEFAUT]))
        texte = modele.format(nom=nom, de_sport=de_sport(sport),
                              distance=formater_distance(distance_m), duree=duree)
    else:
        texte = MODELE_SANS_DISTANCE.format(nom=nom, de_sport=de_sport(sport), duree=duree)

    if evenement.get("commentaire"):
        texte += f' ("{evenement["commentaire"]}")'
    return texte


def traiter_evenement(valeur: bytes | None, noms: dict[int, str]) -> str | None:
    """Message Redpanda brut -> texte Slack, ou None s'il ne faut rien publier."""
    if valeur is None:          # message vide (tombstone) : rien à faire
        return None
    evenement = json.loads(valeur)
    if not doit_etre_publie(evenement):
        return None
    return construire_message(evenement, noms)
