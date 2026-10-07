-- Une ligne par salarié : éligibilité aux deux avantages et coût pour l'entreprise.
-- Volontairement SANS nom, adresse ni salaire individuel (données lues par Power BI).

with parametres as (
    select * from {{ ref('stg_parametres') }}
),

salaries as (
    select * from {{ ref('stg_salaries') }}
),

-- Activités valides sur la période, postérieures à l'embauche
activites_periode as (
    select a.id_salarie, count(*) as nb_activites
    from {{ ref('stg_activites') }} a
    join salaries s using (id_salarie)
    cross join parametres p
    where a.est_valide
      and a.date_activite >= current_date - p.periode_jours::int
      and a.date_activite >= s.date_embauche
    group by a.id_salarie
),

base as (
    select
        s.*,
        sp.sport_declare,
        coalesce(sp.pratique_declaree, false)          as pratique_declaree,
        d.distance_km,
        d.statut_api,
        case s.mode_api
            when 'WALK'    then p.seuil_marche_km
            when 'BICYCLE' then p.seuil_velo_km
        end                                            as seuil_km,
        case
            when not s.trajet_sportif then 'non concerné'
            -- distance absente, introuvable ou calculée pour une ancienne adresse / un ancien mode
            when d.distance_km is null
              or d.statut_api <> 'ROUTE_EXISTS'
              or d.mode_api is distinct from s.mode_api
              or d.adresse_calculee is distinct from s.adresse then 'non vérifiée'
            when d.distance_km <= case s.mode_api
                                      when 'WALK' then p.seuil_marche_km
                                      else p.seuil_velo_km
                                  end              then 'conforme'
            else 'suspecte'
        end                                            as statut_declaration,
        coalesce(a.nb_activites, 0)                    as nb_activites,
        p.taux_prime,
        p.nb_activites_min,
        p.nb_jours_bien_etre,
        p.jours_travailles_an
    from salaries s
    cross join parametres p
    left join {{ ref('stg_sports') }} sp using (id_salarie)
    left join {{ ref('stg_distances') }} d using (id_salarie)
    left join activites_periode a using (id_salarie)
)

select
    id_salarie,
    bu,
    tranche_age,
    type_contrat,
    date_embauche,
    sport_declare,
    pratique_declaree,
    moyen_deplacement,
    trajet_sportif,
    distance_km,
    seuil_km,
    statut_declaration,

    -- Prime sportive : trajet sportif ET distance vérifiée sous le seuil
    statut_declaration = 'conforme'                               as eligible_prime,
    case when statut_declaration = 'conforme'
         then round(salaire_brut * taux_prime, 2) else 0 end      as montant_prime,

    -- Journées bien-être : au moins N activités valides sur la période
    nb_activites,
    nb_activites >= nb_activites_min                              as eligible_bien_etre,
    case when nb_activites >= nb_activites_min
         then nb_jours_bien_etre else 0 end                       as jours_bien_etre,
    case when nb_activites >= nb_activites_min
         then round(salaire_brut / jours_travailles_an * nb_jours_bien_etre, 2)
         else 0 end                                               as cout_bien_etre
from base
