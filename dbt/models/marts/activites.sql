-- Une ligne par activité, enrichie pour l'analyse de la pratique sportive (Power BI).

select
    a.id_activite,
    a.id_salarie,
    a.date_activite,
    date_trunc('month', a.date_activite)::date   as mois,
    extract(isodow from a.date_activite)::int    as jour_semaine,   -- 1 = lundi
    a.type_activite,
    a.distance_km,
    a.duree_min,
    a.source,
    a.est_valide,
    a.commentaire is not null                    as a_commentaire,
    s.bu,
    s.tranche_age,
    sp.sport_declare
from {{ ref('stg_activites') }} a
left join {{ ref('stg_salaries') }} s using (id_salarie)
left join {{ ref('stg_sports') }} sp using (id_salarie)
