-- Activités : mesures dérivées et indicateur de validité.
-- Les activités incohérentes sont CONSERVÉES mais marquées (est_valide = false) :
-- elles ne comptent pas pour les avantages, et restent visibles pour l'analyse qualité.

-- On commence par récupérer la table raw.activites (a) en calculant en plus la duree et en faisant une jointure avec vitesse_max
-- La jointure porte sur le 'type_activite' qui, je le rappelle, correspond dans notre code à l'activité ('Course à pied, natation')
with activites as (
    select
        a.*,
        extract(epoch from (a.date_fin - a.date_debut))      as duree_s,
        v.vitesse_max_kmh
    from {{ source('raw', 'activites') }} a
    left join {{ ref('vitesses_max') }} v using (type_activite)
)

--Une fois que l'on a récupéré cette très grande table, on selectionne les champs qui nous intéresse et on rajoute un champ
--Ce champs s'appelle est_valide et contrôle, la cohérence des dates, de la distance et de la vitessse
--Si ces 3 indicateurs sont plausibles, alors est_valide est également à TRUE : c'est un premier (petit) contrôle
select
    id_activite,
    id_salarie,
    date_debut,
    date_fin,
    (date_debut at time zone 'Europe/Paris')::date            as date_activite,
    type_activite,
    distance_m,
    round(distance_m / 1000.0, 2)                             as distance_km,
    round(duree_s / 60.0, 1)                                  as duree_min,
    -- nullif : pas de division par zéro si la durée est nulle
    round(distance_m / 1000.0 / nullif(duree_s / 3600.0, 0), 1) as vitesse_kmh,
    commentaire,
    source,
    (
        date_fin > date_debut
        and duree_s < 24 * 3600
        and (distance_m is null or distance_m between 0 and 300000)
        -- vitesse plausible pour le sport (sports sans seuil : pas de contrôle)
        and (distance_m is null or vitesse_max_kmh is null
             or distance_m / 1000.0 / nullif(duree_s / 3600.0, 0) <= vitesse_max_kmh)
    )                                                         as est_valide
from activites
