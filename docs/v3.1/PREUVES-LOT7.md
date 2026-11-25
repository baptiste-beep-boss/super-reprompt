# Lot 7 — Mémoire (preuves, 24-25/11/2026)

## Livré (rupture 4 de l'audit, suite)
- `scripts/memoire.py`, sans réseau ni modèle, réutilise le contexte, les modèles de notes et le verrou de `vault.py`.
  - `archive` est la partie **mécanique** de l'archiviste, en script, sans un token. Il range les décisions et leçons (événements `log.*`) et les risques ouverts (reçus) dans les notes du projet. Les lignes sont dédupliquées et les secrets refusés. Il est idempotent et n'écrit que dans `projets/<slug>/`.
  - `reprise` écrit `REPRISE.md` (moins de 1 200 tokens) à partir des seuls fichiers canoniques de la mission : objectif, état, fait et reste, décisions, leçons, risques, budget par étiquette, prochaine action.
- Raccordement dans `manager.py done` :
  - en fin de phase, `memoire.archive`, puis `sr-archiviste` **seulement pour le jugement** (tableau, consolidation) ;
  - à la clôture, `archive` puis `reprise`, et le brief de synthèse pointe vers `REPRISE.md` ;
  - `manager.py status` relit `REPRISE.md` à la reprise.
- Mode dégradé explicite sans vault : `<mission>/memoire/`, signalé comme tel.
- Fiche `sr-archiviste` : elle ne recopie plus ce que le script a rangé.

## Défaut trouvé par la mission réelle (corrigé, test de non-régression)
`vault.py index --full` plantait sur un index existant avec `OperationalError: Safety level may not be changed inside a transaction` : le `PRAGMA synchronous` venait après les `DELETE`. Ce chemin n'avait jamais été testé.
- Le correctif place le `PRAGMA` avant toute écriture.
- `test_vault.TestIndexSearch.test_full_reindex_works_on_an_existing_index` : rouge vu, puis vert.

## Mission réelle
`py -3 dev/mission_lot7.py` : **13/13 PASS**. Le vault jetable contient un autre projet, `client-b`, avec une ligne confidentielle. La mission compte deux phases, conduites par la boucle.
- `vault.py log` refuse une décision qui ressemble à un jeton.
- Fin de P1 : 1 décision et 1 leçon rangées par script.
- Clôture : `REPRISE.md` fait 519 caractères, environ 140 tokens. Le brief de synthèse est écrit.
- La décision répétée n'est écrite qu'une fois dans le vault.
- Une nouvelle invocation de `manager.py status` relit `REPRISE.md`.
- Étanchéité : rien de `client-b` dans la reprise ni dans les notes du projet, et aucun secret dans le vault du projet.
- Le mode dégradé sans vault est annoncé tel quel.
- `vault.py lint` ne trouve ni orpheline ni lien mort.
- **A10** :
  - l'index est construit hors du vault ;
  - la recherche à froid (`-I -S`, 7 essais) donne une **médiane de 212 ms**, pour un plancher de l'interpréteur de 134 ms sur la même machine, soit un **coût propre de la recherche de 78 ms** ;
  - la cible de 150 ms n'est **pas tenue sur cette machine**, qui est chargée.

## Tests
- `test_memoire` : 5 tests, rouge vu avant implémentation.
- `test_vault` : 29 tests, dont le nouveau.
- `py -3 dev/accept.py`, deux passages :
  - Premier passage : A1 ROUGE, 1 échec sur 531, `test_orchestration.Orchestration.test_milestones_archivist_and_synthesis`.
    - Rejoué seul, le test passe.
    - La suite complète, rejouée aussitôt (`unittest discover`, 577 tests, 512 s), est verte. L'échec est **intermittent**.
    - La trace n'a pas été conservée par `accept.py`, la cause n'est donc **pas prouvée**.
    - Hypothèse retenue : un `os.replace` refusé plus d'une seconde par un lecteur concurrent sous Windows chargé, au-delà de la fenêtre de reprise d'alors (20 × 50 ms).
    - Durcissement : l'écriture atomique attend désormais de façon progressive jusqu'à environ 8 s.
  - Second passage : A1 = 531 tests, 0 échec, 1 sauté. Bilan : vert 19, rouge 1 (A20, médiane 315 ms), non mesuré 4.
  - A10 reste « non mesuré » dans `accept.py`, qui cherche l'index du vault personnel. Il est mesuré par la mission ci-dessus.

## Critères V3.1
- A10 Mémoire / Obsidian : recherche, indexation et déduplication **fonctionnelles et mesurées**. Performance **FAIL** contre la cible de 150 ms sur cette machine (médiane 212 ms, plancher 134 ms). Une machine calme reste à mesurer.
- A11 Archiviste : **PASS** pour la partie raccordée, exécutée à une étape précise sans doublon (en script). L'agent de jugement n'a pas été exécuté.
- A12 Synthèse : raccordée à la clôture et fondée sur les reçus. L'agent n'a pas été exécuté : **NOT MEASURED**.

## Limites (non vérifié)
- Agents `sr-archiviste` et `sr-synthese` non exécutés en session réelle.
- La déduplication porte sur la ligne exacte, pas sur le sens.
- Le contrôle de qualité des notes s'appuie sur le `vault.py lint` existant. Les contradictions et informations périmées ne sont pas détectées.
