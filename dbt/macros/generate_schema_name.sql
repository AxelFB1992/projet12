-- Cette méthode (generate_schema_name) va être appelé automatiquement pour chaque model et pour chaque seed (à chaque création)
-- En effet, cette méthode est réservée : dbt en a une version par défaut et on la surcharge
{#
  Par défaut, dbt nomme les schémas "<schéma_cible>_<schéma_personnalisé>"
  (ex. staging_analytics). On veut exactement les schémas créés par
  01_init.sh : staging, analytics.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name else target.schema }}
{%- endmacro %}
