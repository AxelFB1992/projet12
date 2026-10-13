"""Génération d'activités sportives simulées, façon Strava.

Ce module ne touche pas à la base de données : il produit des objets Seance.
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
    ACTIVITES_OCCASIONNELLES,
    ACTIVITES_PAR_SPORT,
    COMMENTAIRES_GENERIQUES,
    COMMENTAIRES_PAR_TYPE,
    Activite,
)

#On récupère le fuseau horaire grâce à la configuration python initalisé par uv dans le dossier src/projet12 via le fichier config.py 
#A l'intérieur du fichier config.py, il y a la variable FUSEAU qui servira à tous les scripts qui ont besoin du fuseau (FUSEAU = "Europe/Paris")
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
class Seance:
    id_salarie: int
    date_debut: datetime
    nom_activite: str
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
    #On ne garde que les informations qui nous intéressent
    rh = pd.read_excel(fichier_rh, usecols=["ID salarié", "Date d'embauche"])
    sport = pd.read_excel(fichier_sport, usecols=["ID salarié", "Pratique d'un sport"])
    #On fait une jointure entre les deux dataframes en utilisant la règle suivante : on se base sur les identifiants du fichier rh pour faire la jointure
    #Si il n'y a pas d'ID correspondant dans le fichier sport, on fait quand même la jointure avec une ligne vide : le fichier RH fait foi
    df = rh.merge(sport, on="ID salarié", how="left")

    #On boucle sur chacune des lignes du résultat correspondant à la jointure et on stocke chaque ligne intérmediaire dans "ligne"
    salaries = []
    for ligne in df.itertuples(index=False):
        #Etant donné qu'on a gardé seulement les informations essentielles, le sport déclaré se trouve à la 3ème place dans l'ordre des colonnes.
        sport_declare = ligne[2]
        #Si il y a un sport, on nettoie le champ correspondant pour ne récupérer que le sport et sinon on met None
        sport_declare = str(sport_declare).strip() if pd.notna(sport_declare) else None
        #On crée un objet Salarié de la classe décrité précedemment avec les champs que l'on a stocké, et on l'ajoute à la liste salaries
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
#Retourne une liste d'activité  pour chaque salarié c'est à dire une liste d'activité ainsi qu'un poids par activité pour renseigner sa fréquence.
#Les activités qu'un salarie peut effectuer sont déterminés dans activites.py en fonction du "sport" qu'il a renseigné.
#Rappel : Une activité est une activité ou type d'activité (course à pied, vélo, natation) et des caractéristiques "plausibles" (durée, distance) que l'on peut lui associer.
def activites_du_salarie(salarie: Salarie) -> list[tuple[Activite, float]]:
    """Activités possibles pour un salarié, selon son sport déclaré."""
    if salarie.sport is None:
        return ACTIVITES_OCCASIONNELLES
    # Sport inconnu des activites (nouveau sport dans le fichier RH) : on se
    # rabat sur les activités occasionnelles plutôt que d'échouer.
    # Sinon on cherche dans la liste "normale" de activite pour un sport connu renseigné.
    return ACTIVITES_PAR_SPORT.get(salarie.sport, ACTIVITES_OCCASIONNELLES)


def simuler_frequence_hebdomadaire(salarie: Salarie, rng: random.Random) -> float:
    """Nombre moyen d'activités par semaine, propre à chaque salarié.
    Les écarts entre salariés sont voulus : certains atteindront le seuil
    des 15 activités par an, d'autres non."""
    # Si pas de sport renseigné, il s'agit d'un non sportif qu'on affecte donc à une frequence d'activité occassionnelle
    if salarie.sport is None:
        return rng.uniform(0.0, 0.3)       # occasionnel : 0 à ~15 activités / an
    # Si il fait partie des 15% (rng.random() est entre 0 et 0.15) de sportifs (avec un sport déclaré) non régulier, on lui retourne un nombre d'activité par semaine entre 0.1 et 0.3 (1 activité par mois)
    if rng.random() < 0.15:
        return rng.uniform(0.1, 0.3)       # sportif irrégulier : ~5 à 15 / an
    # Sinon, il s'agit d'un sportif régulier donc entre 0.5 et 3 acivités par mois (nombre lui aussi généré aléatoirement)
    return rng.uniform(0.5, 3.0)           # sportif régulier : ~25 à 150 / an

# Retourne un float qui, grâce à cette formule, augmente lorsque le jour se rapproche de la saison estivale et diminue près de la saison hivernale.
def coefficient_saison(jour: date) -> float:
    """Plus de sport au printemps et en été, moins en hiver (moyenne = 1)."""
    return 1 + 0.25 * math.cos(2 * math.pi * (jour.month - 6) / 12)

# Retourne un horaire de la journée, en sachant que cette fonction a plus de chance de retourner certains horaires plutôt que d'autre, en fonction du jour qu'on lui passe en paramètre (voir description)
def simuler_heure_debut_seance(jour: date, rng: random.Random) -> datetime:
    """Heure plausible : avant le travail, à midi ou le soir en semaine,
    n'importe quand dans la journée le week-end."""
    if jour.weekday() >= 5:
        heure = rng.uniform(8, 17)
    else:
        heure = rng.choice([rng.uniform(6.5, 8), rng.uniform(12, 13.5), rng.uniform(17.5, 20)])
    minutes = int(heure * 60)
    return datetime(jour.year, jour.month, jour.day, minutes // 60, minutes % 60, tzinfo=TZ)


def simuler_mesures_seance(activite: Activite, rng: random.Random) -> tuple[int | None, int]:
    """Renvoie (distance en mètres ou None, durée en secondes)."""
    if activite.avec_distance:
        # récupère les 3 mesures (mini, mode, maxi) qui ont déjà été renseigné dans l'activité passé en paramètres
        mini, mode, maxi = activite.distance_km
        # On génère une distance aléatoire en fonction des 3 mesures données ci-dessus
        distance_km = rng.triangular(mini, maxi, mode)
        # De même, on génère une mesure aléatoire de la vitesse en utilisant le tuple (min, max) vitesse_kmh du activite déjà prévu à cet effet.
        vitesse = rng.uniform(*activite.vitesse_kmh)
        # Et on retourne les deux mesures : distance en mètre et durée en secondes, arrondis pour éviter les virgules
        return round(distance_km * 1000), round(distance_km / vitesse * 3600)
    #Si pas de distance dans l'activité renseigné, alors on retourne simplement la durée de l'activité en seoncde avec None devant pour la distance
    duree_minutes = rng.randint(*activite.duree_min)
    return None, duree_minutes * 60


def choisir_commentaire(nom_activite: str, proba: float, rng: random.Random) -> str | None:
    # Si c'est une activité historique, la proba est à 0.2 donc il y aura beaucoup de chances que l'on tombe dans le cas ou la méthode retourner None
    # Sinon il s'agit d'un activité live, dans de cas la proba est à 0.5 donc on a une moitié de chance pour qu'il y ait un commentaire, et une autre moitié pour qu'il n'y en ait pas.
    if rng.random() >= proba:
        return None
    # Dans le cas où il y a un commentaire, on a encore deux choix : soit un commentaire spécifique, soit un commentaire générique
    candidats = COMMENTAIRES_PAR_TYPE.get(nom_activite, []) + COMMENTAIRES_GENERIQUES
    # Cela sera encore une fois tranché aléatoirement, grâce à cette dernière instruction ci-dessous
    return rng.choice(candidats)


def simuler_anomalie(seance: Seance, rng: random.Random) -> Seance:
    """Introduit volontairement une erreur, pour vérifier que les tests de
    qualité (Soda) la détectent."""
    # On énumère le type d'anomalie possible et on en choisit une aléatoirement
    anomalie = rng.choice(["distance_negative", "dates_inversees", "distance_absurde"])
    # Si c'est la distance négative, on se contente d'inverser la distance actuelle de l'acivité
    if anomalie == "distance_negative" and seance.distance_m:
        # Et on retorune un nouvel objet (une nouvelle activité) dans lequel on a remplacé la distance par son opposé (voir méthode _remplacer ci-dessous)
        return _remplacer(seance, distance_m=-seance.distance_m)
    # Si c'est une distance absurde, alors on mutliplie la distance en mètre par 1000 et on est sur d'obtenir une absurdité
    if anomalie == "distance_absurde" and seance.distance_m:
        # On utilise une fois encore la méthode _remplacer ci dessous
        return _remplacer(seance, distance_m=seance.distance_m * 100)
    # Sinon il s'agit du cas dates inversés dans lequel on inverse la date de fin et date de début; et on utilse _remplacer pour réaliser l'opération
    return _remplacer(seance, date_debut=seance.date_fin, date_fin=seance.date_debut)

# Cette fonction de modifier une activité en re-créant un objet Activité avec les modifications (car Activité est statique par défaut)
def _remplacer(seance: Seance, **champs) -> Seance:
    # {**a, **b} fusionne les deux ensembles (dictionnaire) de champs et Seance(**dictionnaire) appelle le constructeur pour retourner un nouvel élément
    return Seance(**{**seance.__dict__, **champs})

# Retourne non pas le activite d'un salarié mais une activité dans le activite d'un salarié qu'on lui passe en paramètre, obtenu grâce à activites_du_salarie qui est une autre fonction
# C'est peut-être une mauvaise appelation, elle fait référence au fait du tirer au sort parmi les activités d'un activite pour renvoyer un seul activite
def choisir_activite(activites: list[tuple[Activite, float]], rng: random.Random) -> Activite:
    return rng.choices([p for p, _ in activites], weights=[w for _, w in activites])[0]


# ---------------------------------------------------------------------------
# Les deux modes de génération
# ---------------------------------------------------------------------------
# Retourne une liste d'Activités correspondant à la simulation de l'historique des activités
def simuler_historique_seances(salaries: list[Salarie],fin: datetime,jours: int = 365,graine: int | None = None,taux_anomalies: float = 0.0,) -> list[Seance]:
    """Génère l'historique des `jours` derniers jours, jusqu'à `fin`.Avec la même graine, le résultat est identique (reproductible)."""
    #Une graine permet de reproduire exactement les mêmes résultats sur les différentes simulations en obtenant la même variable aléatoire
    #On utilisera donc cette variable aléatoire (rng) pour toutes les simulations que nous devrons faire.
    rng = random.Random(graine)
    #On doit décider depuis quand s'est construit l'historique pour la simulation : c'est la date de fin (aujoud'hui) - 365 jours donc un historique d'un an
    debut_periode = (fin - timedelta(days=jours)).date()
    #La liste d'activité globale qui concerne tous les salariés
    seances: list[Seance] = []
    
    #On parcourt chacun des salariés
    for salarie in salaries:
        # On retire la liste des activités possibles pour un salariés, avec les poids associés à chacune des activités pour chacun des tirages
        activites = activites_du_salarie(salarie)
        # Une fois les activites recupérés, il faut générer sa fréquence de sport par jour en fonction de ce qu'il a renseigné, c'est l'objet de la fonction simuler_frequence_hebdomadaire
        proba_par_jour = simuler_frequence_hebdomadaire(salarie, rng) / 7
        # Pas d'activité avant l'arrivée du salarié dans l'entreprise : il faut donc choisir la date la plus récente entre le début de la période de simulation et sa date d'embauche
        premier_jour = max(debut_periode, salarie.date_embauche)
        # On va incrementer à chaque fois la variable jour pour créer les activités de manière chronologique et de pas créer une activité antiérieure à une autre
        jour = premier_jour
        # Tant que ce jour c'est pas arrivé à la fin de la période, alors on continue la boucle de génération pour ce salarié et on incrémente jour d'une journée
        while jour <= fin.date():
            # Pour chaque jour des 365 jours énumérés, on calcule le coeff du jour pour savoir si il y a une chance que ce salarié ait fait une activité ce jour-là.
            coef_jour = 1.5 if jour.weekday() >= 5 else 0.8   # plus de sport le week-end
            # On multiplie les 3 coefficients pour obtenir un taux moyen de réalisation d'une activité sportive en fonction de :
            # -son appetence au sport en fonction de ce qu'il a renseigné (proba par jour)
            # -le coefficient du jour (semaine ou week-end)
            # -le coefficient de la saison, en fonction de jour courant (été ou hiver)
            # Si le nombre généré entre 0 et 1 dépasse le résultat de cette mutiplication, alors on peut générer une activité.
            if rng.random() < proba_par_jour * coef_jour * coefficient_saison(jour):
                # Un activite est un activite d'activité, c'est à dire une activité avec ses caractéristiques et mesures types
                # On récupère donc un activite d'activité parmi les différents activites (d'activité) associé à ce salarié en fonction de ce qu'il a renseigné comme sport.
                activite = choisir_activite(activites, rng)
                # On génère les statistiques de son activité en fonction de mesures de celle-ci (via simuler_mesures_seance)
                distance_m, duree_s = simuler_mesures_seance(activite, rng)
                # De même pour l'heure de début
                date_debut = simuler_heure_debut_seance(jour, rng)
                # Et l'heure de fin n'est que = début + durée
                date_fin = date_debut + timedelta(seconds=duree_s)
                # Si la date de fin est bien antérieure à la date de fin de période globale, alors c'est une activité valide
                # Si non elle est tout simplement oublié et on passe à la suite
                if date_fin <= fin:   # pas d'activité dans le futur
                    # On crée un objet de type Activité avec toutes ces caractéristiques
                    seance = Seance(
                        id_salarie=salarie.id_salarie,
                        date_debut=date_debut,
                        nom_activite=activite.nom,
                        distance_m=distance_m,
                        date_fin=date_fin,
                        commentaire=choisir_commentaire(
                            activite.nom, PROBA_COMMENTAIRE_HISTORIQUE, rng
                        ),
                        # Et on rajoute ce champs pour savoir qu'il s'agit bien d'une activité de l'historique généré, et non d'une activité live
                        source="backfill",
                    )
                    # Ici, on voit si on va appliquer une anomalie à l'activité pour tester les tests SODA : il faut que cela concerne une petite proportion d'activité
                    # Ce taux est prévu dans le fichier main.py et est très proche de 0
                    if rng.random() < taux_anomalies:
                        seance = simuler_anomalie(seance, rng)
                    seances.append(seance)
            #On incréménete la variable jour de 1
            jour += timedelta(days=1)

    #Une fois que l'on a générer l'historique pour tous les salariés (et tous les jours depuis 1 an), on trie toutes les activité dans l'ordre chronologiques (tout salarié confondu)
    seances.sort(key=lambda a: a.date_debut)
    return seances

#Permet de générer un nombre n d'activités parmi la liste de salariés passées en paramètre
def simuler_n_seances(salaries: list[Salarie],n: int,maintenant: datetime,rng: random.Random,) -> list[Seance]:
    """Génère `n` activités qui viennent de se terminer.
    Les sportifs déclarés sont 4 fois plus souvent tirés au sort."""
    # Parmi les salariés de la liste, on donne un pods 4x supérieur à ceux qui ont déclaré un sport.
    poids = [4 if s.sport else 1 for s in salaries]
    # La liste générale des activités, que l'on aura pas besoin de trier par ordre chronoligue vu qu'elles seront toutes générés les unes après les autres, pour tous les salariés (il n'y a qu'une boucle)
    seances = []
    # Pour tous les salariés choisis dans la liste, il y a en n soit autant que le nombre d'activité (1 activité généré par salarié)
    for salarie in rng.choices(salaries, weights=poids, k=n):
        # On suit la même logique que pour la méthode précédente à savoir qu'on selectionne un activite d'activité parmi ses activites et on génère les statistiques grâce aux mesures prévus pour ce activite
        activite = choisir_activite(activites_du_salarie(salarie), rng)
        distance_m, duree_s = simuler_mesures_seance(activite, rng)
        date_fin = maintenant - timedelta(seconds=rng.randint(0, 300))
        # On ajoute l'activité en question avec toutesl es caractéristiques générées...
        seances.append(
            Seance(
                id_salarie=salarie.id_salarie,
                date_debut=date_fin - timedelta(seconds=duree_s),
                nom_activite=activite.nom,
                distance_m=distance_m,
                date_fin=date_fin,
                commentaire=choisir_commentaire(activite.nom, PROBA_COMMENTAIRE_LIVE, rng),
                # ... En n'omettant pas la source : live !
                source="live",
            )
        )
    return seances
