-- Une seule ligne : les indicateurs clés du POC, avec les paramètres utilisés.

-- On est déjà au stade où la table analytics.avantages_salaries a été crée et où la vue stg_parametres a été générée
-- A partir de analytics.parametre --> on peut voir l'ordre de création des tables marts dans models/marts/marts.yml

-- Cette expression est une CTE : table temporaire nommé qui permet de poser certains calculs et renommer les tables avant la jointure
-- La première sous-table ramène 161 lignes (car 161 salariés), la deuxième 1 ligne (car une ligne de paramètres), la troisième
-- une ligne également, car on fait déjà une agregation sur une colonne sans group by, cela ramène tout à une ligne
with av as (select * from {{ ref('avantages_salaries') }}),
     p  as (select * from {{ ref('stg_parametres') }}),
     act as (
     	 -- Ce sont les deux seuls champs qui vont être récupéré de stg_activites, or ce sont des agrégations.
     	 -- Donc le résultat de cette sous table n'est qu'une ligne avec les deux champs nb_activites_valides et nb_activites_invalides
     	 -- qui calcule le nombre d'activite valides et invalides sur la période d'un an
         select count(*) filter (where est_valide)     as nb_activites_valides,
                count(*) filter (where not est_valide) as nb_activites_invalides
         from {{ ref('stg_activites') }}, p
         -- On ne récupère que les activités sur la période étudiée, à savoir 1 an, pour faire cette synthèse
         where date_activite >= current_date - p.periode_jours::int
     )

select
	-- Combien de salaries au total --> 161
    count(*)                                              as nb_salaries,
    -- Combien ont une réelle pratique sportive (déclarée et contrôlé)
    count(*) filter (where pratique_declaree)             as nb_sportifs_declares,
    -- Combien de trajets sportifs réels pour aller au travail ont été enregistrés
    count(*) filter (where trajet_sportif)                as nb_trajets_sportifs,
    --Combien de déclarations suspects et non vérifiés
    count(*) filter (where statut_declaration = 'suspecte')     as nb_declarations_suspectes,
    count(*) filter (where statut_declaration = 'non vérifiée') as nb_declarations_non_verifiees,
    --Combien sont éligibles à la prime et quel cout total cela va représenter
    count(*) filter (where eligible_prime)                as nb_eligibles_prime,
    sum(montant_prime)                                    as cout_prime,
    --Combien sont éligibles au bien être et combien de jours ainsi que quel cout cela va représenter ?
    count(*) filter (where eligible_bien_etre)            as nb_eligibles_bien_etre,
    sum(jours_bien_etre)                                  as nb_jours_bien_etre,
    sum(cout_bien_etre)                                   as cout_bien_etre,
    --Quel cout total (prime + jours bien être) cela va représenter pour l'entreprise ?
    sum(montant_prime) + sum(cout_bien_etre)              as cout_total,
    --Quels sont les statistiques d'activités valides et invalides ?
    --Ici, on est obligé d'utiliser une fonction d'agrégation car toutes les autres colonnes sont agrégés
    --Donc, à moins d'utiliser un group by sur ces lignes pour orienter l'agrégation, on utilise max (au hasard).
    max(act.nb_activites_valides)                         as nb_activites_valides,
    max(act.nb_activites_invalides)                       as nb_activites_invalides,
    --Quels sont les paramètres en vigueur, pour savoir à quoi correspondent ces chiffres
    max(p.taux_prime)                                     as taux_prime,
    max(p.seuil_marche_km)                                as seuil_marche_km,
    max(p.seuil_velo_km)                                  as seuil_velo_km,
    max(p.nb_activites_min)                               as nb_activites_min,
    max(p.nb_jours_bien_etre)                             as nb_jours_bien_etre_par_salarie

-- La jointure à proprement parler est ici, et vu qu'il n'y a pas de conditions : ca sera un produit cartesien
-- Le résultat fera donc 161 x 1 x 1 soit 161 lignes. Sur lequels on va faire des agrégations pour ne produire qu'une seule ligne
from av, p, act
