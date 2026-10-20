-- Ce modèle s'interesse aux avantages que les salariés peuvent avoir par rapport aux activités qu'ils ont déclaré

-- Une ligne par salarié : éligibilité aux deux avantages et coût pour l'entreprise.
-- Volontairement SANS nom, adresse ni salaire individuel (données lues par Power BI).

-- On va faire la jointure de 3 vues staging : stg_parametres, stg_salaries et stg_activites
with 

-- On prend la vue stg_parametres avec tous ses paramètres
parametres 
as (
    select * from {{ ref('stg_parametres') }}
),

-- On prend la vue stg_salaries avec tous ses paramètres
salaries 
as (
    select * from {{ ref('stg_salaries') }}
),

-- On prend la vue stg_activites avec certains paramètres seulement : id_salarie et nb_activites et avec des conditins
-- Conditions réalisés à l'aide d'une jointure interne avec les deux tables cités précedemment : 
-- 	-Activité valide au sens du tests présent 'est_valide' déjà présent dans les champs de la table
-- 	-Activité réalisé sur la période d'étude prévue dans les paramètres
-- 	-Activité postérieure à la date d'embauche de chaque salarié
-- On groupe le résultat de la jointure et du nombre n'activité par salarié (id_salarié)
activites_periode 
	as (select a.id_salarie, count(*) as nb_activites
    	from {{ ref('stg_activites') }} a
    	join salaries s using (id_salarie)
    	cross join parametres p
    	where a.est_valide
      	and a.date_activite >= current_date - p.periode_jours::int
      	and a.date_activite >= s.date_embauche
    	group by a.id_salarie
),


-- Auparavant on a prépareé 3 tables qui vont nous permettre de faire nos traitements
-- Ici on commence véritable les traitements qui vont nous permettre d'arriver à la table finale en base de ce fichier
-- On remarque que 2 nouvelles tables sont ajoutées aux traitements : stg_sports et stg_distances

-- Ici on commence par faire tous les calculs et traitement pour calculer les primes et journées bien-être
-- Les traitments les plus complexes concernes :
-- -le seuil de km (seuil_km) correspondant au salarié et à son mode de transport -> à aller cherche dans la table p de paramètres
-- -le statut de la déclaration (statut_declaration) pour juger si la distance réelle domicile-travail d'un salarié est suspecte
-- 		par rapport à ce qu'il a renseigné comme mode de déplacement (WALK ou BYCICLE)
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

-- Ici on récupère seulement les champs qui nous interesseet on calcule, pour chaque salarié :
-- -Eligibilité à la prime de ce salarié
-- -Montant de la prime pour ce salarié
-- -Eligibilite aux journees bien-être pour ce slarié
-- -Nombre de jours bien-être octroyé au salarié
-- -Couts des journées bien-être représenté par ce salarié

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
    -- Seuil du nombre de km cohérent correspondant au moyen de transport déclaré par le salarié : marche -> 15km, vélo -> 25km
    seuil_km,
    statut_declaration,

    -- Prime sportive : trajet sportif ET distance vérifiée sous le seuil
    statut_declaration = 'conforme'                               as eligible_prime,
    case when statut_declaration = 'conforme'
         then round(salaire_brut * taux_prime, 2) else 0 end      as montant_prime,

    -- Journées bien-être : au moins N activités valides sur la période
    -- On calcule également le nombre d'activité pour savoir si il atteint le seuil (de 15 activités actuellement) pour être éligible
    nb_activites,
    nb_activites >= nb_activites_min                              as eligible_bien_etre,
    case when nb_activites >= nb_activites_min
         then nb_jours_bien_etre else 0 end                       as jours_bien_etre,
    -- On calcule également le cout bien être par salarié en sachant qu'une journée bien être est une journée payée non travaillée
    case when nb_activites >= nb_activites_min
         then round(salaire_brut / jours_travailles_an * nb_jours_bien_etre, 2)
         else 0 end                                               as cout_bien_etre
from base
