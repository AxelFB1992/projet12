-- Test qualité : aucune activité ne devrait être datée avant l'embauche du salarié.
-- Simple avertissement : ces activités sont déjà exclues du calcul des
-- journées bien-être (voir avantages_salaries), le test sert à les signaler.
 
{{ config(severity='warn') }}
 
select
    a.id_activite,
    a.id_salarie,
    a.date_activite,
    s.date_embauche
from {{ ref('stg_activites') }} a
join {{ ref('stg_salaries') }} s using (id_salarie)
where a.date_activite < s.date_embauche
