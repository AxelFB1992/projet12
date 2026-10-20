-- Ce modèle s'interesse purement aux activités, sans regarder les primes et avantages que les salariés peuvent avoir

-- Une ligne par activité, enrichie pour l'analyse de la pratique sportive (Power BI).

-- C'est certainemet la table principale obtenus après tous les traitements : celle des activités
-- Elle fait une jointure des 3 vues principales issues du staging des 3 tables brutes : raw.activite, raw.salaries et raw.sports
-- Le but est d'obtenir un tableau générale présentant toutes les infomrations en une seule fois, sans les primes
-- A ce stade, chacune des colonnes prise indépendemment est nettoyé et cohérente
-- Ex : la distance a fait l'objet :
-- 		- De Contrôles Soda prévues dans soda/checks/raw.yml : invalid_percent(distance_m)) sur les données brutes (tables raw)
--		- De Contrôles Soda prévues dans soda/checks/raw.yml : vitesses_implausibles sur les données brutes (tables raw)
-- 		- De calculs enregistrés dans la colonne a.est_valide, à titre informatif (c'est très grossier)
-- Aucun test au sens de dbt n'est realisé, ni dans un tests générique (fichier .yml); ni dans un test métier (fichier .sql)
-- Par ailleurs, pour cette table, il n'y a que deux tests dbt : id_activite (source.yml) et id_activite/id_salarie (marts.yml)
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
    -- Le commentaire est-celui inscrit au moment de la génération
    a.commentaire is not null                    as a_commentaire,
    s.bu,
    s.tranche_age,
    sp.sport_declare
from {{ ref('stg_activites') }} a
left join {{ ref('stg_salaries') }} s using (id_salarie)
left join {{ ref('stg_sports') }} sp using (id_salarie)
