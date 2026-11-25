# Banc V3.1 (lot 10) — résultats intermédiaires : 2 répétitions sur 3 (25/11/2026)

**Statut : 18 essais sur 27.** La répétition 3 est étalée après la remise à zéro de la fenêtre de 5 h du quota (18:40 UTC). Après 18 essais, cette fenêtre est à 84 % ; une 3e répétition l'aurait saturée en cours de route et aurait produit des essais en erreur.

## Protocole (figé avant les essais)
- **Tâches** (empreintes `MANIFEST.json`, vérifiées avant chaque essai) : `facile` (duree), `moyen` (dedup), `difficile` (planif).
- **Bras** :
  - `nu` : Claude Code sans plugin ;
  - `v25` : plugin super-reprompt 2.5.0 ;
  - `v31` : plugin V3.1 de cette branche, sans fournisseur de Relais.
- **Conditions communes** : sessions `claude -p` isolées (`dev/a24_run.py` : configuration dédiée sans hook ni CLAUDE.md personnel, dossier vierge), même invite (« Réalise le projet décrit dans ENONCE.md. »), Sonnet 5.5, effort medium.
- **Juge objectif et aveugle**, sans modèle :
  - tests cachés, plus la batterie étendue figée (`batterie-etendue/`, empreintes vérifiées : 10 tests Spec et 2 tests Robustesse par tâche, sauf `facile`) ;
  - exécutés sur une copie du livrable ;
  - **re-jugés après le banc**, sur machine calme, 3 passes, verdict à la majorité. Les tests de robustesse sont des tests de temps, sensibles à la charge : pendant le banc, un même livrable passait puis échouait.
  - Il n'y a **pas de juge LLM**, pour préserver le quota : la qualité de rédaction n'est pas notée.
- **Tokens** : usage réel de la sortie JSON de `claude -p` (entrée, cache créé, cache lu et sortie).

## Résultats bruts
Fichier `journal.jsonl`, une ligne par essai, verdict pendant le banc et `juge_final`.

```
py -3 dev/a24_v31_rapport.py evals/v3-a24/v31/journal.jsonl
```

| Tâche | Bras | Essais | Tests cachés | Étendue spec | Étendue robustesse | Tokens médian (min-max) | Durée médiane | Erreurs |
|---|---|---|---|---|---|---|---|---|
| facile | nu | 2 | 4/4 | - | - | 522 k (476-567 k) | 107 s | 0 |
| facile | v25 | 2 | 4/4 | - | - | 575 k (573-577 k) | 80 s | 0 |
| facile | v31 | 2 | 4/4 | - | - | 586 k (583-589 k) | 88 s | 0 |
| moyen | nu | 2 | 6/6 | 16/16 | 4/4 | 584 k (578-591 k) | 93 s | 0 |
| moyen | v25 | 2 | 6/6 | 16/16 | 3/4 | 626 k (596-656 k) | 82 s | 0 |
| moyen | v31 | 2 | 6/6 | 16/16 | 4/4 | 596 k (515-677 k) | 87 s | 0 |
| difficile | nu | 2 | 8/8 | 19/20 | 2/4 | 593 k (589-598 k) | 93 s | 0 |
| difficile | v25 | 2 | 8/8 | 20/20 | 2/4 | 715 k (518-911 k) | 135 s | 0 |
| difficile | v31 | 2 | 8/8 | 19/20 | 3/4 | 852 k (718-985 k) | 267 s | 0 |

Écart des tokens médians à Claude seul :
- facile : v25 +10 %, v31 +12 % ;
- moyen : v25 +7 %, v31 +2 % ;
- difficile : v25 +20 %, v31 +44 %.

## Lecture provisoire (n = 2, pas une conclusion)
- **Tâche où Claude seul échoue** : `difficile`. Claude seul échoue 1 fois sur 20 en spec, sur le message d'un cycle non simple, et 2 fois sur 4 en robustesse (longue chaîne ; ce test est instable). Aucun bras n'est parfait sur cette tâche.
- **Qualité** : aucun écart net entre bras. Tous font 100 % des tests cachés. Les différences restent à 1 test près sur les batteries étendues.
- **Coût** : V3.1 ne réduit pas les tokens. Sur la tâche difficile, elle en consomme +44 % en médiane, et sa durée médiane est 2,9 fois plus longue (267 s contre 93 s). La cible du cahier (−20 % à qualité égale) **n'est pas atteinte** sur ces tâches.
- Cause probable, déjà notée dans `ANALYSE.md` § 2.2 : sur une invite courte en `claude -p`, le cycle de V3.1 (cadrage, plan, Vigie, Relais) ne se déclenche pas. Le plugin ajoute du contexte sans changer l'exécution. Le Relais, sans fournisseur, ne peut rien économiser.

## Coût du banc (quota du compte, `get_usage`)
| Moment | Semaine | Fenêtre de 5 h |
|---|---|---|
| Avant le 1er essai | 51 % | 55 % |
| Après 1 essai | 51 % | 58 % |
| Après la répétition 1 (9 essais) | 53 % | 68 % |
| Après la répétition 2 (18 essais) | 55 % | 84 % |

Soit environ 0,2 point de semaine et 1,6 point de fenêtre de 5 h par essai, la session d'orchestration comprise. Projection pour 27 essais : environ 57 % de la semaine, sous le seuil de 85 %.
