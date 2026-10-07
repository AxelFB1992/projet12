-- Paramètres en vigueur : valeurs du fichier seeds/parametres.csv,
-- éventuellement surchargées au lancement, par exemple :
--   dbt build --vars '{taux_prime: 0.03, seuil_velo_km: 15}'

{%- set noms = [
    'taux_prime', 'seuil_marche_km', 'seuil_velo_km', 'nb_jours_bien_etre',
    'nb_activites_min', 'jours_travailles_an', 'periode_jours'
] %}

select
{%- for nom in noms %}
    {%- if var(nom, none) is not none %}
    {{ var(nom) }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- else %}
    {{ nom }}::numeric as {{ nom }}{{ "," if not loop.last }}
    {%- endif %}
{%- endfor %}
from {{ ref('parametres') }}
