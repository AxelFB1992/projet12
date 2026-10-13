#!/usr/bin/env bash
# Renommages du code (à lancer depuis la racine du projet, sur un dépôt git propre).
# perl -pi : remplace dans le fichier ; \b = limite de mot (évite les remplacements partiels).
# L'ORDRE des étapes compte : chaque nom doit être libéré avant d'être réutilisé.
set -euo pipefail
GENE="src/projet12/generation/generateur.py"
MAIN="src/projet12/generation/__main__.py"
ECRI="src/projet12/generation/ecriture.py"
PROF="src/projet12/generation/profils.py"
GEN="src/projet12/generation/*.py tests/test_generation.py"
GEO="src/projet12/geo/__main__.py src/projet12/geo/distances.py src/projet12/geo/routes.py tests/test_geo.py"

# 1. La séance réelle : classe Activite -> Seance
perl -pi -e 's/\bActivite\b/Seance/g' $GEN

# 2. Les variables qui contiennent des séances : activite(s) -> seance(s)
#    (avant l'étape 5, qui réutilise le nom "activite" pour le type de sport)
perl -pi -e 's/\bactivites\b/seances/g; s/\bactivite\b/seance/g' $GENE $MAIN
perl -pi -e 's/\binserer_activites\b/inserer_seances/g' $MAIN $ECRI
#    ecriture.py contient aussi le NOM DE LA TABLE "activites" (COPY, SELECT) : on n'y touche pas
perl -pi -e 's/(Connection, )activites:/${1}seances:/; s/\bin activites:/in seances:/; s/len\(activites\)/len(seances)/' $ECRI
perl -pi -e 's/\bactivites = /seances = /; s/len\(activites\)/len(seances)/; s/\bin activites:/in seances:/' tests/test_generation.py

# 3. Le type de sport : ProfilActivite -> Activite
perl -pi -e 's/\bProfilActivite\b/Activite/g' $GEN

# 4. Son attribut : type_activite -> nom (activite.nom = "Course à pied"), dans la classe et sur
#    les objets "profil" seulement ; le champ type_activite des séances, la colonne en base,
#    dbt et Slack ne changent pas
perl -pi -e 's/^(\s*)type_activite: str/${1}nom: str/' $PROF
perl -pi -e 's/\bprofil\.type_activite\b/profil.nom/g' $GENE

# 5. Les variables "profil(s)" -> "activite(s)" (le nom est libre depuis l'étape 2)
#    (?<!\.) : on ne touche pas au nom du MODULE dans "from projet12.generation.profils import"
perl -pi -e 's/(?<!\.)\bprofils\b/activites/g; s/(?<!\.)\bprofil\b/activite/g' $GENE

# 6. Constantes et fonctions (noms uniques : pas de risque de toucher du texte)
perl -pi -e '
  s/\bPROFILS_PAR_SPORT\b/ACTIVITES_PAR_SPORT/g;
  s/\bPROFILS_OCCASIONNELS\b/ACTIVITES_OCCASIONNELLES/g;
  s/\bprofils_du_salarie\b/activites_du_salarie/g;
  s/\bsimuler_mesures\b/simuler_mesures_seance/g;
  s/\bheure_de_depart\b/simuler_heure_debut_seance/g;
  s/\bfrequence_hebdo\b/simuler_frequence_hebdomadaire/g;
  s/\bappliquer_anomalie\b/simuler_anomalie/g;
  s/\bgenerer_historique\b/simuler_historique_seances/g;
  s/\b_tirer_profil\b/choisir_activite/g;
  s/\bgenerer_live\b/simuler_n_seances/g;
' $GEN

# 7. geo
perl -pi -e 's/\bcalculer_lot\b/calculer_distances_par_lot/g' $GEO
#    "calculer" et "enregistrer" sont aussi des mots français des commentaires :
#    on ne remplace que dans le code (suivis de "(", d'une virgule en fin de ligne, ou en fin de ligne)
perl -pi -e 's/\bcalculer\b(?=\(|,\s*$|\s*$)/calculer_distances_trajets/g; s/\benregistrer\b(?=\(|,\s*$|\s*$)/enregistrer_distances_en_base/g' $GEO
#    preparer_table existe aussi dans chargement/ : on ne touche qu'au module geo
perl -pi -e 's/\bpreparer_table\b/preparer_table_geo/g' $GEO

# Les nouveaux noms changent l'ordre alphabétique des imports : ruff les retrie
uv run ruff check src tests --fix --select I

echo "Renommages appliqués. Vérifier : git diff, puis ruff et pytest."
