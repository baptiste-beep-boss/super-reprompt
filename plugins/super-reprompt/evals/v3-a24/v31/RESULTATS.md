# Banc V3.1 (lot 10) — résultats : 27 essais, 3 répétitions (25/11/2026)

**Statut : banc complet.** 3 tâches × 3 bras × 3 répétitions = 27 sessions, 0 essai en erreur.

## Protocole (figé avant les essais)
- **Tâches** (empreintes `MANIFEST.json`, vérifiées avant chaque essai) : `facile` (duree), `moyen` (dedup), `difficile` (planif).
- **Bras** :
  - `nu` : Claude Code sans plugin ;
  - `v25` : plugin super-reprompt 2.5.0 ;
  - `v31` : plugin V3.1 de cette branche, sans fournisseur de Relais.
- **Conditions communes** : sessions `claude -p` isolées (`dev/a24_run.py` : configuration dédiée sans hook ni CLAUDE.md personnel, dossier vierge), même invite (« Réalise le projet décrit dans ENONCE.md. »), Sonnet 5.5, effort medium. Les répétitions 1 et 2 ont été lancées le 25/11 vers 16 h UTC, la répétition 3 vers 19 h UTC, après la remise à zéro de la fenêtre de 5 h du quota.
- **Juge objectif et aveugle**, sans modèle :
  - tests cachés, plus la batterie étendue figée (`batterie-etendue/`, empreintes vérifiées : 10 tests Spec et 2 tests Robustesse par tâche, sauf `facile`), exécutés sur une copie du livrable ;
  - **re-jugés après le banc**, sur machine calme, 3 passes, verdict à la majorité. Les tests de robustesse sont des tests de temps, sensibles à la charge (`dev/a24_v31_rejuge.py`). Un seul livrable reste instable d'une passe à l'autre : `nu`, `difficile`, essai 2, sur ses deux tests de robustesse.
  - Il n'y a **pas de juge LLM**, pour préserver le quota : la qualité de rédaction n'est pas notée.
- **Tokens** : usage réel de la sortie JSON de `claude -p` (entrée, cache créé, cache lu et sortie). Le cache lu domine : environ 0,5 M tokens par session, quel que soit le bras.

## Résultats
Données brutes : `journal.jsonl`, une ligne par essai, verdict pendant le banc et `juge_final`.

```
py -3 dev/a24_v31_rapport.py evals/v3-a24/v31/journal.jsonl
```

| Tâche | Bras | Essais | Tests cachés | Étendue spec | Étendue robustesse | Tokens médian (min-max) | Durée médiane | Erreurs |
|---|---|---|---|---|---|---|---|---|
| facile | nu | 3 | 6/6 | - | - | 542 k (476-567 k) | 155 s | 0 |
| facile | v25 | 3 | 6/6 | - | - | 573 k (415-577 k) | 99 s | 0 |
| facile | v31 | 3 | 6/6 | - | - | 583 k (433-589 k) | 102 s | 0 |
| moyen | nu | 3 | 9/9 | 24/24 | 6/6 | 591 k (578-668 k) | 102 s | 0 |
| moyen | v25 | 3 | 9/9 | 24/24 | 5/6 | 596 k (576-656 k) | 90 s | 0 |
| moyen | v31 | 3 | 9/9 | 24/24 | 6/6 | 586 k (515-677 k) | 88 s | 0 |
| difficile | nu | 3 | 12/12 | 28/30 | 2/6 | 589 k (492-598 k) | 96 s | 0 |
| difficile | v25 | 3 | 12/12 | 30/30 | 4/6 | 654 k (518-911 k) | 141 s | 0 |
| difficile | v31 | 3 | 12/12 | 28/30 | 5/6 | 718 k (585-985 k) | 172 s | 0 |

| Tâche | v25 vs nu (tokens médians) | v31 vs nu (tokens médians) |
|---|---|---|
| facile | +6 % | +8 % |
| moyen | +1 % | -1 % |
| difficile | +11 % | +22 % |

## Lecture (n = 3 par couple ; ce n'est pas une preuve statistique)
- **Tâche où Claude seul échoue : `difficile`.** Claude seul fait 28/30 en spec (message d'un cycle non simple) et 2/6 en robustesse. C'est sur cette tâche que les bras se séparent un peu :
  - v2.5 obtient 30/30 en spec et 4/6 en robustesse ;
  - V3.1 obtient 28/30 en spec et 5/6 en robustesse.
  - Les écarts de robustesse tiennent à 1 à 3 tests de temps sur 6, dont un livrable de Claude seul instable : **signal faible**, à confirmer.
- **Tâches facile et moyenne** : effet plafond. Les 3 bras font 100 % des tests cachés et de la spec étendue, à un test de robustesse près.
- **Coût** :
  - V3.1 ne réduit pas les tokens : -1 % (moyen), +8 % (facile), **+22 % (difficile)** en médiane, avec une dispersion large (585 à 985 k).
  - Sa durée médiane sur `difficile` est 1,8 fois celle de Claude seul (172 s contre 96 s).
  - **La cible du cahier (−20 % de tokens médians à qualité non inférieure) n'est pas atteinte.**
- **Cause principale, mesurée** : sur une invite courte en `claude -p`, le cycle V3.1 (cadrage, compilation du plan, Vigie, Relais) **ne se déclenche pas**. Le plugin ajoute son contexte et ses hooks sans changer la manière dont la tâche est exécutée. Sans fournisseur, le Relais ne peut rien économiser (`../ANALYSE.md`, § 2.2 et 2.5).
- Le seul levier de qualité mesuré jusqu'ici reste la **contre-épreuve adverse** (`../ANALYSE.md`, § 4) : 8/8 en robustesse aux deux essais, pour un coût d'environ 3 fois plus de tokens.

## Coût du banc (quota du compte, `get_usage`, session d'orchestration et session mère comprises)
| Moment | Semaine | Fenêtre de 5 h |
|---|---|---|
| Avant le 1er essai | 51 % | 55 % |
| Après la répétition 1 (9 essais) | 53 % | 68 % |
| Après la répétition 2 (18 essais) | 55 % | 84 % |
| Remise à zéro de la fenêtre de 5 h, avant la répétition 3 | 59 % | 26 % |
| Après la répétition 3 (27 essais) | 61 % | 37 % |

Soit environ 0,2 à 0,4 point de semaine par essai. Le seuil de 85 % de la semaine n'a jamais été approché.
