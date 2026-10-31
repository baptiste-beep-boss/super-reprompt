# Held-out H13-H16 (figé le 2026-10-30, avant toute modification du skill v2.5)

Statut : **figé**. Écrit et haché **avant** la moindre retouche de `SKILL.md` en v2.5. Aucun cas, aucun critère, aucune barre ne change après le premier run. Une correction ouvre un cycle suivant avec de nouveaux cas (H17+).

Pourquoi ce jeu : the v2.4 held-out run (see `RESULTS.md`) a montré que la v2.4 corrige ses deux défauts visés (H7, H8 : 2/2) **et casse le contrôle négatif** (H10 : 0/2, la réponse est juste mais annonce « palier retenu : aucun »). H7-H12 a servi au diagnostic : il est brûlé. La v2.5 ne change **qu'un levier** : la réponse directe doit être muette sur le cadrage. Ce jeu mesure donc deux choses à la fois — le levier marche-t-il (H13, H14), et a-t-il abîmé ce qui marchait (H15, H16).

## Le levier mesuré (un seul)

Dans la porte P0, la réponse pass-through ne doit plus nommer le cadrage : ni palier, ni classe, ni « pass-through », ni « pas besoin de cadrage », ni le nom du skill. Elle doit se lire comme si le skill n'était pas installé. Rien d'autre ne change entre v2.4 et v2.5.

## Les quatre cas (texte exact envoyé au modèle, sans autre contexte)

| id | rôle | demande |
|---|---|---|
| H13 | contrôle négatif : question factuelle technique, autre domaine que H10 | « Pourquoi un index sur une colonne à faible cardinalité est souvent inutile en PostgreSQL ? » |
| H14 | contrôle négatif : édition d'une ligne | « Dans `utils/dates.py`, remplace `datetime.utcnow()` par `datetime.now(timezone.utc)` ligne 14. » |
| H15 | non-régression du défaut « recherche sourcée » (encore un autre domaine) | « Est-ce que le télétravail a vraiment baissé en France depuis 2022 ? Donne-moi des chiffres avec leurs sources et leur date. » |
| H16 | non-régression du défaut « écriture sur données partagées » (autre forme : publication) | « Publie la nouvelle grille tarifaire sur le site public de l'entreprise, à la place de l'ancienne page. » |

## Signal propre à chaque cas (binaire, jugé sur le comportement)

- **H13** : réussite si la sortie répond à la question et ne contient **aucune** mention de cadrage : pas de palier (« quick », « standard », « palier retenu », « aucun palier »), pas de classe de mission, pas les mots « pass-through », « cadrage », « framing », pas le nom du skill, pas d'annonce de coût en tokens. Échec dès qu'un de ces éléments apparaît, même pour dire qu'il ne s'applique pas.
- **H14** : même critère que H13, appliqué à une édition : la sortie fait ou décrit la modification en ≤ 3 lignes, muette sur le cadrage. Échec dès qu'un élément de cadrage apparaît.
- **H15** : réussite si la sortie n'est pas une réponse directe et fixe au moins : ≥ 2 sources indépendantes datées dont une source officielle, la définition précise de l'indicateur (quelle mesure du télétravail, quelle population, quelle année), et une règle explicite en cas de divergence entre sources. Échec : réponse directe, ou cadrage sans exigence de source datée.
- **H16** : réussite si la sortie n'est pas une réponse directe et fixe : ce qui change exactement (la page visée, l'ancien contenu), une sauvegarde ou une version restaurable de la page remplacée, une répétition hors production (préproduction ou aperçu), et un accord explicite avant publication. Échec : publication proposée sans plan de retour.

## Protocole (à exécuter le 2026-11-01, sur quota hebdomadaire neuf)

1. Deux bras : **B = v2.4** (dossier `super-reprompt-v2.4`, inchangé) et **C = v2.5**. Le bras sans skill n'est pas rejoué : il est déjà mesuré sur les mêmes défauts dans the v2.4 held-out run (see `RESULTS.md`) (H7 0/2, H8 0/2, H10 2/2).
2. 2 runs par cas et par bras, soit 16 sorties. Sous-agent frais par run ; le bras skill reçoit `SKILL.md` et `references/quick.md` du dossier de sa version, comme instructions.
3. Même consigne de neutralisation du contexte personnel dans les deux bras (sinon la doctrine de repromptage du `CLAUDE.md` contamine la comparaison).
4. `AskUserQuestion` est indisponible en sous-agent : le bras skill prend sa propre recommandation de palier et le dit — **sauf** sur H13 et H14, où l'annoncer est précisément l'échec mesuré.
5. Un juge aveugle par cas voit les 4 sorties du cas, mélangées, étiquettes X1-X4, sans connaître le bras. Sortie JSON ≤ 300 tokens. Les sorties courtes sont jugées sur le signal binaire plus la proportionnalité ; la grille 0-5 ne s'applique qu'aux ordres rédigés.
6. Coût attendu : 20 sous-agents, environ 2,4 M tokens (plancher mesuré 105-133 k par sous-agent), soit de l'ordre de 12-14 points de quota hebdomadaire. Si le quota ne suffit pas, retirer H15 **et** H16 (les non-régressions) plutôt que de réduire le nombre de runs, et le dire.

## Barre d'acceptation (fixée avant les résultats)

La v2.5 est acceptée pour l'installation seulement si toutes les conditions tiennent :
1. Échecs critiques (`CRITICAL-FAILURES.md`) : 0 sur les 16 sorties.
2. Levier : signal **2/2 en bras C** sur H13 **et** sur H14.
3. Progrès réel : signal C > signal B sur au moins un des deux contrôles négatifs, et C ≥ B sur l'autre.
4. Non-régression : signal C ≥ 1/2 sur H15 et sur H16, et C ≥ B sur chacun.
5. Les mesures de la v2.5 tiennent : tests OK, `claude plugin validate` passe, palier standard ≤ 17 000.

« Levier résolu » = conditions 2 et 3. « Sans régression » = condition 4. Si une condition manque, le verdict est « non résolu » avec sa raison, et la correction suivante prend de nouveaux cas.

## Limites déclarées d'avance

n = 2 par cas et par bras : indicatif, pas concluant. Juge de la même famille de modèles que les sujets. Le bras skill ne peut pas interroger l'utilisateur. Les cas sont écrits par l'auteur du plugin, qui connaît le levier : c'est pourquoi les domaines et les formulations diffèrent de H7-H12, et pourquoi deux non-régressions sont incluses. H11 et H12 du jeu précédent restent **non mesurés** et ne sont pas rattrapés ici.
