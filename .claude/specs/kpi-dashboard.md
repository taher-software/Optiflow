# Spec — KPI Dashboard & Stats Explorer (web frontend + backend /kpi)

**Design de référence (validé par le client) :** la maquette interactive
(artifact « Maquettes Dashboard KPI ») ; le frontend est déjà implémenté
fidèlement à cette maquette (pages `DashboardPage` / `StatsPage`, thème clair,
couleur = métrique). Ce spec est le contrat pour le **backend `/kpi/*`** qui
remplacera le mock (`frontend/src/utils/dashboardMock.ts`).

Statut : design figé + frontend livré sur mock (commit `b4ba54d2`).
Définitions KPI validées (§5bis, 2026-08-13). Backend à construire via la
Factory (api-agent → test-agent → review-agent).

---

## 1. Système de couleurs (décision client : thème CLAIR)

La couleur encode la MÉTRIQUE, jamais l'entité :
| Métrique | Teinte | Rampe (intensité ∝ volume, forte→faible) |
|---|---|---|
| Temps d'arrêt | rouge | `#dc2626 #ef4444 #f87171 #fca5a5` |
| Causes / nb d'arrêts (Pareto) | violet | `#6d28d9 #7c3aed #8b5cf6 #a78bfa` |
| Temps de réparation / MTTR | vert | `#059669 #10b981 #34d399 #6ee7b9` |
| Accents UI (drill-down, sélection) | teal | `#0d9488` |
| Comparaison épisodes | ép.1 `#dc2626` ↔ ép.2 `#2563eb` (paire validée CVD — ne pas remplacer le bleu par du vert) |

Tokens : ground `#fafafa`, cartes `#ffffff`, encre `#16181d`/`#4b5563`/`#9ca3af`.
Rangée type : `libellé (+ méta) | barre | valeur | ›` — nuance par ratio
valeur/max (seuils 0.8 / 0.55 / 0.3).

## 2. Écrans (déjà implémentés, mock)

- **Dashboard** (`/app`) : nom du namespace, 4 KPI (Temps d'arrêt · Nb ·
  MTTR · MTBF — disponibilité supprimée en révision 2, §5bis.3 ; le temps
  d'arrêt est pondéré par poste et porte un hint qui l'explique, §5bis.1bis),
  période Aujourd'hui/7j/30j/plage ; cartes :
  par équipe (si `shift_number>1`), par UAP (sinon lignes, sinon postes),
  Pareto processus (% + cumul), réparation par processus, par type. Boutons
  « Explorer les stats » et « ⇄ Comparer » en haut à droite.
- **Drill-down** : fil d'Ariane, filtres locaux processus/équipe, jamais sa
  propre dimension, descente UAP→lignes→postes (saut si UAP sans lignes),
  type → badge processus associé (pas de filtre/section processus),
  processus → MTTR + nb d'arrêts par intervenant.
- **Stats** (`/app/stats`, dernier item de la nav) : onglets Suivi | Comparer,
  métrique Temps d'arrêt/Nb/MTTR, filtres scope/processus/équipe/période,
  bargraph journalier ; comparaison = 2 cartes de filtres indépendantes,
  totaux + écart %, barres groupées J1→Jn.

## 3. Contrat backend `/kpi/*` (à construire — remplace le mock)

Types miroir : `frontend/src/constants/dashboard.ts`.

- `GET /kpi/dashboard?from&to` → `ApiResponse[DashboardData]` :
  `{ namespace: {name (= company_name du doc namespace), shift_number (settings),
  shifts: [{id: "1"|"2"|"3", start_time: "HH:MM", end_time: "HH:MM"}] (fenêtres
  réelles des settings — révision 2 ; liste vide si aucune n'est configurée),
  uap_count, line_count, station_count}, overall: Kpis,
  by_shift: BreakdownRow[], by_location: BreakdownRow[] (UAP si >1, sinon
  lignes si >1, sinon postes), pareto_by_process: [{id, share, cumulative}],
  repair_by_process: Bar[], by_type: BreakdownRow[] }`
- `GET /kpi/drilldown?path=<kind:id>[>kind:id...]&process&shift&from&to` →
  `ApiResponse[DrilldownData]` : `{ kpis, children (niveau hiérarchique
  suivant ; UAP sans lignes → postes), children_hint_key, et SEULEMENT les
  sections dont la dimension n'est ni dans le path ni fixée par filtre :
  pareto_by_process, repair_by_process, downtime_by_shift, downtime_by_type ;
  pour un processus : mttr_by_agent, count_by_agent }`
  Un type dans le path fixe aussi le processus (pas de pareto/repair).
- `GET /kpi/daily?metric&scope_kind&scope_id&process&shift&from&to` →
  `ApiResponse[{points: [{date, value}]}]` — bucketing par jour dans la tz du
  namespace. La comparaison = 2 appels côté client.
- `Kpis = { downtime_seconds, count, mttr_seconds, mtbf_seconds }`
  (disponibilité supprimée en révision 2, §5bis.3)
- Les horaires affichés à côté d'un libellé d'équipe (« Équipe 2 (14h–22h) »)
  viennent de `namespace.shifts`, **jamais** d'une table codée en dur.
- Scope = rôles de management (owner/admin/manager/production supervisor) ;
  tenant-scoped au namespace du caller.
- Options de scope frontend : réutiliser `/uaps`, `/production-lines`,
  `/workstations` existants (pas de nouvel endpoint).

## 4. Sources de données (existantes)

Tickets `down_time/{ns}/issues` : `created_at/acknowledged_at/resolved_at/
closed_at/rejected_at` (tz namespace), `status`, `process`, `down_time_type`,
`shift` (int|null — seulement namespaces multi-shifts, tickets récents),
`uap_id/production_line_id/workstation_id/down_time_scope`, `resolved_by`.
Settings `NamespaceSettings/{ns}/settings/{ns}` : `shift_number`, `shift_1..3
{start_time, end_time}`, `time_to_escalate` (pas de `break_minutes` : retiré en
révision 2 avec la disponibilité, §5bis.3). Namespace : `company_name`,
`timezone`.

Plomberie requise : `FirestoreClient.find_subdocuments` ne supporte que
l'égalité — ajouter le filtrage par plage (`>=`/`<=` sur `created_at`).

## 5bis. Définitions des KPIs — VALIDÉES par le client (2026-08-13, révision 2)

1. **Temps d'arrêt** d'un ticket = `created_at → resolved_at` si le ticket est
   **closed** ; sinon durée partielle `created_at → maintenant` (tz namespace),
   bornée à la fenêtre de la période interrogée.
1bis. **Pondération par poste (révision 2)** : le temps d'arrêt **agrégé** est
   compté **par poste de travail**. Chaque ticket porte un poids = nombre de
   postes affectés selon son `production_scope` : poste → 1 ; ligne → nb de
   postes de la ligne ; UAP → nb de postes des lignes de l'UAP ; usine → tous
   les postes du namespace. Poids plancher **1** (une ligne sans poste
   référencé compte 1, jamais 0). La pondération s'applique à **toute somme de
   temps d'arrêt** (overall, décorticages, pareto, barres `downtime_by_*`,
   métrique `duration` de `/kpi/daily`). Elle ne s'applique **pas** aux
   métriques d'effort humain : `count`, MTTR, temps de réparation par
   processus, MTTR/nb par intervenant. Le frontend **affiche l'explication**
   de cette pondération à l'utilisateur (hint sous le KPI temps d'arrêt).
2. **MTTR** = moyenne de `created_at → resolved_at` sur les tickets **closed**
   uniquement (non pondéré).
3. **Disponibilité : SUPPRIMÉE (révision 2)** — on connaît les ressources en
   arrêt mais pas celles planifiées pour travailler ; le ratio serait faux.
   Retirée du modèle `Kpis`, du dashboard et du drill-down. Conséquence :
   `break_minutes` (pause par shift) est **retiré** des settings backend ET de
   l'écran Settings frontend (plus aucune saisie de pause demandée).
4. **MTBF** = `temps de shift de la tranche / nb de pannes` — fenêtres de
   shifts des settings **sans** soustraction de pause ; namespace sans
   settings → 24 h/jour. (Décision d'implémentation : formule validée en
   révision 1 conservée, seul le terme « pause » disparaît avec
   `break_minutes`.) `null` quand la tranche n'a pas de dénominateur (lignes
   de décorticage).
5. Tickets historiques **sans champ `shift`** : **exclus** du décorticage par
   équipe (pas de bucket « non affecté »).
6. **MTTR par intervenant** : attribué à **`resolved_by`**.
7. **Processus d'un ticket (révision 2)** : lu **directement depuis le champ
   `process` stocké sur l'issue** (posé par `add_down_time` à la création,
   quel que soit le type) ; repli sur `DOWNTIME_TYPE_PROCESS[type]` pour les
   documents hérités sans `process` valide.

## 6. Divers
- i18n FR/EN ; `tabular-nums` ; états loading/error/empty (skill frontend).
- Reproduire en test la structure « UAP sans lignes » (saut direct aux postes).
- Swap frontend : uniquement `fetchDashboard`/`fetchSeries` des 2 stores +
  `mockScopeOptions` → stores ressources réels.
