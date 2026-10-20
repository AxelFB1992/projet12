-- Distances domicile-travail calculées par l'API Google Routes.

-- Dès lors que la table distances_domicile_travai a été crée et les distances calculé à l'aide de Google Routes API
-- On reformule certaines colonnes (adresse, distance, duree et statut) tout en appliquant des transformations pour avoir le bon format
select
    id_salarie,
    adresse                         as adresse_calculee,
    mode_api,
    round(distance_m / 1000.0, 1)   as distance_km,
    round(duree_s / 60.0)           as duree_min,
    statut                          as statut_api,
    calcule_le
from {{ source('geo', 'distances_domicile_travail') }}

-- Pourquoi on a un champ adresse_calculee ici alors que ce champ est déjà présent dans raw.salaries puis dans stg_salaries.adresse ?
-- Une fois que l'on a fait l'ingestion des données RH (où se trouve l'adresse), on fait le calcul des distances à l'aide de geo.
-- On a recopié l'adresse de raw.salarié pour la mettre dans geo.distances_domicile_travail et calculer la distance associée
-- Si jamais on a refait une ingestion derrière, et que le salarié a changé d'adresse, alors on saura qu'il faut recalculer la distance
-- On le verra dans la table analytics.avantages_salaries - En effet, le modèle de mart prévoit un champ (statut_declaration) :
-- Ce champs relève toute type de déclaration suspecte dont la déclaration d'adresse si elle n'est pas la même dans les deux tables :
-- ...  or d.adresse_calculee is distinct from s.adresse then 'non vérifiée' ... as statut_declaration

-- Attention, le cache est la table geo.distances_domicile_travail, pas la vue stg_distances
-- Par ailleurs, à chaque execution trajets_a_calculer() (dans geo/distances.py) compare les salariés de raw.salaries à ce qui est déjà
-- dans cette table, et n’appelle Google que pour les trajets absents ou modifiés : nouvel employé, nouvelle adresse ou nouveau mode
