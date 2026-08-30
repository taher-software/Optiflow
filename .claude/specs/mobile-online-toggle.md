# BOM — Mobile "je suis hors ligne" (toggle du champ `online`)

Statut : contrat figé par l'orchestrateur (Lane FACTORY, branche
`feature/mobile-online-toggle`). Décisions produit validées par le développeur le
2026-08-30. Source de vérité pour `test-agent`, puis `api-agent`, la station mobile,
`doc-agent` et `review-agent`.

## 1. Contexte — le champ existe déjà, en lecture seule

`online` est **déjà consommé** par toutes les notifications push :
- `async_jobs/add_down_time.py:225` — `_notify_process_agents`
- `async_jobs/notify_down_time_update.py:140`
- `async_jobs/escalate_down_time.py:135`

Règle établie : **`online` absent vaut `True`** (les utilisateurs créés avant
l'existence du champ sont joignables par défaut). Rien, aujourd'hui, n'écrit ce champ :
il n'existe aucun moyen pour un utilisateur de se déclarer hors ligne. C'est ce que ce
changement ajoute.

**Portée réelle du hors-ligne — à ne pas sur-promettre dans l'UI.** Certaines alertes
ignorent délibérément `online` et continueront donc d'être envoyées à un utilisateur
hors ligne : l'escalade vers les superviseurs (`add_down_time.py:251-253`,
`escalate_down_time.py:172`). Le hors-ligne fait taire les notifications *d'équipe*,
pas les escalades.

## 2. Décisions (tranchées par le développeur)

| Question | Décision |
|---|---|
| Forme de l'endpoint | `PATCH /users/me/online`, **valeur explicite** dans le corps (idempotent) |
| Lecture de l'état courant | `online` **ajouté à `AuthUserOut`** — renvoyé par les logins, pas de `GET /users/me` |
| Autorisation | **tout utilisateur authentifié**, aucun contrôle de rôle |

`PATCH /users/me/online` est idempotent par choix : un double-tap ou un renvoi après
timeout ne peut pas laisser l'utilisateur dans l'état inverse de celui qu'il a choisi.

## 3. Artefacts — backend

### 3.1 `src/app/routers/auth/modelsOut.py`
- `AuthUserOut` : ajouter `online: bool = Field(default=True, ...)`.
  Le défaut `True` reproduit **exactement** la règle des filtres de notification
  (`u.get("online", True)`) : un document utilisateur sans le champ est en ligne.

### 3.2 `src/app/routers/auth/services.py`
- Les trois chemins de login (`login`, `mobile_login`, `check_user_code`) renseignent
  `online` depuis le document Firestore, avec le même défaut `True`.

### 3.3 `src/app/routers/user/modelsIn.py`
- `SetOnlineIn` : `online: bool = Field(..., description=...)`. Champ **requis** —
  pas de valeur par défaut, sinon un corps vide changerait silencieusement l'état.

### 3.4 `src/app/routers/user/modelsOut.py`
- `UserOut` : ajouter `online: bool` (défaut `True`), et le renseigner dans `_to_out`
  (`services.py:17`) — les écrans d'administration voient ainsi l'état réel.

### 3.5 `src/app/routers/user/services.py`
- `set_own_online(user: dict, online: bool) -> UserOut` : écrit `{"online": <bool>}` sur
  le document de **l'utilisateur courant** (`user["id"]`), dans son namespace, puis
  renvoie le `UserOut` à jour. Aucune autre clé du document n'est touchée.

### 3.6 `src/app/routers/user/__init__.py`
- `PATCH /users/me/online`, `response_model=ApiResponse[UserOut]`, `status_code=200`,
  dépendance `get_current_user` (**pas** `_admin_or_owner`).
- **La route doit être déclarée AVANT `/{user_id}`**, sinon `me` est capturé comme un
  `user_id` par la route existante. C'est le piège classique de ce routeur ; le test
  doit le verrouiller.
- L'identité vient **exclusivement** du token (`current["id"]`) : aucun `user_id` n'est
  accepté dans le chemin ou le corps, donc un utilisateur ne peut jamais modifier
  quelqu'un d'autre, ni franchir la frontière de tenant.

## 4. Artefacts — mobile (station sans tests automatisés, voir §6)

### 4.1 `src/constants/types.ts`
- `AuthUser` : ajouter `online: boolean` (miroir de `AuthUserOut`).

### 4.2 `src/stores/useAuthStore.ts`
- Ajouter `setOnline(online: boolean): Promise<ApiResult<...>>` appelant
  `apiRequest("/users/me/online", "PATCH", { online })`.
- **Mise à jour optimiste + rollback** : basculer immédiatement `user.online` dans le
  store, et **restaurer la valeur précédente si l'appel échoue** — sur un téléphone
  d'atelier, la perte de réseau est le cas normal, et un interrupteur qui ment sur la
  joignabilité est pire que pas d'interrupteur du tout. Signaler l'échec via
  `useToastStore`.
- `apiRequest` doit accepter `"PATCH"` (son union de méthodes ne le contient pas
  aujourd'hui : `"GET" | "POST" | "PUT" | "DELETE"`).

### 4.3 `src/screens/HomeScreen.tsx`
- Un interrupteur (`Switch` React Native) dans l'en-tête, sous la ligne de bienvenue,
  étiqueté par i18n, reflétant `user.online`.
- Un libellé d'état explicite (« En ligne » / « Hors ligne »), pas seulement la couleur
  de l'interrupteur — l'atelier se consulte d'un coup d'œil et en gants.
- Sous-titre honnête quand l'utilisateur est hors ligne : les escalades superviseur
  continuent d'arriver (§1). Ne pas écrire « vous ne recevrez plus de notifications ».
- Désactivé pendant l'appel réseau pour éviter le double-tap.

### 4.4 `src/i18n/locales/{en,fr}.ts`
- Clés pour l'étiquette, les deux états, la note d'escalade et le message d'échec.
  **Les deux langues** — jamais une clé ajoutée dans une seule locale.

## 5. Scénarios attendus (base pour `test-agent`, à valider par le développeur)

1. `PATCH /users/me/online {online: false}` → 200, document Firestore de l'appelant mis
   à `online: false`, `UserOut` renvoyé avec `online: false`.
2. `{online: true}` → 200, document remis à `online: true`.
3. **Idempotence** — deux `{online: false}` consécutifs → toujours `false`, pas d'erreur.
4. Sans bearer token → 401.
5. Un rôle non-admin (agent de production) **réussit** — c'est du self-service, aucun
   contrôle de rôle (régression à verrouiller : la route ne doit pas hériter de
   `_admin_or_owner`).
6. Corps vide / `online` absent → 422 (le champ est requis).
7. `online` non booléen (`"yes"`, `1`) → 422.
8. **Routage** : `PATCH /users/me/online` ne doit pas être capturé par `/{user_id}` —
   aucun utilisateur d'id `me` n'est cherché ni modifié.
9. **Isolation** : l'appel ne modifie que le document de l'appelant ; le document d'un
   autre utilisateur du même namespace est inchangé.
10. Le document ne perd aucune autre clé (`security_code`, `role`, `push_token`… intacts).
11. `AuthUserOut.online` : un login d'un utilisateur avec `online: false` renvoie
    `online: false` ; un utilisateur **sans le champ** renvoie `online: true`.
12. Non-régression : les filtres de notification existants continuent d'exclure les
    utilisateurs `online: false` et d'inclure ceux sans le champ.

## 6. Ce que ce changement ne couvre PAS

- **Le mobile n'a pas de station de tests automatisés.** Les artefacts §4 sont livrés
  **non testés automatiquement** et vérifiés à la main. Ne pas laisser entendre le
  contraire.
- Pas de présence automatique (aucun passage hors ligne sur inactivité, déconnexion ou
  fin de poste) : l'état est **uniquement** ce que l'utilisateur a choisi, et persiste
  jusqu'à ce qu'il le change.
- Pas de vue administrateur listant qui est hors ligne (le champ apparaît toutefois
  désormais dans `UserOut`).

## 7. Acceptance (firewall)

- Un utilisateur mobile peut se déclarer hors ligne puis en ligne depuis l'écran
  d'accueil, et l'état survit à la fermeture de l'application (relu au login).
- Un utilisateur hors ligne cesse d'apparaître dans `_notify_process_agents` et
  équivalents ; les escalades superviseur lui parviennent toujours.
- Aucun utilisateur ne peut modifier le `online` d'un autre, ni d'un autre tenant.
- Suite backend verte, sans modification des tests gelés d'autres features.
