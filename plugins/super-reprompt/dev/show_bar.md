# Voir la barre (critère A8, constat par une personne)

Verdict A8 : **`not_run`** tant que le propriétaire n'a pas répondu avec une capture. Jamais « OK » avant.

## Ce que fait la barre
Une ligne au-dessus de la saisie : barre de 3 px, `NN %`, `|  ◷ temps restant`. Gris neutres, 650 px au plus.
Elle n'apparaît que si le dossier de travail contient un dossier `.super-reprompt` (invariant I7) ; sinon le mod ne fait rien.

## Commande exacte (PowerShell, session de l'app de bureau)
```powershell
# 1. depuis la racine du dépôt (branche v3) : noter le chemin du plugin
$plugin = (Resolve-Path ".\plugins\super-reprompt").Path
# 2. dossier d'essai avec un dossier de mission, puis lancement
New-Item -ItemType Directory -Force "$env:TEMP\essai-barre\.super-reprompt" | Out-Null
Set-Location "$env:TEMP\essai-barre"
claude --plugin-dir $plugin
```
Dans la session, écrire : « Appelle l'outil project avec action plan : trois tâches A (4 min), B (10 min), F vérification finale (2 min, final) ; puis démarre A. »
(Variante sans l'outil : demander une liste de 3 étapes ou plus ; la liste native de l'app alimente aussi la barre.)

## Ce qu'il faut regarder
1. La ligne apparaît-elle **au-dessus de la saisie** (oui/non) ?
2. Contient-elle une barre fine, `0 %` (puis un pourcentage qui monte quand A est déclarée terminée), et `◷` suivi d'un temps ?
3. Rien d'autre (ni logo, ni anneau, ni libellé d'étape) ?
4. Dans un dossier **sans** `.super-reprompt` : aucune ligne.
5. En terminal (`claude` hors app) : même contenu en texte (`━━──`).

## Captures à fournir
Une capture de l'app avec la ligne visible (0 %, puis un état intermédiaire), une capture du dossier sans `.super-reprompt`. Les déposer dans la conversation, ou dans `dev/captures/` (ignoré par git si besoin).

## Plan B si la ligne n'apparaît pas (§5.3 du cahier)
Ligne d'état (`$.ui.status`), puis `Pane` ancrée en bas ; fenêtre WPF seulement sur accord écrit.

## V3.1 (lot 9) : capture avec une mission compilee (critere A08)
Depuis le lot 9, quand une mission compilee existe, la barre affiche `.super-reprompt/<mission>/BAR.json`, projection de
`PLAN.json` et `events.ndjson` reecrite par `manager.py next` / `done`. La session qui a construit ce lot ne peut pas
capturer l'app de bureau elle-meme : la capture est a faire par toi, en 5 minutes :

```powershell
$plugin = (Resolve-Path ".\plugins\super-reprompt").Path
py -3 "$plugin\dev\mission_lot9.py"    # verifie d'abord le calcul (8/8 attendu)
New-Item -ItemType Directory -Force "$env:TEMP\essai-barre" | Out-Null
Set-Location "$env:TEMP\essai-barre"; git init -q
claude --plugin-dir $plugin
```
Dans la session : « cadre une mission de 3 taches avec durees estimees, `mission.py ready`, puis `manager.py next` ».
Capturer : (1) la ligne au-dessus de la saisie juste apres `next` (0 %, fourchette de temps) ; (2) apres `manager.py done`
de la premiere tache (le pourcentage du travail monte) ; (3) le meme dossier sans `.super-reprompt` (aucune ligne).
Deposer les captures dans `dev/captures/` ou dans la conversation : A08 reste NOT MEASURED tant qu'elles n'existent pas.
