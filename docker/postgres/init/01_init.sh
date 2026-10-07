#!/bin/bash
# =============================================================================
# Initialisation de PostgreSQL — exécuté UNE SEULE FOIS, au premier démarrage
# (quand le volume de données est vide).
#
# Crée :
#   - 3 bases : app (source façon Strava), dwh (entrepôt), kestra (orchestrateur)
#   - des rôles à privilèges minimaux (un rôle = un usage)
#   - la table source app.public.activites + la publication pour Debezium
#   - les schémas de l'entrepôt dwh
# =============================================================================
set -euo pipefail

# ==============Creation des rôles et des accès sur les différentes accès sur les bases de données==============

""" 
On execute la commande psql qui lance postgres conteneurisé (dans le cadre du docker-compose) via le superutilisateur
Le superutilisateur (POSTGRES_USER) n'est utilisé que pour l'administration et l'execution de ces commandes
Les instructions du bloc ci-dessous réalise, dans l'ordre
	- La création des 5 rôles : app_writer (pour le generateur), debezium, etl (pour DBT), powerbi_reader et kestra.
	- La création des 3 bases de données : app pour les activites (strava), dwh pour le datawarehouse et kestra pour Kestra.
	- Les autorisations d'accès (de connexion - pas de lecture ni d'écriture pour l'instant) sur ces 3 bases de données
"""
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    -- ---------- Rôles applicatifs ----------
    -- Générateur d'activités : écrit dans la base app
    CREATE ROLE app_writer   LOGIN PASSWORD '${APP_WRITER_PASSWORD}';
    -- Debezium : lit le journal (WAL) de la base app
    CREATE ROLE debezium     LOGIN REPLICATION PASSWORD '${DEBEZIUM_PASSWORD}';
    -- Pipeline (ingestion, consommateurs, dbt, Soda) : propriétaire de l'entrepôt
    CREATE ROLE etl          LOGIN PASSWORD '${ETL_PASSWORD}';
    -- Power BI : lecture seule sur les données restituées
    CREATE ROLE powerbi_reader LOGIN PASSWORD '${POWERBI_PASSWORD}';
    -- Kestra : sa base interne
    CREATE ROLE kestra       LOGIN PASSWORD '${KESTRA_DB_PASSWORD}';

    -- ---------- Bases de données ----------
    CREATE DATABASE app    OWNER $POSTGRES_USER;
    CREATE DATABASE dwh    OWNER etl;
    CREATE DATABASE kestra OWNER kestra;

	-- ---------- Accès aux bases de données ----------
    -- Personne ne se connecte par défaut à une base qui ne le concerne pas
    REVOKE ALL ON DATABASE app, dwh, kestra FROM PUBLIC;
    GRANT CONNECT ON DATABASE app    TO app_writer, debezium;
    GRANT CONNECT ON DATABASE dwh    TO etl, powerbi_reader;
    GRANT CONNECT ON DATABASE kestra TO kestra;
EOSQL

# ---------- Base app : la source simulée (façon Strava) ----------
""" 
On execute la commande psql qui lance postgres conteneurisé (dans le cadre du docker-compose) via le superutilisateur
Le superutilisateur (POSTGRES_USER) n'est utilisé que pour l'administration et l'execution de ces commandes
Les instructions du bloc ci-dessous réalise, dans l'ordre
	- La révocation de tous les droits sur le schémas public de la base app
	- L'autorisation de rentrer dans le schémas (repertoire) 'public' de la base app pour les roles app_writer et debezium
	- La création de la table public.activites qui permet de stocker les activités générées par strava ou par notre générateur
	- La gestion des autorisation : lecture pour debezium, lecture ecriture pour app_writer (strava ou notre générateur)
	- La création de la publication sur la table public.activites qui permet à Debezium de recevoir en continu les modifications
"""
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname app <<-EOSQL
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE ON SCHEMA public TO app_writer, debezium;

    -- Table volontairement permissive : elle simule une source externe
    -- (API Strava) dont on ne maîtrise pas la qualité. Les contrôles métier
    -- (distance >= 0, date_fin > date_debut...) sont faits par Soda dans dwh.
    CREATE TABLE public.activites (
        id_activite     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        id_salarie      INTEGER      NOT NULL,
        date_debut      TIMESTAMPTZ  NOT NULL,
        type_activite   TEXT         NOT NULL,
        distance_m      INTEGER,                -- NULL si non pertinent (escalade...)
        date_fin        TIMESTAMPTZ  NOT NULL,
        commentaire     TEXT,
        source          TEXT         NOT NULL DEFAULT 'backfill',  -- backfill | live | strava
        cree_le         TIMESTAMPTZ  NOT NULL DEFAULT now()
    );

    GRANT SELECT, INSERT ON public.activites TO app_writer;
    GRANT SELECT          ON public.activites TO debezium;

    -- Publication logique lue par Debezium (plugin pgoutput).
    -- Créée ici par l'admin pour ne pas donner à Debezium le droit de la créer.
    CREATE PUBLICATION dbz_activites FOR TABLE public.activites;
EOSQL

# ---------- Base dwh : l'entrepôt analytique ----------
""" 
On execute la commande psql qui lance postgres conteneurisé (dans le cadre du docker-compose) via le superutilisateur
Le superutilisateur (POSTGRES_USER) n'est utilisé que pour l'administration et l'execution de ces commandes
Les instructions du bloc ci-dessous réalise, dans l'ordre
	- La révocation de tous les droits sur le schémas public de la base dwh
	- La création des différents schémas (sans création de tables pour l'instant) de la base dwh dont etl est propriétaire
	- L'accès aux schémas analytics et monitoring pour powerbi_reader;
	- La gestion des autorisations sur ces deux schémas : la lecture pour les tables d'analytics et de monitoring à powerbi_reader
	- La création d'une table de suivi pour les éxecution du pipeline (id, type de traitement, nombre de lignes concernées, etc)
"""
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname dwh <<-EOSQL
    REVOKE ALL ON SCHEMA public FROM PUBLIC;

    -- Schémas créés au nom du rôle etl, qui en est propriétaire
    SET ROLE etl;
    CREATE SCHEMA raw;          -- données brutes, jamais modifiées
    CREATE SCHEMA geo;          -- distances domicile-travail (Google Routes API)
    CREATE SCHEMA staging;      -- dbt : nettoyage
    CREATE SCHEMA analytics;    -- dbt : marts lus par Power BI
    CREATE SCHEMA monitoring;   -- suivi des exécutions et de la volumétrie

    -- Power BI : lecture seule sur analytics et monitoring,
    -- y compris sur les tables que dbt créera plus tard
    GRANT USAGE ON SCHEMA analytics, monitoring TO powerbi_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA analytics  GRANT SELECT ON TABLES TO powerbi_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA monitoring GRANT SELECT ON TABLES TO powerbi_reader;

    -- Journal des exécutions du pipeline (volumétrie + état d'exécution)
    CREATE TABLE monitoring.pipeline_runs (
        id_run        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        etape         TEXT        NOT NULL,   -- ex. ingestion_rh, geo, dbt, soda
        debut         TIMESTAMPTZ NOT NULL DEFAULT now(),
        fin           TIMESTAMPTZ,
        statut        TEXT        NOT NULL DEFAULT 'en_cours',  -- en_cours | succes | echec
        nb_lignes     INTEGER,
        message       TEXT
    );
    RESET ROLE;
EOSQL

echo "✅ Initialisation PostgreSQL terminée"
