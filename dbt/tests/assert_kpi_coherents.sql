-- Test métier : les indicateurs de synthèse sont cohérents entre eux
-- et avec le détail par salarié.
-- Le test échoue s'il renvoie au moins une ligne.
 
with detail as (
    select sum(montant_prime) + sum(cout_bien_etre) as cout_total_detail
    from {{ ref('avantages_salaries') }}
)
 
select k.*
from {{ ref('kpi_synthese') }} k
cross join detail d
where k.nb_eligibles_prime     > k.nb_trajets_sportifs      -- éligible => trajet sportif
   or k.nb_trajets_sportifs    > k.nb_salaries
   or k.nb_eligibles_bien_etre > k.nb_salaries
   or abs(k.cout_total - d.cout_total_detail) > 0.01        -- synthèse = somme du détail
