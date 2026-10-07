"""Tests du client Routes API, avec une API simulée (aucun appel réel à Google)."""

import json

import httpx

from projet12.geo.distances import Trajet, calculer
from projet12.geo.routes import calculer_lot


def client_simule(reponse_par_mode: dict, appels: list) -> httpx.Client:
    """Client httpx dont les requêtes sont interceptées : renvoie une réponse
    au format de l'API Google pour chaque origine."""
    def gestionnaire(requete: httpx.Request) -> httpx.Response:
        corps = json.loads(requete.content)
        appels.append({"corps": corps, "entetes": dict(requete.headers)})
        mode = corps["travelMode"]
        elements = [
            {"originIndex": i, "destinationIndex": 0, **reponse_par_mode[mode](o["waypoint"]["address"])}
            for i, o in enumerate(corps["origins"])
        ]
        return httpx.Response(200, json=elements)
    return httpx.Client(transport=httpx.MockTransport(gestionnaire))


def route(distance_m, duree_s):
    return lambda adresse: {"distanceMeters": distance_m, "duration": f"{duree_s}s",
                            "condition": "ROUTE_EXISTS"}


def test_conversion_reponse_google():
    appels = []
    client = client_simule({"WALK": route(4818, 3949)}, appels)
    r = calculer_lot(client, "CLE", ["a", "b"], "bureau", "WALK")
    assert r == [{"distance_m": 4818, "duree_s": 3949, "statut": "ROUTE_EXISTS"}] * 2
    assert appels[0]["entetes"]["x-goog-api-key"] == "CLE"
    assert "x-goog-fieldmask" in appels[0]["entetes"]


def test_route_introuvable():
    appels = []
    introuvable = {"WALK": lambda a: {"condition": "ROUTE_NOT_FOUND"}}
    r = calculer_lot(client_simule(introuvable, appels), "CLE", ["a"], "bureau", "WALK")
    assert r[0] == {"distance_m": None, "duree_s": None, "statut": "ROUTE_NOT_FOUND"}


def test_decoupage_par_mode_et_par_lots_de_25():
    appels = []
    client = client_simule({"WALK": route(1000, 600), "BICYCLE": route(9000, 1800)}, appels)
    trajets = [Trajet(i, f"adresse {i}", "BICYCLE") for i in range(30)] + [Trajet(99, "x", "WALK")]
    lignes = calculer(client, "CLE", trajets, "bureau")
    assert len(lignes) == 31
    assert [len(a["corps"]["origins"]) for a in appels] == [25, 5, 1]   # 2 lots vélo + 1 marche
    assert all(o["waypoint"]["address"].endswith(", France")
               for a in appels for o in a["corps"]["origins"])
    assert {l[0]: l[3] for l in lignes}[99] == 1000
