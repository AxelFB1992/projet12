"""Tests du générateur : cohérence des données simulées (sans base de données)."""

import random
from datetime import date, datetime, timedelta

import pytest

from projet12.config import FICHIER_RH, FICHIER_SPORT
from projet12.generation.generateur import (
    TZ,
    Salarie,
    charger_salaries,
    generer_historique,
    generer_live,
)
from projet12.generation.profils import PROFILS_PAR_SPORT

FIN = datetime(2026, 10, 5, 18, 0, tzinfo=TZ)
SALARIES_TEST = [
    Salarie(1, "Runing", date(2015, 1, 1)),
    Salarie(2, "Escalade", date(2015, 1, 1)),
    Salarie(3, None, date(2015, 1, 1)),
    Salarie(4, "Natation", date(2026, 6, 1)),   # embauché il y a 4 mois
]


@pytest.fixture(scope="module")
def historique():
    return generer_historique(SALARIES_TEST * 10, fin=FIN, graine=1)


def test_dates_dans_la_periode_et_coherentes(historique):
    for a in historique:
        assert FIN - timedelta(days=366) <= a.date_debut < a.date_fin <= FIN


def test_distances_positives_ou_vides(historique):
    for a in historique:
        assert a.distance_m is None or a.distance_m > 0


def test_pas_de_distance_pour_les_sports_sans_distance(historique):
    escalade = [a for a in historique if a.type_activite == "Escalade"]
    assert escalade and all(a.distance_m is None for a in escalade)


def test_aucune_activite_avant_embauche(historique):
    nageur = [a for a in historique if a.id_salarie == 4]
    assert all(a.date_debut.date() >= date(2026, 6, 1) for a in nageur)


def test_reproductible_avec_la_meme_graine():
    a = generer_historique(SALARIES_TEST, fin=FIN, graine=7)
    b = generer_historique(SALARIES_TEST, fin=FIN, graine=7)
    assert a == b


def test_anomalies_injectees_sur_demande():
    avec = generer_historique(SALARIES_TEST * 10, fin=FIN, graine=1, taux_anomalies=0.5)
    erreurs = [a for a in avec if (a.distance_m or 0) < 0 or a.date_fin <= a.date_debut
               or (a.distance_m or 0) > 500_000]
    assert erreurs


def test_live_se_termine_maintenant():
    activites = generer_live(SALARIES_TEST, n=5, maintenant=FIN, rng=random.Random(0))
    assert len(activites) == 5
    for a in activites:
        assert a.source == "live"
        assert FIN - timedelta(minutes=5) <= a.date_fin <= FIN
        assert a.date_debut < a.date_fin


@pytest.mark.skipif(not FICHIER_RH.exists(), reason="fichiers RH absents")
def test_tous_les_sports_du_fichier_rh_ont_un_profil():
    sports = {s.sport for s in charger_salaries(FICHIER_RH, FICHIER_SPORT) if s.sport}
    assert sports <= PROFILS_PAR_SPORT.keys()
