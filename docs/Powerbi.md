# Rapport Power BI — Avantages sportifs

Connexion : PostgreSQL `localhost:5433`, base `dwh`, mode **Importer**, rôle `powerbi_reader`
(accès en lecture à `analytics` et `monitoring` uniquement, aucune donnée nominative).

Après chaque exécution du pipeline (manuelle ou Kestra) : **Accueil → Actualiser**.

---

## 1. Notions et réglages Power BI utilisés dans ce guide

### Noms des visuels

Dans le volet **Visualisations**, les icônes n'ont pas de libellé : le nom exact s'affiche
**au survol de la souris**.

| Nom du visuel | Forme |
|---|---|
| **Carte** | un chiffre seul |
| **Carte multiligne** | plusieurs chiffres empilés |
| **Graphique à barres groupées** | barres **horizontales** |
| **Graphique à barres empilées** | barres horizontales découpées en couleurs (une par valeur de la légende) |
| **Histogramme groupé** | barres **verticales** (colonnes). Attention : ce n'est pas un histogramme statistique |
| **Graphique en courbes** | courbe |
| **Graphique en anneau** | anneau (camembert évidé) |
| **Nuage de points** | un point par élément, placé selon deux valeurs numériques (X et Y) |
| **Table** | tableau de lignes et de colonnes |
| **Segment** | filtre cliquable posé sur la page (icône entonnoir) |

### Zones d'un visuel

Quand un visuel est sélectionné, le volet Visualisations affiche ses **zones** : *Axe X*,
*Axe Y*, *Légende*, *Valeurs*, *Colonnes*… On y fait glisser les champs depuis le volet
**Données** (à droite).

À droite de chaque champ placé dans une zone, une **petite flèche ˅** ouvre le **menu du
champ**. C'est là que se trouvent les deux réglages ci-dessous.

### « Ne pas résumer »

Power BI **additionne** par défaut les colonnes numériques (icône **Σ** dans le volet Données).
C'est faux pour un identifiant, un numéro de jour, un taux ou un seuil.
- Pour un visuel : menu du champ (˅) → **Ne pas résumer**.
- Une fois pour toutes : sélectionner la colonne dans le volet Données → ruban
  **Outils de colonne → Récapitulation → Ne pas résumer** (le Σ disparaît).

### « Hiérarchie de dates »

Une colonne de date placée dans un visuel est découpée par défaut en **Année → Trimestre → Mois
→ Jour**, et l'heure est perdue. Les lignes d'un même jour sont alors **fusionnées**.
Pour garder la date complète avec l'heure : menu du champ (˅) → choisir le **nom de la colonne**
(par exemple `calcule_le`) au lieu de « Hiérarchie de dates ».

### Mesure ou colonne calculée

- Une **mesure** (clic droit sur une table → *Nouvelle mesure*, icône calculatrice) calcule
  **un résultat sur un ensemble de lignes** : un total, un nombre de salariés… Elle ne peut pas
  lire « la valeur » d'une colonne, puisqu'il y en a des milliers.
- Une **colonne calculée** (clic droit sur une table → *Nouvelle colonne*) calcule
  **une valeur pour chaque ligne**, par exemple le nom du jour à partir de son numéro.

### Trier un visuel

Un graphique est trié par défaut sur la **valeur** (la plus grande en premier). Pour le trier
sur l'axe : **« … »** en haut à droite du visuel → **Trier l'axe** → choisir le champ, puis
**Tri croissant**.

---

## 2. Modèle de données

Tables importées :

| Table | Grain | Usage |
|---|---|---|
| `analytics_avantages_salaries` | 1 ligne par salarié | coûts, éligibilités, contrôle des déclarations |
| `analytics_activites` | 1 ligne par activité (valide ou non) | pratique sportive |
| `analytics_kpi_synthese` | 1 ligne | paramètres en vigueur (ses chiffres ne réagissent pas aux filtres) |
| `analytics_historique_kpi` | 1 ligne par exécution de dbt | simulation de paramètres |
| `analytics_parametres` | 1 ligne | (facultatif) valeurs par défaut |
| `monitoring_pipeline_runs` | 1 ligne par étape exécutée | état d'exécution, volumétrie |
| `monitoring_qualite_checks` | 1 ligne par contrôle Soda et par exécution | qualité des données |

**Renommer les tables** (double-clic dans le volet Données) en remplaçant l'espace par un
underscore : `analytics avantages_salaries` → `analytics_avantages_salaries`, etc. Le schéma
d'origine reste visible, et les noms s'écrivent sans apostrophes dans les formules DAX.

**Relation** (vue Modèle) : `analytics_avantages_salaries[id_salarie]` (1) →
`analytics_activites[id_salarie]` (*), filtrage dans un seul sens. Les autres tables restent
indépendantes.

Conséquence : un filtre posé sur `analytics_avantages_salaries` (par exemple la BU) filtre
**aussi** les activités, mais pas l'inverse. Les segments se font donc sur les champs de
`analytics_avantages_salaries`.

**Mise en forme** (sélectionner la colonne, ruban **Outils de colonne**) :
- `montant_prime`, `cout_bien_etre`, `cout_*` : format **Devise → € Euro**, 0 décimale ;
- `taux_prime` : format **Pourcentage** ;
- `mois` : format « mmm aaaa » ;
- `id_salarie`, `jour_semaine`, `nb_activites`, `taux_prime`, `seuil_*`, `nb_*` des tables de
  paramètres et d'historique : **Récapitulation → Ne pas résumer**.

**Colonne calculée** `Jour` (clic droit sur `analytics_activites` → **Nouvelle colonne**,
pas *Nouvelle mesure*) :

```DAX
Jour =
SWITCH ( analytics_activites[jour_semaine],
    1, "Lundi", 2, "Mardi", 3, "Mercredi", 4, "Jeudi",
    5, "Vendredi", 6, "Samedi", 7, "Dimanche" )
```

Puis, la colonne `Jour` sélectionnée : **Outils de colonne → Trier par colonne → `jour_semaine`**
(sinon les jours sont triés par ordre alphabétique).

---

## 3. Mesures DAX

Créer une table de mesures vide (**Accueil → Entrer des données**, nommée `_Mesures`), puis
clic droit sur `_Mesures` → **Nouvelle mesure** pour chacune.

Le `+ 0` final de certaines mesures fait afficher **0** au lieu de « (Vide) » quand aucune ligne
ne correspond.

```DAX
Coût prime = SUM ( analytics_avantages_salaries[montant_prime] )

Coût bien-être = SUM ( analytics_avantages_salaries[cout_bien_etre] )

Coût total = [Coût prime] + [Coût bien-être]

Nb salariés = COUNTROWS ( analytics_avantages_salaries )

Nb sportifs déclarés =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[pratique_declaree] = TRUE () )

Nb trajets sportifs =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[trajet_sportif] = TRUE () )

Nb éligibles prime =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[eligible_prime] = TRUE () ) + 0

Nb éligibles bien-être =
    CALCULATE ( COUNTROWS ( analytics_avantages_salaries ), analytics_avantages_salaries[eligible_bien_etre] = TRUE () ) + 0

% éligibles bien-être = DIVIDE ( [Nb éligibles bien-être], [Nb salariés] )

Déclarations à vérifier =
    CALCULATE (
        COUNTROWS ( analytics_avantages_salaries ),
        analytics_avantages_salaries[statut_declaration] IN { "suspecte", "non vérifiée" }
    ) + 0

Proches du seuil bien-être =
    VAR seuil = MAX ( analytics_kpi_synthese[nb_activites_min] )
    RETURN
        CALCULATE (
            COUNTROWS ( analytics_avantages_salaries ),
            analytics_avantages_salaries[nb_activites] >= seuil - 5,
            analytics_avantages_salaries[nb_activites] < seuil
        ) + 0

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
    ) + 0

Contrôles non conformes (dernier passage) =
    VAR dernier = MAX ( monitoring_qualite_checks[verifie_le] )
    RETURN
        CALCULATE (
            COUNTROWS ( monitoring_qualite_checks ),
            monitoring_qualite_checks[verifie_le] = dernier,
            monitoring_qualite_checks[resultat] <> "pass"
        ) + 0
```

---

## 4. Pages du rapport

Pour chaque visuel : le type exact, puis le champ à placer dans chaque zone.

### Page 1 — Synthèse (pour Juliette)

**Cartes** (une carte par mesure) : `Coût total` · `Coût prime` · `Coût bien-être` ·
`Nb éligibles prime` · `Nb éligibles bien-être` · `Nb activités valides`.

**Carte multiligne** « Paramètres en vigueur », champs de `analytics_kpi_synthese` :
`taux_prime`, `seuil_marche_km`, `seuil_velo_km`, `nb_activites_min`,
`nb_jours_bien_etre_par_salarie`. Renommer chaque champ dans le visuel (double-clic sur le champ
dans la zone) pour remplacer « Somme de taux_prime » par « Taux de prime », etc.

**Graphique en anneau** — répartition des coûts

| Zone | Champ |
|---|---|
| Valeurs | `Coût prime`, `Coût bien-être` |

**Graphique à barres groupées** — coût par BU

| Zone | Champ |
|---|---|
| Axe Y | `bu` (`analytics_avantages_salaries`) |
| Axe X | `Coût total` |

### Page 2 — Prime sportive (contrôle des déclarations)

`statut_declaration` (table `analytics_avantages_salaries`) prend 4 valeurs :

| Valeur | Signification |
|---|---|
| `conforme` | trajet sportif déclaré et distance sous le seuil : éligible à la prime |
| `suspecte` | trajet sportif déclaré, mais distance au-dessus du seuil |
| `non vérifiée` | trajet sportif déclaré, mais distance absente ou calculée pour une ancienne adresse |
| `non concerné` | pas de trajet sportif déclaré |

Couleurs à fixer sur tous les visuels de la page (Format → Couleurs) : vert = conforme,
orange = suspecte, gris = non vérifiée, gris clair = non concerné.

**Graphique à barres groupées** — salariés par statut

| Zone | Champ |
|---|---|
| Axe Y | `statut_declaration` |
| Axe X | `Nb salariés` |

**Graphique à barres empilées** — statut selon le moyen de déplacement

| Zone | Champ |
|---|---|
| Axe Y | `moyen_deplacement` |
| Axe X | `Nb salariés` |
| Légende | `statut_declaration` |

Une barre par moyen de déplacement, découpée en couleurs par statut : les modes non sportifs
sont entièrement « non concerné ».

**Nuage de points** — distance de chaque trajet par rapport à son seuil

| Zone | Champ | Rôle |
|---|---|---|
| Valeurs (ou Détails) | `id_salarie` | un point par salarié (sinon tout est agrégé en un seul point) |
| Axe X | `distance_km` | distance domicile-bureau calculée par Google |
| Axe Y | `seuil_km` | 15 (marche) ou 25 (vélo) |
| Légende | `statut_declaration` | couleur du point |

- **Filtre du visuel** (volet Filtres → Filtres de ce visuel) : `statut_declaration` différent de
  « non concerné » (ces salariés n'ont pas de distance).
- Les points s'alignent sur deux lignes horizontales (15 et 25) : un point situé à droite de son
  propre seuil est une déclaration suspecte.
- Facultatif : volet **Analyse** (icône loupe) → lignes constantes sur l'axe X à 15 et 25, si la
  version le propose.

**Table** (pour les RH) — déclarations à contrôler

Colonnes : `id_salarie`, `bu`, `moyen_deplacement`, `distance_km`, `seuil_km`,
`statut_declaration` (`id_salarie` et `distance_km` en **Ne pas résumer**).
Filtre du visuel : `statut_declaration` = « suspecte » ou « non vérifiée ».

**Carte** : `Déclarations à vérifier`.

> Avec les paramètres par défaut, les 68 trajets sportifs sont conformes : la table est vide et la
> carte affiche 0. Pour la démo, lancer une simulation avec un seuil plus bas
> (`dbt build --vars '{seuil_velo_km: 10}'`), actualiser, puis revenir aux valeurs par défaut.

### Page 3 — Pratique sportive et bien-être

**Graphique en courbes** — activités par mois

| Zone | Champ |
|---|---|
| Axe X | `mois` (`analytics_activites`) |
| Axe Y | `Nb activités valides` |
| Légende | `source` (backfill / live) |

Sans séances live, la légende n'a qu'une valeur : lancer `generation simuler_n_seance --n 5` avant d'actualiser.

**Graphique à barres groupées** — activités par sport

| Zone | Champ |
|---|---|
| Axe Y | `type_activite` |
| Axe X | `Nb activités valides` |

**Histogramme groupé** — activités par jour de la semaine

| Zone | Champ |
|---|---|
| Axe X | `Jour` (colonne calculée, section 2) |
| Axe Y | `Nb activités valides` |

Puis **« … » → Trier l'axe → Jour**, et **Tri croissant** : Lundi → Dimanche.

**Histogramme groupé** — répartition des salariés par nombre d'activités

| Zone | Champ |
|---|---|
| Axe X | `nb_activites` (`analytics_avantages_salaries`), en **Ne pas résumer** |
| Axe Y | `Nb salariés` |
| Légende | `eligible_bien_etre` |

- Chaque barre = un nombre d'activités ; sa hauteur = le nombre de salariés qui en ont fait
  exactement autant.
- La légende colore différemment les barres sous le seuil (False) et à partir du seuil (True) :
  le seuil de 15 se voit sans ligne, et il se déplace si l'on simule un autre `nb_activites_min`.
- Si les barres sont trop fines : clic droit sur `nb_activites` → **Nouveau groupe** → type
  **Compartiment**, taille 5 (tranches 0-4, 5-9, 10-14, 15-19…).

**Cartes** : `% éligibles bien-être` · `Proches du seuil bien-être` (salariés à moins de
5 activités du seuil : levier d'animation pour les RH).

**Segments** : `bu` et `tranche_age`, pris dans **`analytics_avantages_salaries`** (pour filtrer
aussi les activités, voir la relation en section 2). Format → Paramètres du segment → style
*Vignette* ou *Liste déroulante*. Pour les appliquer à d'autres pages : onglet **Affichage →
Synchroniser les segments**.

### Page 4 — Simulation de paramètres (historique)

**Table** `analytics_historique_kpi` — une ligne par exécution de dbt

Colonnes : `calcule_le`, `taux_prime`, `seuil_marche_km`, `seuil_velo_km`, `nb_activites_min`,
`nb_eligibles_prime`, `cout_prime`, `nb_eligibles_bien_etre`, `cout_total`, `execution_id`.

Réglages indispensables, sinon Power BI fusionne les exécutions en une seule ligne :
1. `calcule_le` : menu du champ (˅) → choisir **`calcule_le`** et non « Hiérarchie de dates »
   (la date complète avec l'heure distingue chaque exécution).
2. Toutes les colonnes numériques : menu du champ → **Ne pas résumer**.
3. `execution_id` : identifiant unique de chaque exécution ; il garantit une ligne par
   exécution, même quand deux exécutions ont exactement les mêmes valeurs.

**Graphique en courbes** — évolution des coûts selon les simulations

| Zone | Champ |
|---|---|
| Axe X | `calcule_le` (sans hiérarchie de dates) |
| Axe Y | `cout_total`, `cout_prime` |

**Zone de texte** : « Relancer le calcul avec d'autres paramètres : formulaire Kestra (bouton
Execute) ou `dbt build --vars`. Chaque exécution ajoute une ligne. »

> Pour remplir la page : lancer quelques simulations (`--vars '{taux_prime: 0.03}'`,
> `--vars '{seuil_velo_km: 10}'`, puis sans `--vars`) et actualiser.

### Page 5 — Monitoring

**Cartes** : `Dernière exécution` · `Étapes en échec (7 j)` · `Contrôles non conformes (dernier passage)`.

**Table** `monitoring_pipeline_runs` — journal des exécutions

**Table** `monitoring_qualite_checks` — contrôles qualité en anomalie

Colonnes : `verifie_le`, `fichier_soda`, `table_verifiee`, `controle`, `resultat`, `valeur`.
- `verifie_le` sans hiérarchie de dates ; `valeur` en **Ne pas résumer**.
- Filtre du visuel (volet Filtres → Filtres de ce visuel → `resultat`, Filtrage de base) :
  cocher **warn**, **fail** et **erreur**, laisser **pass** décoché.
- Tri : clic sur l'en-tête `verifie_le`.
- Format → Éléments de cellule → couleur sur `resultat` : orange pour warn, rouge pour fail,
  violet (ou gris foncé) pour erreur.
- Une ligne `erreur` correspond à un contrôle **impossible à exécuter** (colonne inexistante,
  connexion perdue) : `table_verifiee` est vide et `controle` commence par « Erreur technique ».
- `valeur` dépend du contrôle : nombre de lignes, pourcentage, ou **millisecondes** pour la
  fraîcheur (diviser par 3 600 000 pour obtenir des heures).

> Si tous les contrôles sont « pass », la table est vide (base propre). Pour la démo :
> `generation simuler_n_seance --n 10 --taux-anomalies 0.5`, puis `python -m projet12.qualite`, puis Actualiser.

**Histogramme groupé** — volumétrie traitée par étape

| Zone | Champ |
|---|---|
| Axe X | `etape` |
| Axe Y | `nb_lignes` (Somme : ici, l'addition est voulue) |

**Table** `monitoring_qualite_checks` — contrôles qualité en anomalie

Colonnes : `verifie_le`, `table_verifiee`, `controle`, `resultat`, `valeur`.
- `verifie_le` sans hiérarchie de dates ; `valeur` en **Ne pas résumer**.
- Filtre du visuel (volet Filtres → Filtres de ce visuel → `resultat`, Filtrage de base) :
  cocher **warn**, **fail** et **erreur**, laisser **pass** décoché.
- Tri : clic sur l'en-tête `verifie_le`.
- Format → Éléments de cellule → couleur sur `resultat` : orange pour warn, rouge pour fail.

> Si tous les contrôles sont « pass », la table est vide (base propre). Pour la démo :
> `generation simuler_n_seance --n 10 --taux-anomalies 0.5`, puis `python -m projet12.qualite`, puis Actualiser.

---

## 5. Limites et évolutions

- Actualisation manuelle dans Power BI Desktop ; en production : publication sur Power BI Service
  + passerelle de données + actualisation planifiée après le pipeline Kestra.
- Connexion sans chiffrement en local ; en production : SSL sur PostgreSQL.
- Le fichier `.pbix` n'est pas versionné (le montant de la prime permet de retrouver les
  salaires) : versionner le modèle `.pbit` et des captures d'écran.
