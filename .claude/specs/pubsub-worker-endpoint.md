# BOM — Pub/Sub push worker endpoint (`POST /pubsub_job`)

Statut : contrat figé par l'orchestrateur (Lane FACTORY, branche
`feature/pubsub-worker-endpoint`). Source de vérité pour `test-agent`, puis
`api-agent`, `doc-agent`, `review-agent`.

## 1. Problème

`POST /cloud_job` accepte un corps **plat** (`{job_id, job_type, namespace_id,
payload}`) — c'est exactement ce que Cloud Tasks envoie (`gcp/cloud_tasks.py:create_task`).
Il est pourtant aussi cité comme endpoint de push **Pub/Sub**. Or un push Pub/Sub
livre une **enveloppe** :

```json
{
  "message": {
    "data": "<base64 du JSON publié>",
    "messageId": "123",
    "publishTime": "2026-08-28T10:00:00Z",
    "attributes": {}
  },
  "subscription": "projects/p/subscriptions/s"
}
```

Ce corps ne valide pas contre `CloudJobIn` → FastAPI répond **422** → Pub/Sub
considère l'échec et **redélivre indéfiniment**. Les jobs publiés par
`PubSubInteraction.publish_job` ne sont donc jamais exécutés.

## 2. Décision

Deux entrypoints, un seul moteur d'exécution :

| Route | Transport | Corps |
|---|---|---|
| `POST /cloud_job` | Cloud Tasks **uniquement** | corps plat `CloudJobIn` (inchangé) |
| `POST /pubsub_job` | Pub/Sub push **uniquement** | enveloppe push, transformée en `CloudJobIn` |

`/pubsub_job` **transforme** l'enveloppe puis délègue au service existant
`services.process_cloud_job(CloudJobIn)`. Aucune logique de dispatch dupliquée,
aucune modification de `/cloud_job` ni du registre `async_jobs`.

## 3. Artefacts

### 3.1 `src/app/routers/workers/modelsIn.py`
- `PubSubMessageIn` : `data: Optional[str]` (JSON encodé base64),
  `message_id: Optional[str]` (alias `messageId`), `publish_time: Optional[str]`
  (alias `publishTime`), `attributes: Optional[dict]`. Modèle **permissif**
  (champs inconnus ignorés) — un rejet 422 provoquerait une redélivraison infinie.
- `PubSubPushIn` : `message: PubSubMessageIn`, `subscription: Optional[str]`.
- `CloudJobIn` : **inchangé**.

### 3.2 `src/app/routers/workers/services.py`
- `process_pubsub_push(envelope: PubSubPushIn) -> CloudJobAckOut`
  1. décode `message.data` en base64 puis en JSON ;
  2. construit un `CloudJobIn` à partir de `{job_id, job_type, namespace_id, payload}`
     lus **au niveau racine** du JSON décodé — `job_type` est à la racine, à côté de
     `namespace_id`/`job_id`, **hors** du dict `payload` (c'est déjà ce que produit
     `publish_job`). Les champs supplémentaires (`attempt`, `created_at`) sont ignorés.
     `job_id` est **transmis tel quel** (`None` s'il est absent) — pas de repli sur
     `message.messageId` : l'idempotence manquante est déjà traitée en aval par le
     handler, ne pas la traiter deux fois.
  3. délègue à `process_cloud_job` et retourne son ack.
- **Toute enveloppe invalide est ack `200`**, jamais une 4xx/5xx : `data` absent,
  base64 invalide, JSON invalide, JSON qui n'est pas un objet, `job_type` absent,
  `message` absent, ou toute autre enveloppe que l'on ne peut pas convertir en
  `CloudJobIn` (ex. `namespace_id` manquant → `ValidationError` attrapée par la même
  branche générique, sans traitement dédié : le handler valide déjà son entrée).
  Motif : un non-2xx fait redélivrer le message par Pub/Sub à l'infini ; un message
  qui ne peut pas réussir ne doit jamais être requeue (même règle que `/cloud_job`).
- **Observabilité — obligatoire.** Chaque branche qui ack sans exécuter de job écrit un
  `logger.error` **avant** de retourner l'ack, identifiant la cause et ce que l'on sait du
  message (`messageId`, `subscription`, `job_type`/`job_id` si connus). Un ack silencieux
  rend un job perdu invisible en production. Un `payload` absent (job exécuté avec `{}`)
  est également logué en `error`.

### 3.3 `src/app/routers/workers/__init__.py`
- `POST /pubsub_job`, `response_model=ApiResponse[CloudJobAckOut]`, `status_code=200`,
  **sans authentification applicative** (OIDC infra, comme `/cloud_job`),
  `summary`/`description` OpenAPI décrivant l'enveloppe push et la garantie « toujours 200 ».
- `POST /cloud_job` : description resserrée sur **Cloud Tasks uniquement**.

### 3.4 Aucun changement
`async_jobs/*`, `gcp/pub_sub.py`, `gcp/cloud_tasks.py`, `JobType`.
Le format publié par `publish_job` est déjà compatible avec la transformation.

## 4. Scénarios attendus (base pour `test-agent`, à valider par le développeur)

Révision 2 — après annotations de revue du 2026-08-28 (source de `job_type` tranchée par
le développeur : racine du JSON décodé ; scénarios doublonnant le handler supprimés ;
logs d'observabilité rendus obligatoires et assertés).

1. Enveloppe push valide → handler du registre appelé une fois avec
   `(namespace_id, payload, job_id)`, réponse 200, `data.result` = retour du handler.
2. `payload` absent → handler appelé avec `{}`, **et** un `logger.error` est émis.
3. Champs `attempt` / `created_at` présents → ignorés, pas d'erreur.
4. `job_type` inconnu → ack 200, aucun handler appelé, `logger.error` émis.
5. `data` base64 invalide → ack 200, aucun handler appelé, `logger.error` émis.
6. JSON décodé invalide → ack 200, aucun handler appelé, `logger.error` émis.
7. JSON décodé non-objet → ack 200, aucun handler appelé, `logger.error` émis.
8. `data` absent → ack 200, aucun handler appelé, `logger.error` émis.
9. `job_type` absent du JSON décodé → ack 200, aucun handler appelé, `logger.error` émis.
10. `message` absent de l'enveloppe → ack 200 (jamais 422), `logger.error` émis.
11. Route accessible **sans** bearer token.
12. Non-régression : `/cloud_job` accepte toujours le corps plat Cloud Tasks et rejette
    l'enveloppe push en 422 (tests existants de `tests/api/test_down_time.py` verts).

**Supprimés en révision 2** (déjà couverts en aval par le handler — ne pas traiter deux
fois) : repli de `job_id` sur `message.messageId` ; cas dédié `namespace_id` manquant.

## 5. Acceptance (firewall)

- `POST /pubsub_job` exécute un job publié par `PubSubInteraction.publish_job` de bout en bout.
- Aucune entrée malformée ne produit un statut ≠ 200.
- Aucun ack sans exécution n'est silencieux : chaque branche loggue en `error` avant l'ack.
- `/cloud_job` et le registre `async_jobs` inchangés fonctionnellement ; suite existante verte.
