#!/usr/bin/env bash
# À lancer APRÈS renommer.sh. Convention :
#   - un objet Activite      -> "activite"
#   - le nom d'une activité  -> "nom_activite" (chaîne, ex. "Course à pied")
# Côté Python seulement : la COLONNE "type_activite" de la base ne change pas
# (la correspondance attribut -> colonne est faite dans ecriture.py, liste COLONNES).
set -euo pipefail

# generateur.py : champ de Seance, arguments nommés, paramètre et corps de choisir_commentaire
#   (aucune requête SQL dans ce fichier : on peut tout renommer)
perl -pi -e 's/\btype_activite\b/nom_activite/g' src/projet12/generation/generateur.py

# __main__.py : lectures sur les séances + variable de la boucle de résumé (pas de SQL non plus)
perl -pi -e 's/\btype_activite\b/nom_activite/g' src/projet12/generation/__main__.py

# ecriture.py et tests : seulement l'attribut des séances ; "type_activite" dans COLONNES reste
perl -pi -e 's/\ba\.type_activite\b/a.nom_activite/g' \
  src/projet12/generation/ecriture.py tests/test_generation.py

echo "Fait. Vérifier : git diff, puis ruff et pytest."
