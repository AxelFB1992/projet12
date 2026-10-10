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

# Cette méthode prend en paramètre une liste d'origine (str) et une destination (str) et renvoit une liste de distance (list[dict])
def calculer_lot(client: httpx.Client, cle: str, origines: list[str], destination: str, mode: str) -> list[dict]:
    """Distances de plusieurs origines vers une destination, pour un mode (WALK, BICYCLE).
    Renvoie une liste alignée sur `origines` : {distance_m, duree_s, statut}."""
    # le corps du message que l'on va envoyer à l'API de google via le endpoint ci-dessous (client.post(URL, corps, entetes)
    # Ce corps contient : les origines, la destination et le moyen de déplacement (Il n'y a qu'un seul moyen par appel de calculer_lot)
    corps = {
        "origins": [{"waypoint": {"address": a}} for a in origines],
        "destinations": [{"waypoint": {"address": destination}}],
        "travelMode": mode,
    }
    # Les entêtes (cachés) nécessaires pour avoir l'autorisation d'utilisation l'API
    entetes = {"X-Goog-Api-Key": cle, "X-Goog-FieldMask": FIELD_MASK}
    # On fixe 3 tentatives possibles pour la même requête, au délà de laquelle une génère une exception
    for tentative in range(1, 4):
        # Le coeur du calcul : la requête par l'API qui genère une réponse 
        try:
            reponse = client.post(URL, json=corps, headers=entetes)
            reponse.raise_for_status()
            break
        # Il s'agit d'une erreur soulevé par raise_for_status() qui indiquerait que le calcul s'est mal passé
        # Par défaut, le protocole (utilisé client.post())par httpx ne lève pas d’erreur. raise_for_status() force la levée dans certains cas.
        except httpx.HTTPError as erreur:
            # On ne récupère que le status-code de l'erreur : Pas de message complet dans les logs (peut contenir des informations sensibles)
            code = getattr(getattr(erreur, "response", None), "status_code", "-")
            # On l'affiche avec une jolie message d'erreur marqué avec un niveau d'importance "warning"
            log.warning("Échec Routes API (tentative %d/3) : %s, code HTTP %s",
                        tentative, type(erreur).__name__, code)
            # Si on est déjà à la 3e tentative et qu'on se retrouve encore ici, alors une soulève une exception qui nous sort de la boucle
            if tentative == 3:
                # Permet de relancer l'exeception en cours et la laisse arriver au programme appelant
                raise
            # Sinon on retente '2 * (le nombre de tentatives)' secondes plus tard
            time.sleep(2 ** tentative)

    # On prépare la liste de résultats qui est une liste de dictionnaires avec autant de dictionnaire qu'il y a d'origine
    resultats = [{"distance_m": None, "duree_s": None, "statut": "SANS_REPONSE"}] * len(origines)
    # On parcourt les élements de la réponse un par un : chaque élément est un résultat de distance par rapport à une origine
    for element in reponse.json():
        # On récupère l'indice de la position de l'origine qu'elle avait lorsque l'on a fourni la liste d'origine
        # Cela nous permet de reconstruire l'ordre des distances transmis pour associer le bon résultat (distance) au bon trajet
        i = element.get("originIndex", 0)
        # Si le code du statut n'est pas vide dans la réponse associée à un élement, c'est qu'il y a une erreur
        if element.get("status", {}).get("code"):          # erreur propre à cet élément
            # On récupère dont le statut correctement formaté
            statut = f"ERREUR_{element['status']['code']}"
        # Sinon, c'est soit que le calcul a été fait, soit qu'il n'y a pas de route entre les deux. Dans les deux cas, c'est un résultat valide
        else:
            # On récupère également le statut
            statut = element.get("condition", "INCONNU")    # ROUTE_EXISTS / ROUTE_NOT_FOUND

        # Dans les deux cas (status renseigné ou non), on stocke les résultats donné par l'API dans le dictionnaire à la position i de la liste
        resultats[i] = {
            "distance_m": element.get("distanceMeters"),
            "duree_s": _secondes(element.get("duration")),
            "statut": statut,
        }
    # Et on retourne cette ligne une fois que tous les éléments de la réponse ont été parcourus.
    return resultats
