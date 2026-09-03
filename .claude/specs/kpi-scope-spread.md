# BOM — Diffusion descendante des tickets de scope large dans les KPI

Statut : contrat figé par l'orchestrateur (Lane FACTORY, branche
`feature/kpi-scope-spread`). Décisions produit validées par le développeur le 2026-09-02.
Source de vérité pour `test-agent`, puis `api-agent`, `doc-agent`, `review-agent`.

## 1. Le défaut

`_resolve_location` (`src/app/routers/kpi/services.py:739`) ne fait remonter une
localisation que **vers le haut** : un poste remonte à sa ligne, une ligne à son UAP.
Rien ne descend. Conséquence : un ticket déclaré au scope **plant** ne porte ni
`uap_id`, ni `production_line_id`, ni `workstation_id` — `_group_tickets_by_location`
(`:770`) le jette donc de **toutes** les lignes de la ventilation par localisation.

Un arrêt qui touche toute l'usine est précisément celui qui compte le plus, et c'est le
seul qui n'apparaît nulle part dans la ventilation.

Le même trou existe dans `_filter_by_scope` (`:1502`) : un drill-down sur l'UAP A exclut
les tickets plant. Les deux doivent être corrigés ensemble, sinon la ligne « UAP A » du
tableau de bord et l'écran de drill-down « UAP A » affichent deux chiffres différents
pour la même chose.

## 2. La règle — diffusion descendante symétrique

Un ticket appartient à une localisation `L` de type `kind` si `L` est **la localisation
du ticket, ou un descendant de celle-ci** :

| Scope du ticket | Apparaît dans les lignes… |
|---|---|
| `plant` | tous les UAP, toutes les lignes, tous les postes |
| `uap` | son UAP · toutes les lignes de cet UAP · tous les postes de ces lignes |
| `production line` | son UAP (inchangé) · sa ligne · tous les postes de cette ligne |
| `work station` | son UAP · sa ligne (inchangés) · son poste |

La remontée existante (`_resolve_location`) est **conservée telle quelle** : elle reste
la façon dont un ticket poste alimente la ligne « son UAP ».

Le scope est lu sur `down_time_scope` (valeurs `ProductionScope`), **comme
`_ticket_weight` le fait déjà** (`:689`). Un document légataire sans `down_time_scope`,
ou avec une valeur inconnue, garde **exactement** le comportement actuel : les ids
stockés, aucune diffusion. On ne devine pas un scope large à partir d'ids absents.

## 3. La pondération — la part propre de la ligne

`downtime_seconds` n'est pas une durée : c'est un **poste-seconde**
(`_compute_kpis:276` → `durée × weight_of(issue)`). `_ticket_weight` renvoie le nombre de
postes touchés.

Aujourd'hui le poids est une propriété du **ticket seul**. Dès qu'un ticket apparaît dans
plusieurs lignes, il faut décider du poids **dans chaque ligne**. Décision du
développeur : **la part propre de la ligne** — le nombre de postes que le ticket touche
*dans cette ligne-là*.

Exemple. Usine à 3 UAP : A = 10 postes, B = 6, C = 4 (20 au total). Un arrêt plant de
30 minutes. KPI d'en-tête : `30 × 20 = 600` poste-minutes.

| | UAP A (10) | UAP B (6) | UAP C (4) | Somme | En-tête |
|---|---|---|---|---|---|
| Poids plant entier | 30 × 20 = 600 | 30 × 20 = 600 | 30 × 20 = 600 | **1800** ✗ | 600 |
| **Part propre (retenu)** | 30 × 10 = 300 | 30 × 6 = 180 | 30 × 4 = 120 | **600** ✓ | 600 |

Le poids plant entier casse deux choses : la ventilation ne se réconcilie plus avec
l'en-tête (triple), et les trois lignes affichent le même chiffre — le classement dit que
A, B et C ont souffert autant, ce qui est faux (10 postes à l'arrêt contre 4).

**La durée n'est jamais divisée.** Chaque ligne affiche bien « cet UAP a été arrêté 30
minutes » ; seul le poids est local.

Poids attendu par type de ligne, pour un ticket diffusé :
- ligne `uap` → nombre de postes de cet UAP (somme des postes de ses lignes)
- ligne `line` → nombre de postes de cette ligne
- ligne `station` → 1
- plancher à **1** dans tous les cas, comme `_ticket_weight` aujourd'hui.

Un ticket **non diffusé** (déclaré exactement à ce niveau, ou remonté) garde le poids que
`_ticket_weight` lui donne déjà : ce contrat ne change aucun chiffre existant.

## 4. `count` et `mttr` — non pondérés, décision explicite

`count` est `len(count_source)` (`:279`) et n'est jamais pondéré. Un ticket diffusé
comptera donc **1 dans chaque ligne** où il apparaît : trois lignes UAP à 1 pour un seul
arrêt plant. C'est correct **ligne par ligne** (« cet UAP a subi 1 arrêt ») et c'est le
comportement retenu, mais la somme des `count` d'une ventilation ne vaut plus le `count`
d'en-tête. Idem pour `mttr`, moyenné par ligne. **À documenter explicitement** dans le
docstring de `_group_by_location` — c'est une propriété du modèle, pas un bug à corriger
plus tard en douce.

## 5. Artefacts

### 5.1 `src/app/routers/kpi/services.py`
- `_locations_for_ticket(issue, hierarchy, kind) -> list[str]` (nouveau) : les ids de
  localisation de type `kind` auxquels `issue` est imputable, selon §2. Remplace le
  `loc_id` unique de `_group_tickets_by_location`.
- `_group_tickets_by_location` : boucle sur ces ids au lieu d'un seul.
- `_row_weight(issue, hierarchy, kind, loc_id) -> int` (nouveau) : le poids §3. Pour un
  ticket **non diffusé** il doit rendre exactement `_ticket_weight(issue, hierarchy)`.
- `_group_by_location` : construit une fonction de poids **par ligne** et la passe à
  `_compute_kpis`. Le cache mémoïsé de `_weight_of_builder` (`:712`) est indexé par id de
  ticket seul — la clé doit devenir `(ticket_id, kind, loc_id)`, sinon le premier poids
  calculé pour un ticket est resservi à toutes les autres lignes.
- `_filter_by_scope` (`:1502`) : un ticket est retenu pour `(scope_kind, scope_id)` si
  `scope_id` figure dans `_locations_for_ticket(ticket, hierarchy, scope_kind)`.

### 5.2 Hors périmètre — ne pas toucher
`_resolve_location`, `_ticket_weight`, `_weight_from_ids`, `_pick_location_kind`,
`_group_by_shift`, `_group_by_type`, `_pareto_by_process`, et les KPI d'en-tête. Aucun
chiffre actuellement affiché ne doit bouger, sauf ceux qui manquaient un ticket de scope
large.

## 6. Scénarios attendus (base pour `test-agent`, à valider par le développeur)

1. Ticket **plant**, ventilation par `uap` → apparaît dans **chaque** ligne UAP.
2. Idem ventilation par `line` → chaque ligne ; par `station` → chaque poste.
3. Pondération §3 : usine 10/6/4, arrêt plant de 30 min → lignes UAP à 300/180/120
   poste-minutes, et leur **somme égale** le `downtime_seconds` d'en-tête.
4. Ticket **uap** (UAP A) → apparaît dans la ligne UAP A (inchangé), **et** dans toutes
   les lignes de A, **et** dans tous les postes de ces lignes ; **jamais** dans UAP B.
5. Ticket **ligne** → sa ligne + tous les postes de cette ligne + son UAP (remontée).
6. Ticket **poste** → strictement inchangé par rapport à aujourd'hui.
7. Document légataire **sans** `down_time_scope` → comportement actuel, aucune diffusion.
8. `down_time_scope` inconnu (`"atelier"`) → idem, aucune diffusion.
9. Ticket plant dans une usine **sans aucun UAP** → aucune ligne, aucun plantage.
10. Poids planchéré à 1 : UAP sans poste → 1, pas 0.
11. `count` : un arrêt plant donne `count == 1` dans **chaque** ligne (§4).
12. `_filter_by_scope` : drill-down sur UAP A **inclut** le ticket plant ; le
    `downtime_seconds` du drill-down UAP A **égale** celui de la ligne UAP A du tableau
    de bord (c'est la cohérence que ce contrat existe pour garantir).
13. Non-régression : un ticket déclaré exactement au niveau ventilé garde son poids
    `_ticket_weight` actuel, et la suite KPI existante reste verte.

## 7. Acceptance (firewall)

- Un arrêt plant apparaît dans toutes les lignes de la ventilation, à sa juste part.
- La somme des `downtime_seconds` d'une ventilation égale le `downtime_seconds`
  d'en-tête (ce qui n'est pas le cas avec un poids plant entier).
- Tableau de bord et drill-down affichent le même chiffre pour la même localisation.
- Aucun chiffre existant ne bouge pour un ticket qui n'est pas de scope large.
- Suite backend verte, sans modification des suites gelées d'autres features.

---

## 8. Addendum (2026-09-02) — la localisation propre prime sur le scope

Décision du développeur après revue de l'implémentation (option 3).

L'implémentation livrée s'écarte de §2 sur un point, **et cet écart est validé** : la
localisation propre du ticket (`_resolve_location`) l'emporte quand elle résout quelque
chose de concret à ce niveau ; la diffusion par `down_time_scope` ne comble qu'un niveau
resté **vide**. Un ticket `plant` **sans aucun id** se diffuse partout (le cas visé) ;
un ticket `plant` **portant un `uap_id`** reste imputé à ce seul UAP.

**Le trou que cela laisse.** `_ticket_weight` continue de traiter le scope comme
autoritaire : un ticket `plant` portant `uap_id=A` pèse *tous* les postes de l'usine, mais
n'apparaît que dans la ligne UAP A — cette ligne affiche donc le poids de l'usine entière
(mesuré : 5 postes de dommage sur un UAP qui en compte 3). C'est exactement l'inflation
que la pondération §3 existe pour éviter.

**La correction retenue : rendre le cas impossible à créer.** `CreateDownTimeIn`
(`src/app/routers/down_time/modelsIn.py`, validateur `_validate_scope_id`) doit **refuser
en 422** un `production_scope = plant` accompagné d'un `uap_id`, `production_line_id` ou
`workstation_id` non vide. Symétrique des règles existantes (qui *exigent* l'id
correspondant pour les scopes uap / ligne / poste) : le scope plant en **interdit** tout.

Rayon d'action vérifié avant décision : le client mobile met déjà les trois ids à `null`
pour le scope plant (`DeclareDownTimeScreen.tsx:67-69`) ; aucun test existant n'envoie
plant + un id réel en attendant un succès. Aucun client cassé.

**Ce que cela ne corrige pas** : les documents **déjà stockés** qui combinent
`down_time_scope = plant` et un id restent lus avec la règle « localisation propre
d'abord ». Le validateur ne protège que les créations futures. Si de tels documents
existent en base, ils gonfleront leur ligne — à vérifier côté données, hors périmètre de
ce contrat.

### Scénarios (à valider par le développeur)
14. `POST /down-times` avec `production_scope: "plant"` + `uap_id` non vide → **422**.
15. Idem avec `production_line_id` non vide → **422**.
16. Idem avec `workstation_id` non vide → **422**.
17. `production_scope: "plant"` avec les trois ids `null`/absents → **201** (inchangé).
18. Les scopes uap / ligne / poste conservent **exactement** leurs règles actuelles
    (id correspondant requis ; un id de contexte d'un autre niveau reste accepté).

---

## 9. Révision 2 (2026-09-02) — suite à la revue croisée

Gate rouvert **une fois** par le développeur. Décisions ci-dessous ; §7 (acceptance) reste
la promesse à tenir, et c'est elle qui arbitre les conflits.

### 9.1 B1 — l'en-tête du drill-down ignore la pondération par ligne (bloquant)

`get_drilldown` construit `weight_of = _weight_of_builder(hierarchy)` (`:1492`) et le passe
à ses KPI d'en-tête (`:1544`). `get_daily` a été corrigé pour cela (`:1756`), pas
`get_drilldown` : un drill-down sur l'UAP A affiche donc le poids de **l'usine entière**
dans son en-tête (36 000 mesuré, contre 18 000 sur la ligne du tableau de bord), et
l'en-tête ne se réconcilie même pas avec son propre bloc `children`.

**Correction.** Quand le chemin fixe une localisation (`last_location_kind` /
`last_location_id` renseignés), le poids de la requête devient
`_location_weight_fn(hierarchy, last_location_kind, last_location_id)` et sert à `kpis`
**et** aux agrégations `pareto_by_process` (`:1623`), `downtime_by_shift` (`:1630`),
`downtime_by_type` (`:1637`) et au repli `_group_by_location` (`:1617`). `_weight_of_builder`
n'est conservé que pour un chemin **sans** étape de localisation.

### 9.2 B2 — postes sans ligne : une ligne « non affectée » explicite (bloquant)

Un poste dont `production_line_id` est `None` est compté dans le poids d'en-tête
(`_ticket_weight` plant = `len(hierarchy["stations"])`) mais n'est atteignable par aucune
ligne de ventilation. Mesuré : 4 postes rattachés + 5 non rattachés → en-tête 9, somme des
lignes 4. **Décision : ajouter une ligne explicite** plutôt que masquer l'écart.

- `id = "unassigned"`, `kind` = celui de la ventilation, `label = ""` — le client localise
  sur l'id sentinelle ; le backend n'invente pas de libellé produit.
- Poids : le nombre de postes non rattachés (postes sans `production_line_id`, et pour la
  ventilation par ligne, les lignes sans `uap_id`).
- Émise **uniquement** si ce nombre est > 0, et **jamais drillable** : un chemin de
  drill-down visant `unassigned` conserve le comportement actuel d'un id de localisation
  inconnu, ce contrat ne l'étend pas.
- Le frontend ne sait pas encore afficher cette ligne — **suivi hors périmètre**, à
  signaler au développeur, pas à masquer.

### 9.3 W4 — les localisations vides ne reçoivent plus la diffusion

Le plancher à 1 (§3) et la réconciliation (§7) ne peuvent pas être vrais ensemble : une
localisation vide ajoutait `durée × 1` que l'en-tête ne compte pas. **Décision : §7 gagne.**

- `_locations_for_ticket` **n'inclut pas** une localisation de `kind`/`loc_id` sans aucun
  poste descendant lorsqu'il s'agit d'une **diffusion**.
- Le plancher à 1 reste entier pour un ticket **déclaré à ce niveau** : un ticket déclaré
  sur un UAP vide produit bien sa ligne, pondérée 1, jamais 0.
- **Le scénario 10 de la §6 est donc remplacé** (voir 9.6) : c'est l'anomalie levée par
  l'implémentation, re-validée ici par le développeur.

### 9.4 W2 — la diffusion doit partir de la localisation *résolue*

`_locations_for_ticket` calcule `own` via `_resolve_location` (avec remontée) mais les
branches de diffusion relisent les ids **bruts** du ticket. Un ticket de scope `uap` ne
portant qu'un `production_line_id` disparaît alors de **toutes** les lignes poste
(mesuré : 10 enfants à 0). Les branches de diffusion doivent utiliser les ids résolus
(`uap_id or issue.get("uap_id")`, idem ligne) déjà dépaquetés en tête de fonction.

### 9.5 W5 — l'invariant §8 doit tenir à l'écriture, pas seulement à l'entrée HTTP

`CreateDownTimeIn` refuse `plant` + sous-localisation, mais `add_down_time`
(`src/app/async_jobs/add_down_time.py`) recopie `production_scope` et les trois ids dans le
document sans revalidation, et les routes worker sont non authentifiées par conception.
La combinaison interdite reste donc créable par le chemin job.

**Correction :** dans `add_down_time`, avant de construire `issue_data`, **forcer à `None`**
les trois ids quand `production_scope == "plant"`, avec un `logger.warning` nommant le
ticket. On neutralise, on ne rejette pas : un arrêt réel ne doit jamais être perdu à cause
d'un payload mal formé.

### 9.6 Scénarios — révision 2

**Remplacé.**
10. *(ancien : un UAP vide reçoit le ticket diffusé, pondéré 1)* → devient : un ticket
    **diffusé** n'atteint **pas** une localisation sans poste descendant (aucune ligne pour
    elle) ; mais un ticket **déclaré sur** cette localisation vide produit bien sa ligne,
    pondérée **1**, jamais 0.

**Ajoutés.**
19. `/kpi/drilldown?path=uap:<A>` : le `downtime_seconds` de l'**en-tête** égale la ligne
    UAP A du tableau de bord **et** la somme de son propre bloc `children` (B1).
20. Idem pour un chemin `station:<X>` — l'en-tête ne porte jamais le poids de l'usine.
21. Hiérarchie contenant un poste sans `production_line_id` : une ligne `id="unassigned"`
    apparaît, et **somme des lignes == en-tête** (B2).
22. Aucun poste non rattaché → **aucune** ligne `unassigned` (pas de ligne à zéro).
23. Ticket de scope `uap` ne portant qu'un `production_line_id` : il atteint bien les
    lignes poste de cet UAP (W2).
24. `add_down_time` recevant un payload `plant` + `uap_id` : le document stocké a ses trois
    ids à `None`, un warning est logué, et le ticket est bien créé (W5).
25. Réconciliation sur jeu mixte : tickets diffusés + non diffusés + carry-over hors
    période → somme des lignes == en-tête (la promesse §7, testée hors du cas propre).
