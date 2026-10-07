"""Appel à l'API Google Routes (computeRouteMatrix) : distance domicile -> bureau.

https://developers.google.com/maps/documentation/routes/compute_route_matrix
"""

import logging
import time

import httpx

log = logging.getLogger("geo")

URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# Champs demandés à l'API (obligatoire avec la Routes API, et limite le coût)
FIELD_MASK = "originIndex,destinationIndex,distanceMeters,duration,condition,status"
# Avec des adresses en texte, une requête est limitée à 50 éléments (origines x destinations)
TAILLE_LOT = 25


def _secondes(duree: str | None) -> int | None:
    """'3949s' -> 3949."""
    return int(duree.rstrip("s")) if duree else None


def calculer_lot(
    client: httpx.Client, cle: str, origines: list[str], destination: str, mode: str
) -> list[dict]:
    """Distances de plusieurs origines vers une destination, pour un mode (WALK, BICYCLE).
    Renvoie une liste alignée sur `origines` : {distance_m, duree_s, statut}."""
    corps = {
        "origins": [{"waypoint": {"address": a}} for a in origines],
        "destinations": [{"waypoint": {"address": destination}}],
        "travelMode": mode,
    }
    entetes = {"X-Goog-Api-Key": cle, "X-Goog-FieldMask": FIELD_MASK}

    for tentative in range(1, 4):
        try:
            reponse = client.post(URL, json=corps, headers=entetes)
            reponse.raise_for_status()
            break
        except httpx.HTTPError as erreur:
            # Pas de message complet dans les logs (il pourrait contenir des informations sensibles)
            code = getattr(getattr(erreur, "response", None), "status_code", "-")
            log.warning("Échec Routes API (tentative %d/3) : %s, code HTTP %s",
                        tentative, type(erreur).__name__, code)
            if tentative == 3:
                raise
            time.sleep(2 ** tentative)

    resultats = [{"distance_m": None, "duree_s": None, "statut": "SANS_REPONSE"}] * len(origines)
    for element in reponse.json():
        i = element.get("originIndex", 0)
        if element.get("status", {}).get("code"):          # erreur propre à cet élément
            statut = f"ERREUR_{element['status']['code']}"
        else:
            statut = element.get("condition", "INCONNU")    # ROUTE_EXISTS / ROUTE_NOT_FOUND
        resultats[i] = {
            "distance_m": element.get("distanceMeters"),
            "duree_s": _secondes(element.get("duration")),
            "statut": statut,
        }
    return resultats
