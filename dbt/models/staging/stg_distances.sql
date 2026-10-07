-- Distances domicile-travail calculées par l'API Google Routes.

select
    id_salarie,
    adresse                         as adresse_calculee,
    mode_api,
    round(distance_m / 1000.0, 1)   as distance_km,
    round(duree_s / 60.0)           as duree_min,
    statut                          as statut_api,
    calcule_le
from {{ source('geo', 'distances_domicile_travail') }}
