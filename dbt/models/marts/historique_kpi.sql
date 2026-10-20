-- Historique des indicateurs : une ligne ajoutée à CHAQUE exécution de dbt.
-- Permet de comparer l'effet d'un changement de paramètre (ex. taux 5 % -> 3 %).
-- Attention : "dbt build --full-refresh" vide cet historique.

--On récupère la ligne courante calculée dans kpi_synthese juste avant d'executer ce modèle
--Et on la stocke en rajoutant la date et l'heure actuel et un identifiant unique (execution_id)
--Cela ne permet de garder un historique de toutes les executions du pipeline, non en terme de logs mais en terme de statistiques métiers
{{ config(materialized='incremental') }}

select
    now()                    as calcule_le,
    '{{ invocation_id }}'    as execution_id,
    k.*
from {{ ref('kpi_synthese') }} k
