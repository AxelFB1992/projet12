"""Tests de la construction des messages Slack (sans réseau ni Kafka)."""

import json

from projet12.slack.messages import formater_distance, formater_duree, traiter_evenement

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
    assert texte == "Bravo Juliette Mendes ! Tu viens de courir 10,8 km en 46 min ! Quelle énergie ! 🔥🏅"


def test_commentaire_ajoute_entre_guillemets():
    texte = traiter_evenement(evenement(type_activite="Randonnée", commentaire="Top spot"), NOMS)
    assert texte.endswith('("Top spot")')


def test_sport_sans_distance():
    texte = traiter_evenement(evenement(type_activite="Escalade", distance_m=None), NOMS)
    assert texte == "Bravo Juliette Mendes ! 46 min d'escalade, quelle séance ! 💪"
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
