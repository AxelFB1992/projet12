-- Annuaire minimal pour le consommateur Slack : identifiant, prénom, nom.
-- Rien d'autre (pas de salaire, d'adresse ni de date de naissance).
-- Lu par le rôle slack_notifier, qui n'a accès qu'à cette vue (grants dans dbt_project.yml).
-- La vue s'exécute avec les droits de son propriétaire (etl) : slack_notifier
-- n'a donc besoin d'aucun droit sur raw ou staging.

select
    id_salarie,
    prenom,
    nom
from {{ ref('stg_salaries') }}
