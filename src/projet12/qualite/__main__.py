"""Contrôles de qualité des données (Soda Core).

Usage :
    uv run --env-file .env python -m projet12.qualite              # tous les contrôles
    uv run --env-file .env python -m projet12.qualite --schemas raw geo

Code de sortie : 0 si aucun échec (les avertissements sont acceptés), 1 sinon.
Kestra s'en servira pour arrêter le pipeline avant de publier les statistiques d'erreurs.
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

from projet12.config import connexion_dwh
from projet12.qualite.controles import CONTROLES, enregistrer, lancer_scan

log = logging.getLogger("qualite")

SYMBOLES = {"pass": "✅", "warn": "⚠️ ", "fail": "❌", "erreur": "💥"}


def main() -> int:
    # Toujours les lignes de configuration des logs, qui permet de spécifier le niveau d'affichage (info, warn, error)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    # Si le niveau du logger global est 'Info', celui du logger Soda est "Warning" pour éviter les écritures inutiles
    # Autrement dit, toutes les informations globales vont êter affiché, mais pas toutes les informations provenant de Soda
    #logging.getLogger("soda").setLevel(logging.WARNING)   # Soda est très bavard

    # On parle la commande pour obtenir les informations qui correspondent à cette partie de l'application
    parser = argparse.ArgumentParser(prog="python -m projet12.qualite",
                                     description="Contrôles de qualité des données (Soda).")
    # Le seul argument que l'on peut passer en paramètre est --seulement qui permet de définir les schémas sur lesquels on veut que les contrôles s'exercent
    parser.add_argument("--schemas", nargs="+", choices=list(CONTROLES),
                        help="Ne lancer que certains fichiers de contrôles (ex. raw geo)")
    # Permet d'afficher tous les détails des logs d'execution (notamment les erreurs) dans le terminal, seulement si on le souhaite
    parser.add_argument("--details", action="store_true",
                            help="Afficher les messages complets de Soda (SQL, erreurs)")
    
    # On parse avec les arguments donnés ci-dessus
    args = parser.parse_args()

    #On passe à un niveau d'affichage de base plus restrictif que Warning (ci-dessus) car Soda est très bavard (surtout si erreurs)
    logging.getLogger("soda").setLevel(logging.WARNING if args.details else logging.CRITICAL)
    
    # Les contrôles correspondant aux arguments de la commande sont écrits dans  "raw": "dwh_raw", "geo": "dwh_geo","analytics": "dwh_analytics",
    # Soit on stocke les noms des tables à contrôler dans à_lancer, soit on stocke toutes les tables pour toutes les controler.
    a_lancer = {f: CONTROLES[f] for f in args.schemas} if args.schemas else CONTROLES
    debut = datetime.now(UTC)
    # On se prépare à stocker les résultats et les erreurs séparés comme ils sont retournés par la méthode lancer_scan()
    #resultats, erreurs = [], [] --> plus d'actualité, déjà présents dans resultats[]
    resultats = []
    # On parcours les différents sources à contôler : l'intitulé de la source qu'on utilisera pour nommer les résultats et la véritable table en base de données
    for fichier, data_source in a_lancer.items():
        # On va afficher le résultat des contrôle dans le log qui est actuellement la sortie standard
        log.info("🔎 Contrôles %s (%s)", fichier, data_source)
        # On réalise les contrôles et on stocke les résultats dans res et dans err --> plus d'actualité, déjà présents dans resultats[]
        #res, err = lancer_scan(fichier, data_source)
        res = lancer_scan(fichier, data_source)
        # On commence par parcourir les résultats : le coeur du contrôle
        for r in res:
            # On affiche que lees résultat qui ne sont pas passés à savoir warn, fail ou erreur, car c'est ce qui nous interesse
            if r.resultat != "pass":
                cible = f"{r.data_source}.{r.table_verifiee}" if r.table_verifiee else r.data_source
                log.warning("   %s %s : %s (valeur : %s)", SYMBOLES.get(r.resultat, "?"),cible, r.controle, r.valeur)
        # On affiche ensuite les erreurs en affichant leur contenu --> plus d'actualité, déjà présents dans resultats[]
        #for e in err:
        #    log.error("   💥 %s", e)
        # Synthèse finale, qui reprend le nombre de "controles" (test) réalisés et le nombre de ceux qui sont un succès
        log.info("   %d contrôle(s), %d OK", len(res), sum(r.resultat == "pass" for r in res))
        # On ajoute à la variable global resultats les resultats courant correspondants à un schémas (et à toutes les tables qui le compose)
        resultats += res
        # On fait de même avec les erreurs --> plus d'actualité, déjà présents dans resultats[]
        #erreurs += err

    # Puis on écrit les résultats et les erreurs dans les tables monitoring.qualite_checks (résultats des controles) et monitoring.pipeline_run (synthèse des controles)
    with connexion_dwh() as conn:
        #statut = enregistrer(conn, resultats, erreurs, debut, datetime.now(UTC))
        statut = enregistrer(conn, resultats, debut, datetime.now(UTC))
    return 0 if statut == "succes" else 1


if __name__ == "__main__":
    sys.exit(main())
