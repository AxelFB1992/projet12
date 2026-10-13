{#
  Écrit une ligne dans monitoring.pipeline_runs à la fin de chaque commande dbt
  (build, run, test, seed) : statut, nombre de nœuds traités, détail des erreurs.
#}
{% macro tracer_execution(results) %}
    {%- if execute -%}
        {%- set erreurs = results | selectattr('status', 'in', ['error', 'fail', 'runtime error']) | list -%}
        {%- set avertissements = results | selectattr('status', 'equalto', 'warn') | list -%}
        {%- set statut = 'echec' if erreurs else 'succes' -%}
        {%- set message = results | length ~ ' noeud(s), ' ~ erreurs | length ~ ' erreur(s), '
                          ~ avertissements | length ~ ' avertissement(s)'
                          ~ (' : ' ~ (erreurs | map(attribute='node.name') | join(', ')) if erreurs else '') -%}
        insert into monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes, message)
        values ('dbt_{{ flags.WHICH }}', '{{ run_started_at }}', now(), '{{ statut }}',
                {{ results | length }}, '{{ message | replace("'", "''") }}')
    {%- endif -%}
{% endmacro %}
