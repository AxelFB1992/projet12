{#
  Par défaut, dbt nomme les schémas "<schéma_cible>_<schéma_personnalisé>"
  (ex. staging_analytics). On veut exactement les schémas créés par
  01_init.sh : staging, analytics.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name else target.schema }}
{%- endmacro %}
