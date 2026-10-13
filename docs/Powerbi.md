# Rapport Power BI — Avantages sportifs

Connexion : PostgreSQL `localhost:5433`, base `dwh`, mode **Importer**, rôle `powerbi_reader`
(accès en lecture à `analytics` et `monitoring` uniquement, aucune donnée nominative).

Après chaque exécution du pipeline (manuelle ou Kestra) : **Accueil → Actualiser**.

---

## 1. Modèle de données

Tables importées :

| Table | Grain | Usage |
|---|---|---|
| `analytics_avantages_salaries` | 1 ligne par salarié | coûts, éligibilités, contrôle des déclarations |
| `analytics_activites` | 1 ligne par activité | pratique sportive |
| `analytics_kpi_synthese` | 1 ligne | paramètres en vigueur |
| `analytics_historique_kpi` | 1 ligne par exécution de dbt | simulation de paramètres |
| `analytics_parametres` | 1 ligne | (facultatif) valeurs par défaut |
| `monitoring_pipeline_runs` | 1 ligne par étape exécutée | état d'exécution, volumétrie |
| `monitoring_qualite_checks` | 1 ligne par contrôle Soda | qualité des données |

**Renommer les tables** (double-clic dans le volet Données) en remplaçant l'espace par un underscore :
`analytics avantages_salaries` → `analytics_avantages_salaries`, etc. On garde ainsi le schéma
d'origine visible, et les noms s'écrivent sans apostrophes dans les mesures DAX.

**Relation** (vue Modèle) : `analytics_avantages_salaries[id_salarie]` (1) → `analytics_activites[id_salarie]` (*),
filtrage dans un seul sens. Les autres tables restent indépendantes.

**Mise en forme** (vue Données) :
- `montant_prime`, `cout_bien_etre`, `cout_*` : devise €, 0 décimale ;
- `taux_prime` : pourcentage ;
- `mois` : format « mmm aaaa » ; `jour_semaine` : 1 = lundi.

---

## 2. Mesures DAX

Créer une table de mesures vide (**Accueil → Entrer des données**, nommée `_Mesures`) puis
**Nouvelle mesure** pour chacune :

```DAX
Coût prime = SUM ( analytics_avantages_salaries[montant_prime] )

Coût bien-être = SUM ( analytics_avantages_salaries[cout_bien_etre] )

Coût total = [Coût prime] + [Coût bien-être]

Nb salariés = COUNTROWS ( analytics_avantages_salaries )

Nb éligibles prime =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[eligible_prime] = TRUE () )

Nb éligibles bien-être =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[eligible_bien_etre] = TRUE () )

% éligibles bien-être = DIVIDE ( [Nb éligibles bien-être], [Nb salariés] )

Déclarations à vérifier =
    CALCULATE (
        COUNTROWS ( analytics_avantages_salaries ),
        analytics_avantages_salaries[statut_declaration] IN { "suspecte", "non vérifiée" }
    )

Proches du seuil bien-être =
    VAR seuil = MAX ( analytics_kpi_synthese[nb_activites_min] )
    RETURN
        CALCULATE (
            COUNTROWS ( analytics_avantages_salaries ),
            analytics_avantages_salaries[nb_activites] >= seuil - 5,
            analytics_avantages_salaries[nb_activites] < seuil
        )

Nb activités valides =
    CALCULATE ( COUNTROWS ( analytics_activites ), analytics_activites[est_valide] = TRUE () )

Distance totale (km) =
    CALCULATE ( SUM ( analytics_activites[distance_km] ), analytics_activites[est_valide] = TRUE () )

Dernière exécution = MAX ( monitoring_pipeline_runs[fin] )

Étapes en échec (7 j) =
    CALCULATE (
        COUNTROWS ( monitoring_pipeline_runs ),
        monitoring_pipeline_runs[statut] = "echec",
        monitoring_pipeline_runs[debut] >= NOW () - 7
    )

Contrôles non conformes (dernier passage) =
    VAR dernier = MAX ( monitoring_qualite_checks[verifie_le] )
    RETURN
        CALCULATE (
            COUNTROWS ( monitoring_qualite_checks ),
            monitoring_qualite_checks[verifie_le] = dernier,
            monitoring_qualite_checks[resultat] <> "pass"
        )
```

---

## 3. Pages du rapport

### Page 1 — Synthèse (pour Juliette)
- **Cartes** : Coût total · Coût prime · Coût bien-être · Nb éligibles prime · Nb éligibles bien-être · Nb activités valides.
- **Carte multiligne** « Paramètres en vigueur » (table `analytics_kpi_synthese`) : `taux_prime`, `seuil_marche_km`, `seuil_velo_km`, `nb_activites_min`, `nb_jours_bien_etre_par_salarie`.
- **Anneau** : répartition Coût prime / Coût bien-être.
- **Barres** : Coût total par `bu`.

### Page 2 — Prime sportive (contrôle des déclarations)
- **Barres** : nombre de salariés par `statut_declaration` (conforme, suspecte, non vérifiée, non concerné).
- **Barres empilées** : `moyen_deplacement` × `statut_declaration`.
- **Nuage de points** : `distance_km` (axe X) par salarié, couleur = `statut_declaration`, ligne de référence = seuil.
- **Table** (pour les RH) : `id_salarie`, `bu`, `moyen_deplacement`, `distance_km`, `seuil_km`, `statut_declaration`, filtrée sur « suspecte » et « non vérifiée ».
- **Carte** : Déclarations à vérifier.

### Page 3 — Pratique sportive et bien-être
- **Courbe** : Nb activités valides par `mois`, légende = `source` (backfill / live).
- **Barres** : Nb activités valides par `type_activite`.
- **Colonnes** : Nb activités valides par `jour_semaine`.
- **Histogramme** : nombre de salariés par `nb_activites` (analytics_avantages_salaries), avec une ligne au seuil (15).
- **Cartes** : % éligibles bien-être · Proches du seuil bien-être (levier d'animation : salariés à moins de 5 activités du seuil).
- **Segments** : `bu`, `tranche_age`.

### Page 4 — Simulation de paramètres (historique)
- **Table** `analytics_historique_kpi` : `calcule_le`, `taux_prime`, `seuil_marche_km`, `seuil_velo_km`, `nb_activites_min`, `nb_eligibles_prime`, `cout_prime`, `nb_eligibles_bien_etre`, `cout_total`.
- **Courbe** : `cout_total` et `cout_prime` par `calcule_le`.
- Texte : « Relancer le calcul avec d'autres paramètres : formulaire Kestra (bouton Execute) ou
  `dbt build --vars`. Chaque exécution ajoute une ligne. »

### Page 5 — Monitoring
- **Cartes** : Dernière exécution · Étapes en échec (7 j) · Contrôles non conformes (dernier passage).
- **Table** `monitoring_pipeline_runs` triée par `debut` décroissant : `etape`, `debut`, `fin`, `statut`, `nb_lignes`, `message`
  (mise en forme conditionnelle : `statut` = echec en rouge).
- **Colonnes** : somme de `nb_lignes` par `etape` (volumétrie traitée).
- **Table** `monitoring_qualite_checks` filtrée sur `resultat` ≠ pass : `verifie_le`, `table_verifiee`, `controle`, `resultat`, `valeur`.

---

## 4. Limites et évolutions (à citer en soutenance)

- Actualisation manuelle dans Power BI Desktop ; en production : publication sur Power BI Service
  + passerelle de données + actualisation planifiée après le pipeline Kestra.
- Connexion sans chiffrement en local ; en production : SSL sur Postgres.
- Sécurité au niveau des lignes (RLS) possible, par exemple un manager ne voit que sa BU.
