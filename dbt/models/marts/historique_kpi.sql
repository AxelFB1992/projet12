-- Historique des indicateurs : une ligne ajoutée à CHAQUE exécution de dbt.
-- Permet de comparer l'effet d'un changement de paramètre (ex. taux 5 % -> 3 %).
-- Attention : "dbt build --full-refresh" vide cet historique.

{{ config(materialized='incremental') }}

select
    now()                    as calcule_le,
    '{{ invocation_id }}'    as execution_id,
    k.*
from {{ ref('kpi_synthese') }} k
