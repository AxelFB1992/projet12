"""Tests de la construction des messages Slack (sans réseau ni Kafka)."""

import json

from projet12.slack.messages import (
    formater_distance,
    formater_duree,
    formater_vitesse,
    traiter_evenement,
)

NOMS = {43015: "Juliette Mendes"}


def evenement(**champs) -> bytes:
    base = {
        "id_activite": 1, "id_salarie": 43015,
        "date_debut": "2026-10-05T13:26:00.000000Z", "date_fin": "2026-10-05T14:12:00.000000Z",
        "type_activite": "Course à pied", "distance_m": 10800, "commentaire": None,
        "source": "live", "__op": "c",
    }
    return json.dumps({**base, **champs}).encode()


def test_message_course_comme_dans_la_note_de_cadrage():
    texte = traiter_evenement(evenement(), NOMS)
    assert texte == "Bravo Juliette Mendes ! Tu viens de courir 10,8 km en 46 min ! Quelle énergie ! — 14,1 km/h de moyenne"


def test_commentaire_ajoute_entre_guillemets():
    texte = traiter_evenement(evenement(commentaire="Top spot"), NOMS)
    assert texte.endswith('("Top spot")')


def test_sport_sans_distance():
    texte = traiter_evenement(evenement(type_activite="Escalade", distance_m=None), NOMS)
    assert texte == "Bravo Juliette Mendes ! 46 min d'escalade, quelle séance !"
    texte = traiter_evenement(evenement(type_activite="Tennis", distance_m=None), NOMS)
    assert "46 min de tennis" in texte


def test_historique_et_snapshot_ignores():
    assert traiter_evenement(evenement(source="backfill"), NOMS) is None
    assert traiter_evenement(evenement(__op="r"), NOMS) is None
    assert traiter_evenement(None, NOMS) is None


def test_salarie_inconnu():
    assert traiter_evenement(evenement(id_salarie=1), NOMS).startswith("Bravo Un collègue")


def test_formats():
    assert formater_distance(800) == "800 m"
    assert formater_distance(10879) == "10,9 km"
    assert formater_duree(2760) == "46 min"
    assert formater_duree(3900) == "1 h 05"
    assert formater_vitesse(10800, 2760) == "14,1 km/h"

def test_activite_incoherente_non_publiee():
    assert traiter_evenement(evenement(distance_m=-10800), NOMS) is None
    assert traiter_evenement(evenement(distance_m=1_080_000), NOMS) is None
    # dates inversées
    assert traiter_evenement(evenement(date_debut="2026-10-05T14:12:00.000000Z",
                                       date_fin="2026-10-05T13:26:00.000000Z"), NOMS) is None

def test_vitesse_implausible_non_publiee():
    # 172,4 km de natation en 33 min (> 300 km/h) : anomalie
    nage = evenement(type_activite="Natation", distance_m=172_400,
                     date_debut="2026-10-05T13:00:00Z", date_fin="2026-10-05T13:33:00Z")
    assert traiter_evenement(nage, NOMS) is None
    # 65,9 km de vélo en 2 h 30 (26 km/h) : normal
    velo = evenement(type_activite="Vélo", distance_m=65_900,
                     date_debut="2026-10-05T13:00:00Z", date_fin="2026-10-05T15:30:00Z")
    assert traiter_evenement(velo, NOMS) is not None
