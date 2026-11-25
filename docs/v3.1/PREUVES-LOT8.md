# Lot 8 — Vigie et gouvernance (preuves, 25/11/2026)

## Livré (rupture 5 de l'audit)
- **Réponse graduée** : chaque constat de `guard drift` et de `guard post` porte une gravité `info`, `avertissement` ou `blocage`.
  - `info` : `PLAN_ABSENT`.
  - `avertissement` : `FICHIER_SANS_EXIGENCE`, `EXIGENCE_SANS_TACHE`, `BUDGET_ALERTE`, `BUDGET_DEPASSE`.
  - `blocage` : tout le reste, notamment périmètre, fichier protégé, scellé, ordre ou plan modifié, test ou critère scellé, preuve fabriquée et `BUDGET_ARRET`.
  - La sortie JSON donne `graded` et `bloquant`. Les codes de sortie 3 (corriger) et 4 (deuxième fois, question) sont inchangés.
  - Chaque constat est journalisé (`vigie.finding`, dédupliqué par occurrence).
- **Budget gradué** sur le budget unique du lot 6 : 80 % donne `BUDGET_ALERTE`, plus de 100 % `BUDGET_DEPASSE`, 150 % `BUDGET_ARRET` (bloquant).
- **Un blocage arrête l'action, il ne se contente pas d'écrire.**
  - Avant chaque dispatch, `manager next` lance `drift` et `post`. Sur un constat bloquant, il ne dispatche rien (code 5).
  - Après chaque exécution, `manager done` lance `drift` et **`post`**, qui n'était jusqu'ici appelé par personne. Sur un constat bloquant, la tâche passe `blocked` au lieu de `done` (code 5).
  - Les événements `vigie.block` et `vigie.unblock` sont journalisés. Le déblocage est automatique dès que le constat est corrigé ou dérogé.
- **Dérogations** : `guard.py derogation --code C [--msg M] --by NOM --reason TEXTE`.
  - Les champs `--by` et `--reason` sont obligatoires. L'événement `vigie.derogation` est journalisé avec l'acteur `user`.
  - Le constat reste affiché, dégradé en `info`, avec sa dérogation.
  - `derogations.json` est un fichier de mission protégé : le pare-feu refuse qu'un outil l'écrive.
- Contrat : la transition `review → blocked` est ajoutée.

## Défaut trouvé (corrigé)
`blocked_by` est un champ d'exécution, mais il entrait dans l'empreinte du plan : la Vigie levait donc `PLAN_MODIFIE` à tort, ce qui bloquait tout après le premier blocage. Trouvé par `test_vigie`, il est corrigé en ajoutant `blocked_by` aux champs de progression.

## Mission réelle
`py -3 dev/mission_lot8.py` : **14/14 PASS**.
- Le **hook réel** refuse trois actions (code 2) : une écriture hors périmètre, `rm -rf ../` et l'écriture de `derogations.json`.
- Une écriture hors périmètre passée par un autre chemin, un script, est **détectée par `post` après l'exécution**. T1 reste bloquée (code 5), et `next` ne dispatche plus rien (code 5).
- Une dérogation explicite est accordée. T1 est débloquée, redispatchée, puis `done`. Le constat reste visible en `info` avec sa dérogation.
- Budget à 84 % : avertissement, sans blocage. Budget à 164 % : `BUDGET_ARRET`, dispatch arrêté.
- Piste d'audit complète : `guard.deny`, `vigie.finding`, `vigie.block`, `vigie.derogation` (acteur `user`), `vigie.unblock`, `budget.stop`.

## A20 — latence du hook : mesure et justification
`py -3 dev/bench_guard.py --n 40`, le 25/11/2026 :

| Mesure | Médiane |
|---|---|
| Interpréteur seul (`python -I -S -c pass`) | 66 ms |
| Hook pare-feu en appel direct, dans une mission (mix) | 76 ms (**+10 ms** de code du pare-feu) |
| Plancher réel : shell + Python (`sh` puis `python -c pass`) | **121 ms** |
| Vraie commande du hook (`sh hooks/run.sh guard.py --guard`), mix de 106 actions | **192 ms** |

Lecture :
- Le code du pare-feu coûte **10 ms**.
- Le plancher shell + Python de cette machine Windows (121 ms) **dépasse à lui seul la cible de 120 ms**. La cible n'est donc pas atteignable par la commande de hook imposée (`sh …`) sur cette machine.
- Le lanceur `run.sh` ajoute environ **71 ms** au-dessus de ce plancher, alors que son chemin en cache n'exécute que des commandes internes et un `exec`. Le coût vient probablement du démarrage de MSYS. **Ce n'est pas prouvé** et il reste à instruire.

Verdict A20 : **FAIL contre la cible de 120 ms**, avec une justification documentée pour la part incompressible (121 ms). Les 71 ms du lanceur sont une piste d'optimisation ouverte.

## Tests
- `test_vigie` : 4 tests, rouge vu avant implémentation, puis le défaut `blocked_by` trouvé et corrigé.
- `test_guard`, `test_orchestration`, `test_economie` et `test_contracts` sont verts : 55 tests.
- `py -3 dev/accept.py` :
  - A1 = 535 tests, 0 échec, 1 sauté.
  - A17 (40 attaques) et A18 (faux positifs) verts.
  - Bilan : vert 19, rouge 1, non mesuré 4.
  - A20 a mesuré dans ce passage **678 ms pour un plancher de l'interpréteur à 214 ms**, contre 66 ms une heure plus tôt. La machine était très chargée pendant la suite.
  - Le chemin chaud n'a gagné qu'un dictionnaire de gravités au chargement du module. La mesure de référence reste celle du tableau ci-dessus, faite sur une machine moins chargée.

## Critères V3.1
- A26 Vigie : **PASS**. Contrôles aux jalons, avant le dispatch, après l'exécution et sur le budget, réellement déclenchés et suivis d'effet.
- A27 Sécurité : **PASS en test**. L'action hors périmètre est bloquée avant l'action (hook) et après (`post`, tâche bloquée). Aucune prétention de sandbox : `RELAIS.md` et le README le disent déjà, et un hook n'est pas un bac à sable.
- A20 : FAIL contre la cible, justifié pour la part incompressible.

## Non vérifié
- Blocage dans une vraie session Claude Code : non rejoué ici, pour ne pas sceller une mission dans le dépôt de la session courante.
- Une dérogation passée par l'outil Bash peut être lancée par l'agent lui-même : le modèle de confiance est le même que celui des avenants (`--by` déclaratif). Il n'existe pas de signature forte.
