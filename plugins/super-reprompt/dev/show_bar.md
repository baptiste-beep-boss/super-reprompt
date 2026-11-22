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
