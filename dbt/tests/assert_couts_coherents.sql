-- Tests métier : 
-- -aucune prime négative
-- -pas de prime sans éligibilité.
-- -aucun cout_bien_etre négatif (pour les journées bien être)
-- -pas de cout_bien_etre sans éligibilité.
-- Le test échoue s'il renvoie au moins une ligne.

select *
from {{ ref('avantages_salaries') }}
where montant_prime < 0
   or cout_bien_etre < 0
   or (not eligible_prime and montant_prime > 0)
   or (not eligible_bien_etre and cout_bien_etre > 0)
