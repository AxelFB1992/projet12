"""Tests du rechargement de l'annuaire Slack (sans base de données)."""

import psycopg

from projet12.slack.consommateur import recharger_noms


def test_rechargement_complete_l_annuaire():
    noms = {1: "Juliette Mendes"}
    recharger_noms(noms, lire=lambda: {1: "Juliette Mendes", 2: "Paul Durand"})
    assert noms == {1: "Juliette Mendes", 2: "Paul Durand"}


def test_vue_absente_avant_ingestion():
    def vue_absente():
        raise psycopg.errors.UndefinedTable("relation raw.noms_salaries does not exist")

    noms = {}
    recharger_noms(noms, lire=vue_absente)   # ne doit pas planter
    assert noms == {}

def test_vue_pas_encore_creee():
    noms = {}
    recharger_noms(noms, lire=lambda: None)   # to_regclass a renvoyé NULL
    assert noms == {}
