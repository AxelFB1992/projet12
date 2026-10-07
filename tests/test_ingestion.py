"""Tests de lecture et de validation des fichiers RH (sans base de données)."""

import datetime

import pandas as pd
import pytest

from projet12.config import FICHIER_RH, FICHIER_SPORT
from projet12.ingestion.referentiels import (
    SALARIES,
    SPORTS,
    FichierInvalide,
    lire_et_valider,
    vers_lignes,
)

pytestmark = pytest.mark.skipif(not FICHIER_RH.exists(), reason="fichiers RH absents")


def test_fichier_rh_valide_et_renomme():
    df = lire_et_valider(FICHIER_RH, SALARIES)
    assert list(df.columns) == list(SALARIES.colonnes.values())
    assert len(df) == 161
    assert isinstance(df["date_embauche"].iloc[0], datetime.date)


def test_sport_vide_devient_null():
    df = lire_et_valider(FICHIER_SPORT, SPORTS)
    lignes = vers_lignes(df, FICHIER_SPORT)
    assert any(l[1] is None for l in lignes)              # pas de sport -> NULL
    assert all(l[-1] == "donnees_sportives.xlsx" for l in lignes)


def test_valeurs_brutes_conservees():
    df = lire_et_valider(FICHIER_SPORT, SPORTS)
    assert "Runing" in set(df["pratique_sport"])          # la correction se fera dans dbt


def _excel(tmp_path, df):
    chemin = tmp_path / "test.xlsx"
    df.to_excel(chemin, index=False)
    return chemin


def test_colonne_manquante_refusee(tmp_path):
    df = pd.DataFrame({"ID salarié": [1, 2]})               # pas de colonne "Pratique d'un sport"
    with pytest.raises(FichierInvalide, match="colonnes manquantes"):
        lire_et_valider(_excel(tmp_path, df), SPORTS)


def test_identifiant_en_double_refuse(tmp_path):
    df = pd.DataFrame({"ID salarié": [1, 1], "Pratique d'un sport": ["Tennis", None]})
    with pytest.raises(FichierInvalide, match="en double"):
        lire_et_valider(_excel(tmp_path, df), SPORTS)
