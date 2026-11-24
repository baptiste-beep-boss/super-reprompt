# Resultats A24 : banc REDUIT, lance le 24/11/2026

**Reduction declaree** : n = 1, deux projets (moyen, difficile), trois bras sur quatre. Le bras « v3 complete » n'est pas
mesurable : aucun fournisseur gratuit n'est connecte. Ces chiffres n'ont **aucune valeur statistique** ; ils donnent un
premier signal. Protocole : `PROTOCOLE.md`. Empreintes verifiees avant les essais (`dev/a24_manifest.py --check`).
Execution : `dev/a24_run.py`, `claude -p` Sonnet medium, dossier de configuration isole (aucun hook, plugin ni CLAUDE.md
personnel), dossier vierge par essai, meme invite. Juge : Opus, a l'aveugle (livrables renommes A/B/C, carte tiree au sort,
levee apres notation).

| Bras | Projet | Tests caches | Note juge /20 | Tokens Claude (total) | Tokens de sortie | Tours | Duree |
|---|---|---|---|---|---|---|---|
| Claude nu | moyen | 3/3 | 17 | 278 531 | 3 266 | 8 | 57 s |
| v2.5 | moyen | 3/3 | 16 | 332 030 | 3 725 | 9 | 60 s |
| v3 sans Relais | moyen | 3/3 | 17 | 516 570 | 5 446 | 9 | 87 s |
| Claude nu | difficile | 4/4 | 18 | 659 907 | 5 638 | 11 | 97 s |
| v2.5 | difficile | 4/4 | 19 | 663 223 | 5 244 | 13 | 92 s |
| v3 sans Relais | difficile | 4/4 | 17 | 733 155 | 4 961 | 12 | 93 s |
| v3 complete | — | non mesure | — | — | — | — | — |

Totaux juge : Claude nu 35, v2.5 35, v3 sans Relais 34 (ecarts de 1 point par projet : dans le bruit selon le juge).
Tokens : v3 sans Relais +85 % (moyen) et +11 % (difficile) par rapport a Claude nu.
Cout fixe du plugin v3 mesure a part (invite triviale) : 69 467 contre 68 543 tokens de contexte initial, soit **+1,3 %** ;
l'ecart du projet moyen vient donc surtout du comportement de la session (plus de sortie, contexte relu a chaque tour).

Defauts trouves par le juge (extraits) : moyen v3 et nu : CSV avec BOM -> KeyError ; difficile v3 : message de cycle
incomplet et algorithme quadratique (9,6 s sur 5 000 taches contre 0,03 s pour v2.5).

## Lecture
- Sur des taches de code courtes et bien specifiees, **aucun bras ne se distingue** : tests caches 100 % partout.
- **v3 n'apporte pas de gain mesurable sur ce type de tache** et coute plus de tokens. Explication probable : sur une invite
  courte, les hooks de cadrage de v3 restent silencieux (par conception) ; v3 se comporte alors comme Claude nu + 1,3 %.
- Ce banc ne mesure **pas** ce que v3 apporte par ailleurs : pare-feux (essai reel : `git push --force` bloque, F09),
  memoire de projet, delegation au Relais, missions longues multi-lots.

## Porte d'adoption
« v3 complete non inferieure a v3 sans Relais, tokens en baisse » : **non evaluee** (aucun fournisseur connecte).
Constat ecrit, conformement au CDC : sur ce banc, v3 n'est pas superieur a Claude nu.
