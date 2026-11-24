# L9 — propositions d'allègement de la machine (rien n'est exécuté)

> Statut : **PROPOSITIONS, aucune appliquée.** Chaque ligne attend un « oui » écrit, une par une. Cette session n'a fait que **lire** `~/.claude`
> (réglages, transcriptions, caches) : aucun réglage modifié, aucun plugin désactivé, aucun skill archivé.
> Mesures du 24/11/2026 sur la machine de l'auteur ; ce document est propre à une machine : **à retirer ou généraliser avant publication (L10).**
> Unité : tokens = caractères / 3,7 (convention du dépôt). « Au repos » = ce qu'une session neuve charge avant le premier mot (nom + description).
> Sauvegarde avant toute application : `Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.bak-l9-<ligne>` ; retour arrière = recopier la sauvegarde.

## Tableau (une ligne par proposition)

| # | Proposition | Constat mesuré | Gain estimé au repos | Risque | Recommandation |
|---|---|---|---|---|---|
| P1 | Désactiver `ecc@ecc` | 314 skills + 71 agents + 98 commandes = **36 313 tokens** ; 2 appels de skill et 2 d'agent ECC dans 813 transcriptions ; catalogue embarqué `audit : OK`, écart 0 | **≈ 36 000 tokens** | moyen : plus d'appel par nom `ecc:*` ; on passe par le catalogue (`Read` du fichier embarqué) | **oui**, après installation du plugin v3 |
| P2 | Désactiver les plugins jamais utilisés (`private-equity`, `obsidian`, `equity-research`) | 0 / 0 / 1 appel dans 813 transcriptions ; 1 214 + 443 + 994 tokens | 1 657 à 2 651 tokens | faible | oui pour les deux premiers ; equity-research au choix (1 appel) |
| P3 | Retirer les 4 entrées SessionStart `cbm-session-reminder` | 4 matchers (startup, resume, clear, compact) lancent un exécutable de 296 Mo ; 2,8 à 9,7 s par lancement ; sortie utile : 0 token ; le serveur MCP visé échoue en permanence | 0 token ; **≈ 3 à 10 s de démarrage** par événement | faible (le rappel renvoie vers un outil indisponible) | oui |
| P4 | Modèle par défaut `haiku` | `settings.json` : `"model": "haiku"` ; le défaut s'applique aussi aux sous-agents | **négatif en quota** si on le change | qualité contre quota | **ne rien changer** sauf défaut de qualité constaté |
| P5 | MCP en échec permanent (7 serveurs) | 0 appel d'outil dans 813 transcriptions pour chacun ; échecs de connexion à chaque session (délai de 120 s vu) | délai de démarrage ; jusqu'à 13 800 tokens d'outils MCP si connectés | faible pour 2 (config utilisateur) ; 4 gérés par l'application | oui pour `codebase-memory-mcp` et `vibe-trading` ; les 5 autres : interface seulement |
| P6 | Archiver le skill v1 et ses 2 hooks | v1 masque le plugin (même nom) ; 378 Ko ; 2 hooks : `reinject-*` (SessionStart compact), `detect-reprompt-*` (UserPromptSubmit) | ≈ 150 tokens au repos + 2 lancements de script | **moyen** : sans v1 il faut le plugin v3 installé | oui, **après** installation et essai du plugin |
| P7 | *(hors liste)* Doctrines réinjectées à chaque invite | `doctrines.md` = 1 928 octets ≈ **521 tokens par invite** | 521 tokens × nombre d'invites | **élevé** (rappels de comportement) | ne pas toucher sans décision explicite |
| P8 | *(hors liste, information)* Plugins synchronisés du compte | `get_usage` : skills 19 060 + agents 15 396 + outils MCP 13 817 tokens avant le premier mot | jusqu'à ≈ 48 000 tokens | décision de compte | désactivation dans l'application, pas en ligne de commande |

Gain cumulé réaliste (P1 + P2 + P3) : **≈ 38 000 à 39 000 tokens au repos** sur les ≈ 60 000 mesurés par le cahier des charges le 22/11/2026.

---

## P1 — désactiver `ecc@ecc`
- **Constat (commande → sortie)** :
  - réglage : `py -3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/settings.json'),encoding='utf-8'))['enabledPlugins'])"` → `ecc@ecc: True` (avec 5 autres plugins) ;
  - poids au repos, racine du plugin en cache `~/.claude/plugins/cache/ecc/ecc/2.2.3` (nom + description, `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`) → `skills 314 → 28 001 tokens · agents 71 → 4 380 · commandes 98 → 3 932` (total **36 313**) ;
  - usage : balayage des 813 transcriptions de `~/.claude/projects` (motifs `"skill":"…"` et `"subagent_type":"…"`) → `ecc: skills=2 agents=2` ;
  - catalogue prouvé : `py -3 scripts/catalog.py audit` (dans `plugins/super-reprompt`) → `éléments 762 · fichiers LOCK 1136 couverts · écart 0 · non classés 0 … audit : OK`.
- **Gain** : ≈ 36 000 tokens par session neuve. **Risque** : moyen ; ce qui sert encore passe par le catalogue (`catalog.py search`, puis `Read` du fichier sous `vendor/ecc/`). **Condition** : plugin v3 installé et essayé d'abord.
- **Appliquer** :
  ```powershell
  Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.bak-l9-p1
  py -3 -c "import json,os;p=os.path.expanduser('~/.claude/settings.json');d=json.load(open(p,encoding='utf-8'));d['enabledPlugins']['ecc@ecc']=False;json.dump(d,open(p,'w',encoding='utf-8'),indent=2,ensure_ascii=False)"
  ```
- **Retour arrière** : `Copy-Item $HOME\.claude\settings.json.bak-l9-p1 $HOME\.claude\settings.json -Force` (ou remettre `True` avec la même commande).

## P2 — plugins jamais utilisés
- **Constat** : même balayage → `private-equity: skills=0` · `obsidian: skills=0` · `equity-research: skills=1` ; poids au repos mesurés dans `~/.claude/plugins/cache` → `private-equity 10 skills 1 214 tokens · obsidian 5 skills 443 · equity-research 9 skills 994`. (`superpowers` : 12 appels, `agent-skills` : 3 skills et 6 agents → à garder.)
- **Gain** : 1 657 tokens (deux premiers) à 2 651 (les trois). **Risque** : faible.
- **Appliquer** :
  ```powershell
  Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.bak-l9-p2
  py -3 -c "import json,os;p=os.path.expanduser('~/.claude/settings.json');d=json.load(open(p,encoding='utf-8'));[d['enabledPlugins'].__setitem__(k,False) for k in ('private-equity@claude-for-financial-services','obsidian@obsidian-skills')];json.dump(d,open(p,'w',encoding='utf-8'),indent=2,ensure_ascii=False)"
  ```
- **Retour arrière** : recopier `settings.json.bak-l9-p2`.

## P3 — hook répété (4 entrées SessionStart)
- **Constat** : `settings.json → hooks.SessionStart` contient 4 entrées `cbm-session-reminder.cmd` (matchers `startup`, `resume`, `clear`, `compact`) ; ce ne sont **pas** quatre exécutions par session mais une par événement, plus un second hook sur `compact` (`reinject-*`, voir P6). Sortie du script : `cmd.exe … cbm-session-reminder.cmd | wc -c` → 112 octets, soit la bannière de `cmd`, **aucun texte utile**. Durée, 6 lancements mesurés sous charge (suite de tests en cours) : de 2 774 à 9 752 ms. Le serveur MCP visé (`codebase-memory-mcp`) échoue en permanence (P5).
- **Gain** : 0 token ; 3 à 10 s de démarrage par événement concerné. **Risque** : faible.
- **Appliquer** :
  ```powershell
  Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.bak-l9-p3
  py -3 -c "import json,os;p=os.path.expanduser('~/.claude/settings.json');d=json.load(open(p,encoding='utf-8'));ss=d['hooks']['SessionStart'];[g.__setitem__('hooks',[h for h in g['hooks'] if 'cbm-session-reminder' not in h.get('command','')]) for g in ss];d['hooks']['SessionStart']=[g for g in ss if g['hooks']];json.dump(d,open(p,'w',encoding='utf-8'),indent=2,ensure_ascii=False)"
  ```
- **Retour arrière** : recopier `settings.json.bak-l9-p3`. *(Les autres entrées `cbm-*` — PreToolUse `Grep|Glob`, PostToolUse `Read`, SubagentStart — relèvent du même serveur ; à décider avec P5, non incluses ici.)*

## P4 — modèle par défaut `haiku`
- **Constat** : `py -3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/settings.json'),encoding='utf-8'))['model'])"` → `haiku`. Le cahier des charges rappelle un sous-agent trivial à 107 503 tokens ; `econ.py` impose déjà un **modèle explicite** à tout spécialiste parce que ce défaut est Haiku.
- **Gain** : aucun en quota (changer coûte **plus**) ; ne se justifie que par la qualité. **Risque** : qualité contre quota. **Recommandation : ne rien changer.**
- **Si malgré tout** : `Copy-Item … settings.json.bak-l9-p4` puis `py -3 -c "…d['model']='sonnet'…"` ; retour : recopier la sauvegarde.

## P5 — serveurs MCP en échec permanent
- **Constat** : échecs de connexion listés au démarrage de cette session : `codebase-memory-mcp` (CONNECTION_CLOSED), `vibe-trading` (CONNECT_TIMEOUT 120 s), `openbb` (CONNECT_TIMEOUT), `desktop-commander`, `prisma`, `cockroachdb-toolbox` (CONNECTION_CLOSED), `gitkraken` (CONNECT_TIMEOUT). Usage : balayage des 813 transcriptions (outils `mcp__<serveur>__…`) → **0 appel** pour les sept. Origine : `~/.claude.json → mcpServers` contient `codebase-memory-mcp` et `vibe-trading` (config utilisateur) ; `desktop-commander`, `gitkraken`, `prisma`, `cockroachdb` viennent de plugins **synchronisés du compte** (`~/.claude/plugins/synced/…/.mcp.json`) ; `openbb` : origine non retrouvée en lecture seule.
- **Gain** : délai de démarrage et bruit d'erreurs ; outils MCP chargés quand ils se connectent (13 817 tokens mesurés pour l'ensemble de la session). **Risque** : faible (aucun appel enregistré).
- **Appliquer (les deux serveurs de config utilisateur)** :
  ```powershell
  Copy-Item $HOME\.claude.json $HOME\.claude.json.bak-l9-p5
  claude mcp get codebase-memory-mcp
  claude mcp remove codebase-memory-mcp --scope user
  claude mcp remove vibe-trading --scope user
  ```
- **Retour arrière** : `Copy-Item $HOME\.claude.json.bak-l9-p5 $HOME\.claude.json -Force`. Les quatre serveurs de plugins synchronisés se désactivent **dans l'application** (Paramètres → Connecteurs / Plugins) : aucune commande fiable, donc aucune proposée.

## P6 — archiver le skill v1 et ses hooks
- **Constat** : `~/.claude/skills/super-reprompt` = 378 Ko, `SKILL.md` 12 241 octets, `base/routage.md` 5 742 ; même nom que le plugin : **le v1 masque le plugin**. Deux hooks dans `settings.json` : `SessionStart/compact → hooks/reinject-super-reprompt.sh` (2 655 octets), `UserPromptSubmit → hooks/detect-reprompt-threshold.sh` (6 899 octets, sortie 0 octet sur une invite triviale). La migration (L9, partie A) a **copié** routage, journal de budgets et bibliothèque vers `~/.claude/super-reprompt/` (profil privé) ; le v1 est resté intact (empreinte du routage identique avant et après).
- **Gain** : ≈ 150 tokens au repos (description du v1) et 2 lancements de script ; surtout, **libère le nom** pour le plugin. **Risque** : moyen — sans plugin v3 installé on perd le cadrage. **Condition** : plugin installé, essayé, accord explicite.
- **Appliquer** (archive, jamais de suppression) :
  ```powershell
  Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.bak-l9-p6
  Move-Item $HOME\.claude\skills\super-reprompt $HOME\.claude\skills-archive\super-reprompt-v1-20261124 
  @'
  import json,os
  p=os.path.expanduser('~/.claude/settings.json');d=json.load(open(p,encoding='utf-8'))
  for ev in ('SessionStart','UserPromptSubmit'):
      for g in d['hooks'][ev]:
          g['hooks']=[h for h in g['hooks'] if 'super-reprompt' not in h.get('command','') and 'detect-reprompt-threshold' not in h.get('command','')]
      d['hooks'][ev]=[g for g in d['hooks'][ev] if g['hooks']]
  json.dump(d,open(p,'w',encoding='utf-8'),indent=2,ensure_ascii=False)
  '@ | py -3 -
  ```
  *(dans PowerShell, la fermeture `'@` doit être en colonne 0 : retirer l'indentation à la copie.)*
  *(créer d'abord `skills-archive` s'il n'existe pas : `New-Item -ItemType Directory $HOME\.claude\skills-archive -Force`.)*
- **Retour arrière** : `Move-Item $HOME\.claude\skills-archive\super-reprompt-v1-20261124 $HOME\.claude\skills\super-reprompt` puis recopier `settings.json.bak-l9-p6`.

## P7 — doctrines réinjectées à chaque invite *(hors liste)*
- **Constat** : `settings.json → hooks.UserPromptSubmit` : `cat doctrines.md` à **chaque** invite ; `wc -c ~/.claude/doctrines.md` → 1 928 octets, soit ≈ 521 tokens par invite. Hors invite triviale, `detect-reprompt-threshold.sh` ajoute sa propre ligne.
- **Gain** : 521 tokens × nombre d'invites de la session. **Risque : élevé** — ce sont les rappels de comportement ; les ramener à un seul affichage par session change le comportement. **Aucune commande proposée** : décision de fond à prendre d'abord (injecter une fois au démarrage, ou raccourcir).

## P8 — plugins synchronisés du compte *(hors liste, information)*
- **Constat** : `get_usage` au démarrage de cette session : `Skills 19 060 · Custom agents 15 396 · MCP tools 13 817 · System tools 14 911` tokens, avant le premier mot. Ces listes contiennent des dizaines de plugins qui ne sont **pas** dans `enabledPlugins` : ils viennent du compte.
- **Action** : Paramètres → Plugins / Connecteurs de l'application ; non scriptable ici. Gain potentiel jusqu'à ≈ 48 000 tokens, à arbitrer plugin par plugin.

---
**Vérification à blanc des commandes P1, P2, P3, P6** : exécutées sur une **copie** de `settings.json` placée dans un dossier temporaire (`USERPROFILE` redirigé) ; résultat : `ecc@ecc`, `private-equity`, `obsidian` à `False`, les 4 entrées `cbm-session-reminder` et les 2 hooks du v1 retirés, les autres hooks intacts ; le vrai `settings.json` relu ensuite : `ecc@ecc` toujours `True`, 6 entrées SessionStart inchangées.

Méthode de mesure, reproductible : (1) poids au repos = `(len(name)+len(description)+4)/3,7` sur les en-têtes ; (2) usage = comptage des motifs `"skill":"…"`, `"subagent_type":"…"`, `"name":"mcp__…"` dans les `*.jsonl` de `~/.claude/projects` (un mot cité dans une conversation compte aussi : un **zéro** est donc robuste, un petit nombre est un majorant) ; (3) durées = `Measure-Command`, sous charge. Limite : aucune de ces mesures n'est le `/context` de l'application, qui reste la référence pour A4.
