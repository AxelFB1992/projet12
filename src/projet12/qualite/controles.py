"""Lancement des contrôles Soda et enregistrement des résultats.

Chaque fichier de soda/checks/ est associé à une "data source" (un schéma) de
soda/configuration.yml. Les résultats sont écrits dans :
  - monitoring.qualite_checks : une ligne par contrôle et par exécution
    (historique lu par Power BI) ;
  - monitoring.pipeline_runs  : une ligne de synthèse, comme les autres étapes.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg
from soda.scan import Scan

from projet12.config import RACINE

log = logging.getLogger("qualite")

DOSSIER_SODA = RACINE / "soda"
CONFIGURATION = DOSSIER_SODA / "configuration.yml"

# Fichier de contrôles -> data source (schéma) sur laquelle il s'exécute
CONTROLES = {
    "raw": "dwh_raw",
    "geo": "dwh_geo",
    "analytics": "dwh_analytics",
}

# Le résultats des contrôles qualité vont être dans la table monitoring.qualite_checks, d'où la nécessité de la créer
DDL = """
CREATE TABLE IF NOT EXISTS monitoring.qualite_checks (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id  UUID        NOT NULL,   -- regroupe les contrôles d'une même exécution
    verifie_le    TIMESTAMPTZ NOT NULL,
    data_source   TEXT        NOT NULL,   -- dwh_raw, dwh_geo, dwh_analytics
    table_verifiee TEXT,
    controle      TEXT        NOT NULL,   -- nom lisible du contrôle
    resultat      TEXT        NOT NULL,   -- pass | warn | fail | erreur
    valeur        NUMERIC                 -- valeur mesurée (nb de lignes, %...)
)
"""

# Classe permettant de stocker le résultat d'un contrôle Soda :
# -data_source : De quelle base proviennent les données analysées.
# -table_verifiee : la base de la table.
# -resultat : pass|warn|fail -> le test est passé| le test est passé mais il y a un warning| fail le test n'est pas passé.
#       -> Ces différents "niveaux de résultat" sont prévus dans les tests présents dans le fichier soda/checks/"{}".yml
# -valeur : valeur mesurée par le contrôle précis (Ex : Contôle "Pas d'activité en double" -> Valeur = nombre de doublons trouvés)
@dataclass(frozen=True)
class ResultatControle:
    data_source: str
    table_verifiee: str | None
    controle: str
    resultat: str
    valeur: float | None

# Permet de récuperer la valeur (en float) retournée par le côntôle Soda, stockée dans un dictionnaire
def _valeur(check: dict) -> float | None:
    """Valeur mesurée par Soda, si elle est numérique."""
    valeur = (check.get("diagnostics") or {}).get("value")
    return float(valeur) if isinstance(valeur, int | float) else None

# Fonction qui va lire les fichiers de côntrôle "Soda/checks/{}.yml", executer le côntole grâce à un objet de type soda.scan et retourner un résutlat via un objet de type ResultatControle
def lancer_scan(fichier: str, data_source: str) -> tuple[list[ResultatControle], list[str]]:
    """
    Cette fonction effectues les tâches suivantes : 
    -Exécute un fichier de contrôles (fichier "Soda/checks/{}.yml")
    -Renvoie les résultats et les erreurs techniques éventuelles (connexion impossible, contrôle mal écrit...).
    -Stocker ces résutlats/erreurs dans un objet de type ResultatControle (juste au dessus)
    """
    scan = Scan()
    # Les deux lignes ci-dessous permettent de fixer certains champ dans les résultats obtenus
    # Par exemple : le nom du scan, ici projet12_{fichier}
    scan.set_scan_definition_name(f"projet12_{fichier}")
    scan.set_data_source_name(data_source)
    # On ajoute à l'objet scan la configuration présente dans le fichier CONFIGURATION=configuration.yml (c'est à dire les paramètres de connexion aux bases de données)
    scan.add_configuration_yaml_file(str(CONFIGURATION))
    # On ajoute le fichier .yml spécifique des contrôles que l'on veut réaliser
    scan.add_sodacl_yaml_file(str(DOSSIER_SODA / "checks" / f"{fichier}.yml"))
    # On réalise les contrôles prévus par le fichier "Soda/checks/{}.yml"
    scan.execute()
    # On stocke les résultats du contrôle qui vient d'etre effectué et qui se trouve pour l'instant les éléments "checks" de l'objet Scan (voir le 'for' ci-dessous)
    resultats = [
        ResultatControle(
            # Le data source est celui que l'on a passé en paramètre du scan, reçu dans la signature de lancer_scan
            data_source=data_source,
            table_verifiee=check.get("table"),
            controle=check.get("name") or check.get("definition", "?"),
            resultat=check.get("outcome") or "erreur",
            # On récupère la valeur retournée par la méthode ci-dessous (_valeur) correspondant à la valeur mesurée par le test
            valeur=_valeur(check),
        )
        # Permet de parcourir tous les tests réalisés réalisés et prévu par le fichier "Soda/checks/{}.yml"
        for check in scan.get_scan_results().get("checks", [])
    ]
    # On récupère également les erreurs que l'on palce à part entière
    erreurs = [log_.message for log_ in scan.get_error_logs()] if scan.has_error_logs() else []
    return resultats, erreurs

# Cette méthode permet de stocker les résultat des contrôles réalisées par la méthode précedente dans les tables prévues à cette effet :
# monitoring.qualite_checks et monitoring.pipeline_runs
def enregistrer(conn: psycopg.Connection, resultats: list[ResultatControle],
                erreurs: list[str], debut: datetime, fin: datetime) -> str:
    """
    Cette fonction réalise les tâches suivantes : 
    -Compte les statuts des tests réalisés 
    -Ecrit les résultats des tests du contrôle dans la table monitoring.qualite_check
    -Ecrit la ligne de synthèse du contrôle réalisé, avec les status recensés plus tôt
    """
    # On génère un id d'execution permettant de rassembler tous les tests fait lors d'un contrôle
    execution_id = uuid.uuid4()
    # On calcule le nombre de tests au statut "pass", "warn", "fail" ou "erreur" que l'on stocke dans un grand variable nb
    nb = {r: sum(1 for c in resultats if c.resultat == r) for r in ("pass", "warn", "fail", "erreur")}
    # le statut du contrôle sera passé en échec si jamais il y a au moins une erreur ou un fail
    statut = "echec" if nb["fail"] or nb["erreur"] or erreurs else "succes"
    # On préparer le message que l'on va passer en paramètre de l'insertion à la table monitoring.pipeline_run qui recense le statut du contrôle global et non du tests
    message = (f"{nb['pass']} OK, {nb['warn']} avertissement(s), {nb['fail']} échec(s)"
               + (f", {len(erreurs)} erreur(s) technique(s)" if erreurs else ""))

    # On écrit les résultats en utilisant la variable 'conn' (en paramètre de la méthode) qui recense tous les paramètres de connection à la base dwh
    with conn.cursor() as cur:
        # On commence par créer monitoring.qualite_checks si elle n'existe pas
        cur.execute(DDL)
        # On écrit tous les résultats des tests qui sont stockés dans resultats en les parcourant un à un avec leurs valeurs
        cur.executemany(
            """INSERT INTO monitoring.qualite_checks
               (execution_id, verifie_le, data_source, table_verifiee, controle, resultat, valeur)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [(execution_id, fin, r.data_source, r.table_verifiee, r.controle, r.resultat, r.valeur)
             for r in resultats],
        )
        # On écrit le résultat global du "run" du contrôle courant dans la table monitoring.pipeline_runs, avec le statut global calculé ci-dessous (statut)
        cur.execute(
            """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes, message)
               VALUES ('qualite_soda', %s, %s, %s, %s, %s)""",
            (debut, fin, statut, len(resultats), message),
        )
    # On sauvagarde les bases de données à l'aide de commit
    conn.commit()
    # Et on affiche les résultats globaux que l'on vient de stocker dans monitoring.pipeline_runs
    log.info("Résultat : %s -> %s", message, statut)
    return statut
