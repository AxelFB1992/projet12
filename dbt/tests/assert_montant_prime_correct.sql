-- Test métier : la prime d'un salarié éligible vaut exactement
-- salaire brut annuel x taux en vigueur (arrondi au centime).
-- Garde-fou contre une modification accidentelle de la formule.
-- Le test échoue s'il renvoie au moins une ligne.

select
    a.id_salarie,
    a.montant_prime,
    round(s.salaire_brut * p.taux_prime, 2) as montant_attendu
from {{ ref('avantages_salaries') }} a
join {{ ref('stg_salaries') }} s using (id_salarie)
cross join {{ ref('stg_parametres') }} p
where a.eligible_prime
  and a.montant_prime <> round(s.salaire_brut * p.taux_prime, 2)
