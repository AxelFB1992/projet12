-- Paramètres en vigueur : valeurs du fichier seeds/parametres.csv, éventuellement surchargées au lancement, par exemple :
--   dbt build --vars '{taux_prime: 0.03, seuil_velo_km: 15}'

-- Ce fichier est l'un des seuls à avoir la syntaxe Jinja car la plupart des paramètres vont être remplacé par ceux de paramètres.csv
-- Ici, on indique quels sont les paramètres que l'on va utiliser, dans l'ordre 
{%- set noms = [
    'taux_prime', 'seuil_marche_km', 'seuil_velo_km', 'nb_jours_bien_etre',
    'nb_activites_min', 'jours_travailles_an', 'periode_jours'
] %}

-- On parcourt tous les paramètres pour faire une boucle et pour dire
-- Pour tous les paramètres, si vous en trouvez un qui est clairement spécifié, remplacer le par sa valeur
-- Il y a donc un select par paramètre, ce qui évite d'ecrire 7 fois la même chose pour chaque paramètre
select
{%- for nom in noms %}
    {%- if var(nom, none) is not none %}
    {{ var(nom) }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- else %}
    {{ nom }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- endif %}
{%- endfor %}
from {{ ref('parametres') }}

-- Tous les marts lisent les paramètres à travers ce modèle et uniquement celui-ci : il produit une table stg_parametres.
