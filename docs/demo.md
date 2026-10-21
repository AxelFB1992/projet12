# Déroulé de la démo — POC Avantages sportifs

Toutes les commandes se lancent depuis la racine du projet (`~/Projet12/projet12`).

Trois terminaux :

| Terminal | Rôle |
|---|---|
| **T1** | commandes |
| **T2** | `docker logs -f p12-chargement` : suivi du chargement dans l'entrepôt |
| **T3** | `docker logs -f p12-slack` : suivi des messages Slack |

Les consommateurs tournent dans leurs conteneurs : **Ctrl+C dans T2/T3 arrête
seulement l'affichage**, pas le consommateur.

Qui fait quoi :

| Étape | Qui |
|---|---|
| Démarrer l'infrastructure (Postgres, Redpanda, Debezium, consommateurs) | `docker compose` |
| Simuler Strava (historique, séances en direct, anomalies) | **à la main** : c'est la source externe |
| Chargement dans l'entrepôt, messages Slack | **automatique** (consommateurs) |
| Ingestion → geo → seeds → Soda → dbt → Soda | **à la main** (2A) ou **Kestra** (2B) |

À chaque étape : d'abord la version manuelle, puis la version Kestra quand elle existe.

---

## 0. Avant la démo : repartir d'une base propre

Le `.env` doit contenir toutes les variables de `.env.example`.
Kestra n'est **pas** démarré ici : il n'est pas nécessaire au temps réel, et on
économise de la RAM pendant la démo manuelle (il est lancé en 2B).

```bash
docker compose down -v                 # efface TOUTES les données (bases, topics, Kestra)
docker compose up -d --build postgres redpanda redpanda-console debezium chargement slack
docker compose ps                      # postgres et redpanda : (healthy), les autres : Up
sleep 15
docker logs p12-postgres 2>&1 | grep -iE "error|fatal|unbound|not found|initialisation"
# attendu : la ligne ✅ (et éventuellement "sh: locale: not found", sans importance)
```

Ouvrir T2 et T3 :

```bash
docker logs -f p12-chargement          # T2 : "En écoute sur app.public.activites..."
docker logs -f p12-slack               # T3 : "Vue raw.noms_salaries indisponible..." (normal : pas encore d'ingestion)
```

Contrôle du code :

```bash
uv run ruff check src tests && uv run pytest -q
```

---

## 1. Historique Strava (12 mois)

Strava a déjà un historique quand notre système se branche dessus : on le génère
**avant** le pipeline batch (sinon le contrôle Soda « des activités ont été
chargées » échoue et le pipeline s'arrête).

```bash
# T1
uv run --env-file .env python -m projet12.generation generer_historique --graine 42
```

→ T2 charge ~7 900 activités. T3 ne publie rien : l'historique n'est jamais annoncé
sur Slack.

---

## 2A. Pipeline batch : démo MANUELLE

Mêmes étapes, même ordre que le flow Kestra :

```bash
# 1. Référentiels RH et sport (+ vue des noms pour Slack)
uv run --env-file .env python -m projet12.ingestion

# 2. Distances domicile-bureau (Google Routes API, avec cache)
uv run --env-file .env python -m projet12.geo

# 3. Seeds dbt (paramètres + vitesses max, utilisés par Soda)
cd dbt && uv run --env-file ../.env dbt seed --profiles-dir . && cd ..

# 4. Contrôles qualité des SOURCES (un échec => on ne lance pas les calculs)
uv run --env-file .env python -m projet12.qualite --seulement raw geo

# 5. Calculs et tests dbt
cd dbt && uv run --env-file ../.env dbt build --profiles-dir . && cd ..

# 6. Contrôles qualité des RÉSULTATS (tables lues par Power BI)
uv run --env-file .env python -m projet12.qualite --seulement analytics
```

Résultats :

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select nb_eligibles_prime, cout_prime, nb_eligibles_bien_etre, cout_bien_etre, cout_total
from analytics.kpi_synthese;"
```

L'ingestion a aussi créé la vue des noms pour Slack. Droits du rôle `slack_notifier` :

```bash
docker exec -it p12-postgres psql -U slack_notifier -d dwh -c "select * from raw.noms_salaries limit 3;"   # OK
docker exec -it p12-postgres psql -U slack_notifier -d dwh -c "select salaire_brut from raw.salaries limit 1;"  # permission denied
```

---

## 2B. Pipeline batch : démo KESTRA

Démarrer Kestra, puis importer le flow (après un `down -v`, sa base est vide) :

```bash
docker compose up -d --build kestra
docker logs -f p12-kestra              # attendre "Server Running", puis Ctrl+C
set -a && . ./.env && set +a
curl -s -u "$KESTRA_ADMIN_EMAIL:$KESTRA_ADMIN_PASSWORD" \
     -X POST http://localhost:8080/api/v1/main/flows \
     -H "Content-Type: application/x-yaml" \
     --data-binary @kestra/flows/pipeline_avantages.yml | head -c 300; echo
# attendu : {"id":"pipeline_avantages","namespace":"sport_data",...
```

1. Ouvrir http://localhost:8080 (identifiants : `KESTRA_ADMIN_EMAIL` / `KESTRA_ADMIN_PASSWORD` du `.env`).
2. **Flows → sport_data.pipeline_avantages → Execute**, champs vides.
3. Suivre les tâches (vue **Gantt**, logs) : ingestion → geo → seeds → contrôles
   des sources → dbt → contrôles des résultats.
4. Montrer l'onglet **Triggers** : exécution planifiée chaque nuit à 2 h.

Même résultat qu'en 2A (requête `kpi_synthese` ci-dessus). Si 2A a déjà été faite,
Kestra refait simplement les mêmes étapes : elles sont toutes rejouables.

> Après un `down -v`, la **première** exécution est plus longue : Kestra réinstalle
> l'environnement Python du projet dans son volume. La lancer une fois avant la démo.

---

## 3. Temps réel : une séance → un message Slack

À lancer **après** le pipeline batch (2A ou 2B) : c'est l'ingestion qui crée la vue
des noms.

```bash
# T1
uv run --env-file .env python -m projet12.generation simuler_n_seance  --n 3
```

→ T3 : « Annuaire : 161 salarié(s) » (premier salarié inconnu → relecture de la vue),
puis 3 messages avec les vrais noms. T2 : 3 lignes chargées.

Variante « au fil de l'eau » pendant qu'on parle : `simuler_n_seance --n 1 --intervalle 10`
(Ctrl+C pour arrêter la génération).

---

## 4. Changement de paramètre : relancer le calcul

**Manuel :**

```bash
cd dbt && uv run --env-file ../.env dbt build --profiles-dir . --vars '{taux_prime: 0.03, seuil_velo_km: 10}' && cd ..
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

## 5. Qualité : anomalies détectées

**Avertissements** : quelques séances erronées.

```bash
uv run --env-file .env python -m projet12.generation simuler_n_seance --n 10 --taux-anomalies 0.5
```

→ Slack n'annonce que les séances cohérentes.

- **Manuel :** `uv run --env-file .env python -m projet12.qualite` → anomalies signalées (⚠️), statut `succes`.
- **Kestra :** **Execute** → les contrôles des sources signalent les anomalies, le pipeline va jusqu'au bout.

**Échec** : beaucoup d'erreurs.

```bash
uv run --env-file .env python -m projet12.generation simuler_n_seance --n 100 --taux-anomalies 0.8
```

- **Manuel :** `uv run --env-file .env python -m projet12.qualite ; echo "code de sortie : $?"`
  → ❌, statut `echec`, code de sortie 1.
- **Kestra :** **Execute** → la tâche `qualite_sources` **échoue**, les calculs ne sont
  pas lancés (on ne publie pas de résultats faux), une **alerte arrive dans Slack**.

Historique des contrôles :

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select verifie_le, table_verifiee, controle, resultat, valeur
from monitoring.qualite_checks where resultat <> 'pass' order by verifie_le desc limit 10;"
```

> Ces anomalies restent en base (et bloquent désormais le pipeline) : pour une
> nouvelle répétition, repartir de l'étape 0.

---

## 6. Monitoring : état des exécutions et volumétrie

```bash
docker exec -it p12-postgres psql -U etl -d dwh -c "
select etape, statut, count(*) as executions, sum(nb_lignes) as lignes, max(fin) as derniere
from monitoring.pipeline_runs group by 1, 2 order by 1;"
```

Temps réel : chaque consommateur est actif et à jour (`MEMBERS 1`, `LAG 0`) :

```bash
docker exec -it p12-redpanda rpk group describe dwh-loader
docker exec -it p12-redpanda rpk group describe slack-notifier
```

- Kestra : onglet **Executions** (historique des exécutions, durées, échecs).
- Redpanda Console (topics, messages, consommateurs) : http://localhost:8085
- Power BI : **Accueil → Actualiser**, pages Synthèse et Monitoring.

---

## 7. Arrêter

```bash
docker compose stop kestra # libère la RAM de Kestra, le reste continue
docker compose stop        # arrête tout, données conservées (reprise : docker compose start)
docker compose down        # supprime les conteneurs, données conservées (volumes)
docker compose down -v     # supprime aussi les données : retour à zéro
```

---

## Annexe — Commandes utiles

```bash
# Mettre à jour le flow Kestra après modification du fichier (il existe déjà)
set -a && . ./.env && set +a
curl -s -u "$KESTRA_ADMIN_EMAIL:$KESTRA_ADMIN_PASSWORD" \
     -X PUT http://localhost:8080/api/v1/main/flows/sport_data/pipeline_avantages \
     -H "Content-Type: application/x-yaml" \
     --data-binary @kestra/flows/pipeline_avantages.yml | head -c 300; echo

# Reconstruire l'image des consommateurs après une modification du code
docker compose up -d --build chargement slack

# Dernières lignes d'un consommateur, ou des deux à la fois
docker logs --tail 20 p12-slack
docker compose logs -f chargement slack
```
