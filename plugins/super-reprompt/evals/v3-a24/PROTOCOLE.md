# Protocole A24 : comparaison a 4 bras (prepare, non lance)

**Statut : banc prepare, NON lance.** Le lancer coute du quota (estimation : 12 sessions completes, plus le juge) et
exige l'accord ecrit de l'utilisateur (CDC §12). Reduction possible et declaree : n = 1 sur deux projets.

## Ce qui est fige avant tout essai
Trois projets CODE, de difficulte croissante, dans `projets/` : `facile` (duree), `moyen` (dedup), `difficile` (planif).
Chacun a un `ENONCE.md` donne aux bras et des **tests caches** (`caches/`) que seul le juge execute. Empreintes SHA-256
de chaque fichier dans `MANIFEST.json`, verifiees par `py -3 dev/a24_manifest.py --check` avant chaque essai : un
projet modifie apres le gel invalide la comparaison.

## Les 4 bras
| Bras | Configuration |
|---|---|
| Claude nu | aucun plugin ; **Hooks personnels coupes** (settings sans hooks, CLAUDE.md global retire) |
| v2.5 | plugin super-reprompt 2.5.0 seul |
| v3 sans Relais | plugin 3.0.0, aucun fournisseur connecte (repli Haiku) |
| v3 complete | plugin 3.0.0 avec au moins un fournisseur gratuit connecte par l'utilisateur |

Meme modele et meme effort pour tous les bras (Sonnet 5.5, medium), session neuve par essai, dossier vierge,
meme invite : « Realise le projet decrit dans ENONCE.md. » **n = 3 par bras et par projet** (36 essais).

## Mesures
- **Qualite** : tests caches (taux de reussite) + note d'un **juge aveugle** (Opus 5.5) sur grille fixe : exactitude,
  lisibilite, tests fournis, respect de l'enonce (0 a 5 chacun). Le juge recoit les livrables renommes `bras-1..4`,
  sans configuration ni journal.
- **Cout** : tokens Claude par essai (get_usage avant et apres, et /context), tokens delegues au Relais (grand livre).

## Porte d'adoption
Qualite de « v3 complete » **non inferieure** a « v3 sans Relais » (ecart des tests caches <= 0 et note du juge
a moins de 0,5 point) **et** tokens Claude en baisse. Sinon le Relais reste optionnel, et c'est ecrit dans le README.

## Publication
Tout est publie dans `RESULTS.md`, echecs compris : chaque essai, sa sortie de tests caches, sa note, ses tokens.

## Commande de lancement (pour l'utilisateur, apres accord)
Aucune commande ne lance le banc automatiquement : chaque essai est une session neuve ouverte a la main, puis
`py -3 dev/a24_manifest.py --check` et les tests caches executes par le juge sur le livrable copie hors du depot.
