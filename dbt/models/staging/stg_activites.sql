-- Activités : mesures dérivées et indicateur de validité.
-- Les activités incohérentes sont CONSERVÉES mais marquées (est_valide = false) :
-- elles ne comptent pas pour les avantages, et restent visibles pour l'analyse qualité.

select
    id_activite,
    id_salarie,
    date_debut,
    date_fin,
    (date_debut at time zone 'Europe/Paris')::date            as date_activite,
    type_activite,
    distance_m,
    round(distance_m / 1000.0, 2)                             as distance_km,
    round(extract(epoch from (date_fin - date_debut)) / 60.0, 1) as duree_min,
    commentaire,
    source,
    (
        date_fin > date_debut
        and date_fin - date_debut < interval '24 hours'
        and (distance_m is null or distance_m between 0 and 300000)
    )                                                         as est_valide
from {{ source('raw', 'activites') }}
