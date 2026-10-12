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


@dataclass(frozen=True)
class ResultatControle:
    data_source: str
    table_verifiee: str | None
    controle: str
    resultat: str
    valeur: float | None


def _valeur(check: dict) -> float | None:
    """Valeur mesurée par Soda, si elle est numérique."""
    valeur = (check.get("diagnostics") or {}).get("value")
    return float(valeur) if isinstance(valeur, int | float) else None


def lancer_scan(fichier: str, data_source: str) -> tuple[list[ResultatControle], list[str]]:
    """Exécute un fichier de contrôles. Renvoie les résultats et les erreurs
    techniques éventuelles (connexion impossible, contrôle mal écrit...)."""
    scan = Scan()
    scan.set_scan_definition_name(f"projet12_{fichier}")
    scan.set_data_source_name(data_source)
    scan.add_configuration_yaml_file(str(CONFIGURATION))
    scan.add_sodacl_yaml_file(str(DOSSIER_SODA / "checks" / f"{fichier}.yml"))
    scan.execute()

    resultats = [
        ResultatControle(
            data_source=data_source,
            table_verifiee=check.get("table"),
            controle=check.get("name") or check.get("definition", "?"),
            resultat=check.get("outcome") or "erreur",
            valeur=_valeur(check),
        )
        for check in scan.get_scan_results().get("checks", [])
    ]
    erreurs = [log_.message for log_ in scan.get_error_logs()] if scan.has_error_logs() else []
    return resultats, erreurs


def enregistrer(conn: psycopg.Connection, resultats: list[ResultatControle],
                erreurs: list[str], debut: datetime, fin: datetime) -> str:
    """Écrit le détail et la synthèse. Renvoie le statut global."""
    execution_id = uuid.uuid4()
    nb = {r: sum(1 for c in resultats if c.resultat == r) for r in ("pass", "warn", "fail", "erreur")}
    statut = "echec" if nb["fail"] or nb["erreur"] or erreurs else "succes"
    message = (f"{nb['pass']} OK, {nb['warn']} avertissement(s), {nb['fail']} échec(s)"
               + (f", {len(erreurs)} erreur(s) technique(s)" if erreurs else ""))

    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.executemany(
            """INSERT INTO monitoring.qualite_checks
               (execution_id, verifie_le, data_source, table_verifiee, controle, resultat, valeur)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [(execution_id, fin, r.data_source, r.table_verifiee, r.controle, r.resultat, r.valeur)
             for r in resultats],
        )
        cur.execute(
            """INSERT INTO monitoring.pipeline_runs (etape, debut, fin, statut, nb_lignes, message)
               VALUES ('qualite_soda', %s, %s, %s, %s, %s)""",
            (debut, fin, statut, len(resultats), message),
        )
    conn.commit()
    log.info("Résultat : %s -> %s", message, statut)
    return statut
