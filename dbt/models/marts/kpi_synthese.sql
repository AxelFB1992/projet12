-- Une seule ligne : les indicateurs clés du POC, avec les paramètres utilisés.

with av as (select * from {{ ref('avantages_salaries') }}),
     p  as (select * from {{ ref('stg_parametres') }}),
     act as (
         select count(*) filter (where est_valide)     as nb_activites_valides,
                count(*) filter (where not est_valide) as nb_activites_invalides
         from {{ ref('stg_activites') }}, p
         where date_activite >= current_date - p.periode_jours::int
     )

select
    count(*)                                              as nb_salaries,
    count(*) filter (where pratique_declaree)             as nb_sportifs_declares,
    count(*) filter (where trajet_sportif)                as nb_trajets_sportifs,
    count(*) filter (where statut_declaration = 'suspecte')     as nb_declarations_suspectes,
    count(*) filter (where statut_declaration = 'non vérifiée') as nb_declarations_non_verifiees,
    count(*) filter (where eligible_prime)                as nb_eligibles_prime,
    sum(montant_prime)                                    as cout_prime,
    count(*) filter (where eligible_bien_etre)            as nb_eligibles_bien_etre,
    sum(jours_bien_etre)                                  as nb_jours_bien_etre,
    sum(cout_bien_etre)                                   as cout_bien_etre,
    sum(montant_prime) + sum(cout_bien_etre)              as cout_total,
    max(act.nb_activites_valides)                         as nb_activites_valides,
    max(act.nb_activites_invalides)                       as nb_activites_invalides,
    -- paramètres en vigueur, pour savoir à quoi correspondent ces chiffres
    max(p.taux_prime)                                     as taux_prime,
    max(p.seuil_marche_km)                                as seuil_marche_km,
    max(p.seuil_velo_km)                                  as seuil_velo_km,
    max(p.nb_activites_min)                               as nb_activites_min,
    max(p.nb_jours_bien_etre)                             as nb_jours_bien_etre_par_salarie
from av, p, act
