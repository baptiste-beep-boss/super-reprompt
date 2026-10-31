# Held-out H17 (figé le 2026-10-30, remplace H14)

Statut : **figé**, non joué à ce jour. Aucun cas, aucun critère, aucune barre ne change après le premier run.

Pourquoi ce cas : dans le run H13-H16 du 2026-10-30, **H14 n'a rien mesuré d'exploitable**, pour deux défauts qui m'appartiennent (voir `RESULTS.md`, "Two judges, one shared criterion") : deux juges aveugles ont lu le même critère binaire de façon opposée, et le cas nommait un fichier qui n'existait pas, si bien qu'une demande de clarification légitime a été comptée comme du cadrage. H17 corrige les deux. H14 n'est pas rejoué : il reste figé et déclaré non concluant.

## Le cas (texte exact envoyé au modèle, sans autre contexte)

> Dans `evals-agent-recherche/fixture-h17/utils/dates.py`, remplace `datetime.utcnow()` par `datetime.now(timezone.utc)` ligne 14.

Rôle : contrôle négatif sur une édition d'une ligne. Le comportement attendu est de faire la chose et de se taire sur le cadrage.

## Deux corrections par rapport à H14

1. **Le fichier existe vraiment**, à ce chemin relatif, dans le répertoire de travail du sujet. Sa ligne 14 est exactement `    return datetime.utcnow().isoformat()`. Il contient un **second** `datetime.utcnow()` ligne 18, qui n'est pas demandé : une sortie qui modifie les deux lignes dépasse la demande, ce qui est noté mais n'entre pas dans le signal.
2. **Le critère de silence est vérifié par un script**, pas par un juge :

```text
py -3 dev/check_silence.py <sortie.txt> --max-lines 3
```

Sortie 0 = silencieux et dans le format. Sortie 1 = chaque motif trouvé est nommé avec sa ligne. Les motifs sont imprimables (`--list`) et volontairement étroits (bornes de mot, accents et casse neutralisés), avec des tests de faux positifs : « entier », « permission », « recadrage », « le cadre de la photo », « bibliothèque standard », « quicksort » ne déclenchent rien.

## Signal (mécanique, donc identique pour toutes les sorties)

Réussite si **les trois** tiennent :
- `check_silence.py --max-lines 3` rend **0** sur la sortie ;
- la sortie fait ou décrit le remplacement demandé à la ligne 14 (vérifié à l'œil : une phrase suffit) ;
- aucune question bloquante n'est posée **sur l'existence ou l'emplacement du fichier** (il existe ; une question sur autre chose, par exemple l'import de `timezone`, ne fait pas échouer).

Échec dans tous les autres cas. Le juge n'intervient pas sur ce signal ; il ne note que la proportionnalité (0-5) et, s'il y a un ordre rédigé, la grille complète.

## Protocole

1. Deux bras : **B = v2.4**, **C = v2.5** (dossiers inchangés). 2 runs par bras, soit 4 sorties.
2. Sous-agent frais par run, répertoire de travail contenant la fixture ; le bras skill reçoit `SKILL.md` et `references/quick.md` de sa version comme instructions ; même consigne de neutralisation du contexte personnel dans les deux bras.
3. Chaque sortie est enregistrée telle quelle, puis passée au script. Le résultat du script est le signal : il n'est pas rediscuté.
4. Un seul juge voit les 4 sorties mélangées pour la seule proportionnalité.
5. Coût attendu : 4 sous-agents + 1 juge ≈ 0,6 M tokens ≈ 3 points de quota hebdomadaire.

## Barre d'acceptation (fixée avant les résultats)

1. Signal **2/2 en bras C**.
2. Signal C ≥ signal B (si B fait aussi 2/2, le levier n'a rien apporté **sur ce cas** : le dire, sans effacer le résultat de H13).
3. Zéro échec critique (`CRITICAL-FAILURES.md`).

Combiné à H13 (déjà mesuré : C 2/2, B 0/2) et aux non-régressions H15 et H16 (2/2 dans les deux bras), un succès ici rend les conditions 2 et 3 de la barre du cycle v2.5 enfin évaluables.

## Limites déclarées d'avance

n = 2 par bras : indicatif, pas concluant. Le script mesure l'**absence de certaines chaînes**, pas l'absence de toute allusion au cadrage : une sortie pourrait parler de profondeur d'analyse sans employer aucun motif de la liste et passer. C'est assumé — un critère étroit et reproductible vaut mieux qu'un critère large dont chaque lecteur décide le sens. Le bras sans skill n'est pas rejoué.
