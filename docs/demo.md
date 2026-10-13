# Déroulé de la démo — POC Avantages sportifs

Toutes les commandes se lancent depuis la racine du projet (`~/Projet12/projet12`),
sauf mention contraire. Prévoir 3 terminaux : **T1** (commandes), **T2** (chargement)
et **T3** (Slack).

---

## 0. Avant la démo : repartir d'une base propre

Les anomalies des tests précédents restent en base ; on repart de zéro.
Le `.env` doit contenir tous les mots de passe de `.env.example` (dont `SLACK_DB_PASSWORD`).

```bash
# Arrêter d'abord les consommateurs (Ctrl+C dans T2 et T3) s'ils tournent
docker compose down -v                # efface toutes les données Docker
docker compose up -d postgres redpanda redpanda-console debezium
docker compose ps                     # attendre (healthy) pour postgres et redpanda
docker logs p12-postgres 2>&1 | grep -iE "error|initialisation"   # seule la ligne ✅ attendue
```

Contrôle du code :

```bash
uv run ruff check src tests && uv run pytest -q
```

---

## 1. Chargements initiaux (communs aux deux démos)

L'ordre compte : **référentiels d'abord**, puis les activités.

```bash
# T1 — référentiels RH et sport (Excel -> raw.salaries, raw.sports)
uv run --env-file .env python -m projet12.ingestion

# T2 — chargement Redpanda -> entrepôt (crée raw.activites, puis reste à l'écoute)
uv run --env-file .env python -m projet12.chargement

# T1 — historique de 12 mois (une seule fois : ce n'est pas une étape récurrente)
uv run --env-file .env python -m projet12.generation backfill --graine 42
```

→ T2 charge ~7 900 activités (« Topic pas encore créé » avant le backfill : normal).
Si T2 ne charge rien après une minute : Ctrl+C et le relancer.

---

## 2A. Démo MANUELLE du pipeline batch (mêmes étapes, même ordre que Kestra)

```bash
# 1. Référentiels (déjà fait à l'étape 1 ; à relancer si les fichiers Excel changent)
uv run --env-file .env python -m projet12.ingestion

# 2. Distances domicile-bureau (Google Routes API, avec cache)
uv run --env-file .env python -m projet12.geo

# 3. Seeds dbt (paramètres + vitesses max, utilisés par Soda)
cd dbt
uv run --env-file ../.env dbt seed --profiles-dir .
cd ..

# 4. Contrôles qualité des SOURCES (un échec => on ne lance pas les calculs)
uv run --env-file .env python -m projet12.qualite --seulement raw geo

# 5. Calculs et tests dbt (paramètres par défaut) ; crée aussi la vue des noms pour Slack
cd dbt
uv run --env-file ../.env dbt build --profiles-dir .
cd ..

# 6. Contrôles qualité des RÉSULTATS (tables lues par Power BI)
uv run --env-file .env python -m projet12.qualite --seulement analytics
```

Résultats à montrer :

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select nb_eligibles_prime, cout_prime, nb_eligibles_bien_etre, cout_bien_etre, cout_total
from analytics.kpi_synthese;"
```

---

## 2B. Démo KESTRA du même pipeline

```bash
docker compose up -d --build kestra
docker logs -f p12-kestra             # attendre "Server Running", puis Ctrl+C
```

1. Ouvrir http://localhost:8080 (identifiants : `KESTRA_ADMIN_EMAIL` / `KESTRA_ADMIN_PASSWORD` du .env).
2. Après un `down -v`, recréer le flow : **Flows → Create**, coller `kestra/flows/pipeline_avantages.yml`, **Save**.
3. **Execute**, champs vides → suivre les 6 tâches (vue Gantt, logs).
4. Montrer l'onglet **Triggers** : exécution planifiée chaque nuit à 2 h.

---

## 2C. Consommateur Slack (après 2A ou 2B)

Il affiche le prénom et le nom **issus de notre référentiel RH** (vue `notifications.noms_salaries`,
créée par dbt), jamais ceux fournis par l'application source : c'est notre système qui contrôle
ce qui est publié sur le Slack de l'entreprise. Rôle dédié `slack_notifier` : lecture de cette
vue uniquement (aucun accès aux salaires, adresses, etc.).

```bash
# T3
uv run --env-file .env python -m projet12.slack
```

→ « Annuaire : 161 salarié(s) ».

Les noms sont lus **une fois au démarrage**. Lancé avant le premier `dbt build`, il démarre
quand même (messages « Bravo Un collègue ! ») : le relancer après dbt. Idem après l'ajout de
nouveaux salariés. Pour créer uniquement la vue des noms, sans attendre les activités :

```bash
cd dbt
uv run --env-file ../.env dbt build --profiles-dir . --select +noms_salaries
cd ..
```

---

## 3. Temps réel : une activité → un message Slack

```bash
uv run --env-file .env python -m projet12.generation live --n 3
```

→ 3 messages dans Slack (T3), 3 lignes chargées (T2).
Variante « au fil de l'eau » pendant qu'on parle : `live --n 1 --intervalle 10` (Ctrl+C pour arrêter).

---

## 4. Qualité : anomalies détectées

```bash
# Avertissements : quelques activités erronées
uv run --env-file .env python -m projet12.generation live --n 10 --taux-anomalies 0.5
uv run --env-file .env python -m projet12.qualite
```

→ Slack n'annonce que les activités cohérentes ; Soda signale les autres (⚠️), statut `succes`.

```bash
# Échec : beaucoup d'erreurs
uv run --env-file .env python -m projet12.generation live --n 100 --taux-anomalies 0.8
uv run --env-file .env python -m projet12.qualite ; echo "code de sortie : $?"
```

→ ❌, statut `echec`, code de sortie 1.
**Version Kestra** : relancer le flow → la tâche `qualite_sources` échoue, les calculs ne sont
pas lancés, une alerte arrive dans Slack.

Historique des contrôles :

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select verifie_le, table_verifiee, controle, resultat, valeur
from monitoring.qualite_checks where resultat <> 'pass' order by verifie_le desc limit 10;"
```

---

## 5. Changement de paramètre : relancer le calcul

**Manuel :**

```bash
cd dbt
uv run --env-file ../.env dbt build --profiles-dir . --vars '{taux_prime: 0.03, seuil_velo_km: 10}'
cd ..
```

**Kestra :** **Execute** → saisir `taux_prime = 0.03`, `seuil_velo_km = 10`, le reste vide.

Comparer avant / après :

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select calcule_le, taux_prime, seuil_velo_km, nb_eligibles_prime, cout_prime, cout_total
from analytics.historique_kpi order by calcule_le;"
```

Revenir aux valeurs par défaut : relancer sans `--vars` (ou Kestra avec les champs vides).

---

## 6. Monitoring : volumétrie et état des exécutions

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select etape, statut, count(*) as executions, sum(nb_lignes) as lignes, max(fin) as derniere
from monitoring.pipeline_runs group by 1, 2 order by 1;"
```

Redpanda Console (topics, messages, retard des consommateurs) : http://localhost:8085
