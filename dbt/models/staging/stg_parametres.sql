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
-- Il y a donc un paramètre de selectionné par tour de boucle, ce qui évite d'ecrire 7 fois la même chose pour chaque paramètre
select
{%- for nom in noms %}
    {%- if var(nom, none) is not none %}
    {{ var(nom) }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- else %}
    {{ nom }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- endif %}
{%- endfor %}
-- On va les chercher dans une table qui s'appelle analytics.parametres, qui a été chargé à partir de parametres.csv
from {{ ref('parametres') }}

-- la vue selectionne les 7 paramètres, si ils sont présents (non null) et les transforme en numérique (',' si ce n'est pas le dernier)
-- select taux_prime::numeric as taux_prime, ..., periode_jours::numeric as periode_jours from raw.parametres
-- Tous les marts lisent les paramètres à travers ce modèle et uniquement celui-ci : il produit une vue stg_paramètres
-- Cette vue est produite à partir de {{ ref('parametres') }} qui revient à from "dwh"."analytics"."parametres".
-- Au final l'ordre est : parametres.csv -> dbt seed -> dwh.analytics.parametres -> stg_parametres.slq -> vue (stg_parametres.sql)
