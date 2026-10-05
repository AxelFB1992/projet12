"""Génération d'activités sportives simulées, façon Strava.

Ce module ne touche pas à la base de données : il produit des objets Activite.
L'écriture en base est faite par le module ecriture.py.
"""

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from projet12.config import FUSEAU
from projet12.generation.profils import (
    COMMENTAIRES_GENERIQUES,
    COMMENTAIRES_PAR_TYPE,
    PROFILS_OCCASIONNELS,
    PROFILS_PAR_SPORT,
    ProfilActivite,
)

TZ = ZoneInfo(FUSEAU)

# Probabilité qu'une activité porte un commentaire
PROBA_COMMENTAIRE_HISTORIQUE = 0.2
PROBA_COMMENTAIRE_LIVE = 0.5


@dataclass(frozen=True)
class Salarie:
    id_salarie: int
    sport: str | None          # sport déclaré, None si aucun
    date_embauche: date


@dataclass(frozen=True)
class Activite:
    id_salarie: int
    date_debut: datetime
    type_activite: str
    distance_m: int | None     # None si non pertinent (escalade, tennis...)
    date_fin: datetime
    commentaire: str | None
    source: str                # backfill | live


# ---------------------------------------------------------------------------
# Lecture des fichiers RH
# ---------------------------------------------------------------------------
def charger_salaries(fichier_rh: Path, fichier_sport: Path) -> list[Salarie]:
    """Croise le fichier RH (date d'embauche) et le fichier sport (sport déclaré).
    Seules les colonnes utiles sont lues : pas de salaire ni d'adresse ici."""
    rh = pd.read_excel(fichier_rh, usecols=["ID salarié", "Date d'embauche"])
    sport = pd.read_excel(fichier_sport, usecols=["ID salarié", "Pratique d'un sport"])
    df = rh.merge(sport, on="ID salarié", how="left")

    salaries = []
    for ligne in df.itertuples(index=False):
        sport_declare = ligne[2]
        sport_declare = str(sport_declare).strip() if pd.notna(sport_declare) else None
        salaries.append(
            Salarie(
                id_salarie=int(ligne[0]),
                sport=sport_declare,
                date_embauche=pd.Timestamp(ligne[1]).date(),
            )
        )
    return salaries


# ---------------------------------------------------------------------------
# Briques de simulation
# ---------------------------------------------------------------------------
def profils_du_salarie(salarie: Salarie) -> list[tuple[ProfilActivite, float]]:
    """Activités possibles pour un salarié, selon son sport déclaré."""
    if salarie.sport is None:
        return PROFILS_OCCASIONNELS
    # Sport inconnu des profils (nouveau sport dans le fichier RH) : on se
    # rabat sur les activités occasionnelles plutôt que d'échouer.
    return PROFILS_PAR_SPORT.get(salarie.sport, PROFILS_OCCASIONNELS)


def frequence_hebdo(salarie: Salarie, rng: random.Random) -> float:
    """Nombre moyen d'activités par semaine, propre à chaque salarié.
    Les écarts entre salariés sont voulus : certains atteindront le seuil
    des 15 activités par an, d'autres non."""
    if salarie.sport is None:
        return rng.uniform(0.0, 0.3)       # occasionnel : 0 à ~15 activités / an
    if rng.random() < 0.15:
        return rng.uniform(0.1, 0.3)       # sportif irrégulier : ~5 à 15 / an
    return rng.uniform(0.5, 3.0)           # sportif régulier : ~25 à 150 / an


def coefficient_saison(jour: date) -> float:
    """Plus de sport au printemps et en été, moins en hiver (moyenne = 1)."""
    return 1 + 0.25 * math.cos(2 * math.pi * (jour.month - 6) / 12)


def heure_de_depart(jour: date, rng: random.Random) -> datetime:
    """Heure plausible : avant le travail, à midi ou le soir en semaine,
    n'importe quand dans la journée le week-end."""
    if jour.weekday() >= 5:
        heure = rng.uniform(8, 17)
    else:
        heure = rng.choice([rng.uniform(6.5, 8), rng.uniform(12, 13.5), rng.uniform(17.5, 20)])
    minutes = int(heure * 60)
    return datetime(jour.year, jour.month, jour.day, minutes // 60, minutes % 60, tzinfo=TZ)


def simuler_mesures(profil: ProfilActivite, rng: random.Random) -> tuple[int | None, int]:
    """Renvoie (distance en mètres ou None, durée en secondes)."""
    if profil.avec_distance:
        mini, mode, maxi = profil.distance_km
        distance_km = rng.triangular(mini, maxi, mode)
        vitesse = rng.uniform(*profil.vitesse_kmh)
        return round(distance_km * 1000), round(distance_km / vitesse * 3600)
    duree_minutes = rng.randint(*profil.duree_min)
    return None, duree_minutes * 60


def choisir_commentaire(type_activite: str, proba: float, rng: random.Random) -> str | None:
    if rng.random() >= proba:
        return None
    candidats = COMMENTAIRES_PAR_TYPE.get(type_activite, []) + COMMENTAIRES_GENERIQUES
    return rng.choice(candidats)


def appliquer_anomalie(activite: Activite, rng: random.Random) -> Activite:
    """Introduit volontairement une erreur, pour vérifier que les tests de
    qualité (Soda) la détectent."""
    anomalie = rng.choice(["distance_negative", "dates_inversees", "distance_absurde"])
    if anomalie == "distance_negative" and activite.distance_m:
        return _remplacer(activite, distance_m=-activite.distance_m)
    if anomalie == "distance_absurde" and activite.distance_m:
        return _remplacer(activite, distance_m=activite.distance_m * 100)
    return _remplacer(activite, date_debut=activite.date_fin, date_fin=activite.date_debut)


def _remplacer(activite: Activite, **champs) -> Activite:
    return Activite(**{**activite.__dict__, **champs})


def _tirer_profil(profils: list[tuple[ProfilActivite, float]], rng: random.Random) -> ProfilActivite:
    return rng.choices([p for p, _ in profils], weights=[w for _, w in profils])[0]


# ---------------------------------------------------------------------------
# Les deux modes de génération
# ---------------------------------------------------------------------------
def generer_historique(
    salaries: list[Salarie],
    fin: datetime,
    jours: int = 365,
    graine: int | None = None,
    taux_anomalies: float = 0.0,
) -> list[Activite]:
    """Génère l'historique des `jours` derniers jours, jusqu'à `fin`.
    Avec la même graine, le résultat est identique (reproductible)."""
    rng = random.Random(graine)
    debut_periode = (fin - timedelta(days=jours)).date()
    activites: list[Activite] = []

    for salarie in salaries:
        profils = profils_du_salarie(salarie)
        proba_par_jour = frequence_hebdo(salarie, rng) / 7
        # Pas d'activité avant l'arrivée du salarié dans l'entreprise
        premier_jour = max(debut_periode, salarie.date_embauche)

        jour = premier_jour
        while jour <= fin.date():
            coef_jour = 1.5 if jour.weekday() >= 5 else 0.8   # plus de sport le week-end
            if rng.random() < proba_par_jour * coef_jour * coefficient_saison(jour):
                profil = _tirer_profil(profils, rng)
                distance_m, duree_s = simuler_mesures(profil, rng)
                date_debut = heure_de_depart(jour, rng)
                date_fin = date_debut + timedelta(seconds=duree_s)
                if date_fin <= fin:   # pas d'activité dans le futur
                    activite = Activite(
                        id_salarie=salarie.id_salarie,
                        date_debut=date_debut,
                        type_activite=profil.type_activite,
                        distance_m=distance_m,
                        date_fin=date_fin,
                        commentaire=choisir_commentaire(
                            profil.type_activite, PROBA_COMMENTAIRE_HISTORIQUE, rng
                        ),
                        source="backfill",
                    )
                    if rng.random() < taux_anomalies:
                        activite = appliquer_anomalie(activite, rng)
                    activites.append(activite)
            jour += timedelta(days=1)

    activites.sort(key=lambda a: a.date_debut)
    return activites


def generer_live(
    salaries: list[Salarie],
    n: int,
    maintenant: datetime,
    rng: random.Random,
) -> list[Activite]:
    """Génère `n` activités qui viennent de se terminer.
    Les sportifs déclarés sont 4 fois plus souvent tirés au sort."""
    poids = [4 if s.sport else 1 for s in salaries]
    activites = []
    for salarie in rng.choices(salaries, weights=poids, k=n):
        profil = _tirer_profil(profils_du_salarie(salarie), rng)
        distance_m, duree_s = simuler_mesures(profil, rng)
        date_fin = maintenant - timedelta(seconds=rng.randint(0, 300))
        activites.append(
            Activite(
                id_salarie=salarie.id_salarie,
                date_debut=date_fin - timedelta(seconds=duree_s),
                type_activite=profil.type_activite,
                distance_m=distance_m,
                date_fin=date_fin,
                commentaire=choisir_commentaire(profil.type_activite, PROBA_COMMENTAIRE_LIVE, rng),
                source="live",
            )
        )
    return activites
