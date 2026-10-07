-- Salariés : typage, âge, tranches, et traduction du mode de déplacement.

select
    id_salarie,
    trim(nom)                                           as nom,
    trim(prenom)                                        as prenom,
    date_naissance,
    date_part('year', age(current_date, date_naissance))::int as age,
    case
        when date_part('year', age(current_date, date_naissance)) < 30 then '< 30 ans'
        when date_part('year', age(current_date, date_naissance)) < 40 then '30-39 ans'
        when date_part('year', age(current_date, date_naissance)) < 50 then '40-49 ans'
        when date_part('year', age(current_date, date_naissance)) < 60 then '50-59 ans'
        else '60 ans et +'
    end                                                 as tranche_age,
    trim(bu)                                            as bu,
    date_embauche,
    salaire_brut,
    trim(type_contrat)                                  as type_contrat,
    jours_cp,
    adresse,
    trim(moyen_deplacement)                             as moyen_deplacement,
    trim(moyen_deplacement) in ('Marche/running', 'Vélo/Trottinette/Autres') as trajet_sportif,
    case trim(moyen_deplacement)
        when 'Marche/running'           then 'WALK'
        when 'Vélo/Trottinette/Autres'  then 'BICYCLE'
    end                                                 as mode_api
from {{ source('raw', 'salaries') }}
