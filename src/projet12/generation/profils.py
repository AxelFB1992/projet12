"""Profils des sports : ce qui rend une activité simulée réaliste.

Pour chaque sport déclaré dans le fichier RH, on définit le ou les types
d'activité Strava correspondants, avec des distances, vitesses ou durées
plausibles. Modifier ce fichier suffit à ajuster la simulation.
"""

from dataclasses import dataclass

#Décorateur qui permet d'éviter d'écrire le constructeur (avec tous les paramètres), les fonctions toString() et equals()
@dataclass(frozen=True)
class ProfilActivite:
    """Caractéristiques d'un type d'activité."""

    type_activite: str
    # Sports à distance : distance (km) mini / la plus fréquente / maxi, et vitesse (km/h)
    distance_km: tuple[float, float, float] | None = None
    vitesse_kmh: tuple[float, float] | None = None
    # Sports sans distance (escalade, tennis...) : durée en minutes mini / maxi
    duree_min: tuple[int, int] | None = None

    @property
    def avec_distance(self) -> bool:
        return self.distance_km is not None


# ---------- Types d'activité ----------
COURSE = ProfilActivite("Course à pied", distance_km=(3, 8, 21), vitesse_kmh=(8.5, 13))
RANDONNEE = ProfilActivite("Randonnée", distance_km=(5, 10, 25), vitesse_kmh=(3, 5))
NATATION = ProfilActivite("Natation", distance_km=(0.5, 1.5, 4), vitesse_kmh=(2, 3.5))
VELO = ProfilActivite("Vélo", distance_km=(10, 30, 90), vitesse_kmh=(16, 28))
MARCHE = ProfilActivite("Marche", distance_km=(2, 4, 10), vitesse_kmh=(4, 5.5))
VOILE = ProfilActivite("Voile", distance_km=(5, 12, 35), vitesse_kmh=(7, 15))
EQUITATION = ProfilActivite("Équitation", distance_km=(5, 10, 20), vitesse_kmh=(7, 12))

TENNIS = ProfilActivite("Tennis", duree_min=(45, 120))
BADMINTON = ProfilActivite("Badminton", duree_min=(45, 90))
TENNIS_DE_TABLE = ProfilActivite("Tennis de table", duree_min=(30, 90))
FOOTBALL = ProfilActivite("Football", duree_min=(60, 120))
RUGBY = ProfilActivite("Rugby", duree_min=(60, 120))
BASKETBALL = ProfilActivite("Basketball", duree_min=(45, 120))
JUDO = ProfilActivite("Judo", duree_min=(60, 120))
BOXE = ProfilActivite("Boxe", duree_min=(45, 90))
ESCALADE = ProfilActivite("Escalade", duree_min=(60, 180))

# ---------- Sport déclaré (fichier RH) -> activités possibles avec leur poids ----------
# Les libellés sont ceux du fichier, y compris la faute "Runing".
#C'est un dictionnaire de profil avec, pour chaque profil, le nom des profil et la liste d'activité associée
#Pour chaque activité de la liste, on a un couple (ProfilActivité, poids) avec profil d'activité étant la classe décrité ci-dessus et le poids une probabilité que cette activité ait lieue
PROFILS_PAR_SPORT: dict[str, list[tuple[ProfilActivite, float]]] = {
    "Runing": [(COURSE, 0.9), (RANDONNEE, 0.1)],
    "Randonnée": [(RANDONNEE, 0.85), (MARCHE, 0.15)],
    "Natation": [(NATATION, 1.0)],
    "Triathlon": [(COURSE, 0.4), (VELO, 0.35), (NATATION, 0.25)],
    "Voile": [(VOILE, 1.0)],
    "Équitation": [(EQUITATION, 1.0)],
    "Tennis": [(TENNIS, 1.0)],
    "Badminton": [(BADMINTON, 1.0)],
    "Tennis de table": [(TENNIS_DE_TABLE, 1.0)],
    "Football": [(FOOTBALL, 1.0)],
    "Rugby": [(RUGBY, 1.0)],
    "Basketball": [(BASKETBALL, 1.0)],
    "Judo": [(JUDO, 1.0)],
    "Boxe": [(BOXE, 1.0)],
    "Escalade": [(ESCALADE, 1.0)],
}

# Salariés sans sport déclaré : activités occasionnelles
PROFILS_OCCASIONNELS: list[tuple[ProfilActivite, float]] = [(MARCHE, 0.6), (VELO, 0.4)]

# ---------- Commentaires facultatifs (comme sur Strava) ----------
COMMENTAIRES_GENERIQUES = [
    "Reprise du sport :)",
    "Belle séance !",
    "Dur dur aujourd'hui...",
    "Nouveau record perso 💪",
    "Avec les collègues, top ambiance",
]
COMMENTAIRES_PAR_TYPE: dict[str, list[str]] = {
    "Course à pied": [
        "Sortie le long du Lez",
        "Fractionné au parc Montcalm",
        "Footing sur la plage de Carnon",
    ],
    "Randonnée": [
        "Randonnée de St Guilhem le désert, je vous la conseille c'est top",
        "Montée au Pic Saint-Loup, vue magnifique",
        "Balade dans les gorges de l'Hérault",
    ],
    "Vélo": [
        "Tour de l'étang de l'Or",
        "Sortie avec les semis croustillants 🚴",
        "Aller-retour jusqu'à Palavas",
    ],
    "Natation": ["Piscine olympique d'Antigone", "Baignade à Villeneuve-lès-Maguelone"],
    "Voile": ["Sortie au large de La Grande-Motte", "Beau vent aujourd'hui !"],
    "Escalade": ["Bloc à la salle", "Falaise du Thaurac"],
    "Marche": ["Petite marche digestive", "Balade au bord de l'eau"],
}
