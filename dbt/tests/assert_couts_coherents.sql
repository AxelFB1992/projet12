-- Test métier : aucun coût négatif, et pas de coût sans éligibilité.
-- Le test échoue s'il renvoie au moins une ligne.

select *
from {{ ref('avantages_salaries') }}
where montant_prime < 0
   or cout_bien_etre < 0
   or (not eligible_prime and montant_prime > 0)
   or (not eligible_bien_etre and cout_bien_etre > 0)
