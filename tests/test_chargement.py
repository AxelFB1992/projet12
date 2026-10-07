"""Tests de la conversion message Redpanda -> ligne de l'entrepôt (sans base ni Kafka)."""

import json
from datetime import UTC, datetime

from projet12.chargement.entrepot import COLONNES, evenement_vers_ligne


def message(**champs) -> bytes:
    base = {
        "id_activite": 42, "id_salarie": 43015,
        "date_debut": "2026-10-05T13:26:37.242210Z", "date_fin": "2026-10-05T14:12:37.242210Z",
        "type_activite": "Course à pied", "distance_m": 10800, "commentaire": None,
        "source": "backfill", "cree_le": "2026-10-05T14:12:37.242210Z",
        "__op": "c", "__source_ts_ms": 1791209557254,
    }
    return json.dumps({**base, **champs}).encode()


def test_conversion_complete():
    ligne = evenement_vers_ligne(message())
    assert len(ligne) == len(COLONNES)
    d = dict(zip(COLONNES, ligne))
    assert d["id_activite"] == 42
    assert d["date_debut"] == datetime(2026, 10, 5, 13, 26, 37, 242210, tzinfo=UTC)
    assert d["operation"] == "c"
    assert d["capture_le"].tzinfo is not None


def test_valeurs_aberrantes_conservees_telles_quelles():
    # La couche raw ne filtre pas : c'est le rôle de Soda
    d = dict(zip(COLONNES, evenement_vers_ligne(message(distance_m=-500))))
    assert d["distance_m"] == -500


def test_distance_vide_et_tombstone():
    d = dict(zip(COLONNES, evenement_vers_ligne(message(distance_m=None))))
    assert d["distance_m"] is None
    assert evenement_vers_ligne(None) is None
