# Lot 9 — Barre de progression et ETA (preuves, 25/11/2026)

## Livré (rupture 8 de l'audit)
- **`scripts/progress.py`** : le pôle PROGRESS. `BAR.json` est désormais une **projection** de `PLAN.json` et `events.ndjson`, recalculée par `manager.py next` et `done` ; personne ne la saisit à la main.
  - Avancement : seules les tâches validées comptent. `running`, `review` et `failed` ne font rien bouger. Deux mesures sont données séparément : `percent_tasks` (nombre de tâches) et `percent_work`, pondéré par `estimated_duration`, à défaut `volume_tokens`, à défaut 1.
  - Temps actif : intervalles entre événements successifs, chacun plafonné à 20 min. Au-delà, c'est une pause ; la règle est écrite dans `BAR.json`.
  - ETA : effort restant multiplié par le rapport observé / estimé des tâches terminées (médiane et quartiles). Il est donné en fourchette, avec un niveau de confiance : faible sous 3 tâches observées, moyenne de 3 à 5, bonne à partir de 6. Sans historique, la fourchette va de ×0,5 à ×2 et la confiance est « faible (n = 0) ».
  - Précision : arrondi à 5 min sous l'heure, au quart d'heure au-dessus ; jamais une heure affichée à la minute.
- **Mod de la barre (`hooks/bar/register.tsx`)** : il lit la projection `BAR.json` la plus récente de la mission (`$.fs.list`, `exists`, `read`) et l'affiche telle quelle. La relecture a lieu au démarrage, après chaque commande Bash ou PowerShell et en fin de tour.
  - Sans `BAR.json`, le moteur historique reste un repli (sessions sans mission compilée).
  - Une projection illisible est journalisée (`$.ui.log`) et l'affichage se dégrade, sans échec silencieux.
- **`manager.py`** réécrit `BAR.json` après chaque `next` et chaque `done`. Si l'écriture échoue, il le dit et la boucle continue.
- `dev/show_bar.md` : procédure exacte de capture pour A08.

## Défauts trouvés
1. **Fiches d'agents à l'en-tête YAML illisible** : `sr-archiviste`, `sr-synthese`, `sr-exec-haiku`, `sr-exec-sonnet` et `sr-exec-opus`.
   - Trouvé par `claude plugin validate`, qui échouait.
   - Cause : une `description` non citée contenant « : ». Claude Code chargeait alors ces agents sans leurs champs, donc **sans leur `model`** : l'archiviste ne tournait pas sous Haiku. Ce défaut est antérieur à ce chantier.
   - Correctif : descriptions citées. Test `test_agents_frontmatter` (bibliothèque standard), rouge vu puis vert. Les cinq en-têtes se lisent désormais sous PyYAML, et `claude plugin validate .` réussit.
2. Une première version relisait `BAR.json` à chaque tic de 5 s. Le test existant « attente d'une réponse », qui avance l'horloge d'une heure, dépassait alors son délai. La relecture se fait maintenant seulement après une commande et en fin de tour, là où la projection change réellement.

## Mission réelle
`py -3 dev/mission_lot9.py` : **8/8 PASS**, en cadrage puis par la vraie boucle `manager`.
- T1 en cours : 0 %, ETA 30 min - 2 h 00, confiance faible (n = 0).
- T1 validée : 50 % du travail (30 min sur 60 estimées) et 33 % des tâches. L'ETA est révisé à partir de la durée observée.
- T2 en échec : l'avancement reste à 50 %.
- Après correction de la preuve de T2, la Vigie lève `PLAN_MODIFIE`, débloqué par une dérogation explicite. La mission va jusqu'à 100 %, 3/3, « termine ».
- Aucune heure n'est affichée à la minute.
- Limite : les tâches de la mission s'exécutent en quelques secondes. L'ETA observé tombe donc au plancher d'affichage (« ~ 5 min »), ce qui est fidèle aux données, mais ne constitue pas un étalonnage sur un vrai travail.

## Tests
- `test_progress` : 6 tests, rouge vu avant implémentation.
- `claude plugin test .` : **12/12** dans le moteur, dont le nouveau test « la barre affiche la projection `BAR.json` ».
  - La doublure de `$.fs` fige ses valeurs au démarrage du test : la relecture après un changement de `BAR.json` n'est donc pas testée par une valeur qui change, seulement par le code.
- `claude plugin validate .` : passe. Seul avertissement : l'icône du plugin manque.
- `py -3 dev/accept.py` : A1 = 556 tests, 0 échec, 1 sauté. Bilan : vert 19, rouge 1 (A20 : 435 ms, plancher de l'interpréteur à 159 ms, machine chargée), non mesuré 4 (dont A8).

## Critères V3.1
- A09 ETA : **PASS**. Temps restant révisé à partir des durées observées, en fourchette, avec niveau de confiance.
- A08 Barre : **NOT MEASURED**. Cette session ne peut pas capturer l'app de bureau : un test monté dans le code ne prouve pas que la barre est visible. La procédure pour Baptiste est dans `dev/show_bar.md`, section V3.1.

## Non vérifié
- Rendu réel dans l'app : position, taille, lisibilité, glassmorphism.
- ETA étalonné sur de vraies missions longues.
