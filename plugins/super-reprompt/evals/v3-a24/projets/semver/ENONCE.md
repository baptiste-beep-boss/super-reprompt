# Projet tres difficile : semver

Module : `semver.py` (bibliotheque standard seulement). Livrer `semver.py` et ses propres tests.

API : `satisfies(version, plage) -> bool`, `max_satisfying(versions, plage) -> str | None`, `class RangeError(ValueError)`.

## Versions
`MAJEUR.MINEUR.CORRECTIF`, avec `-prerelease` et `+build` facultatifs. Entiers sans zero de tete (`01` est invalide). Prerelease : identifiants separes par des points, caracteres `[0-9A-Za-z-]`, un identifiant numerique n'a pas de zero de tete, aucun identifiant vide. Build : meme alphabet, ignore dans toute comparaison. Un `v` initial et les espaces autour sont toleres. Une version invalide leve `ValueError` (pas `RangeError`).

## Ordre (precedence)
Compare MAJEUR, MINEUR, CORRECTIF numeriquement. Une version avec prerelease est inferieure a la meme version sans prerelease. Deux prereleases : identifiant par identifiant ; deux numeriques se comparent comme entiers ; un numerique est inferieur a un alphanumerique ; deux alphanumeriques se comparent en ordre ASCII ; si tous les identifiants communs sont egaux, la liste la plus courte est inferieure.

## Plages
Une plage est une union de blocs separes par `||`. Un bloc est une suite de comparateurs separes par des espaces, qui doivent TOUS etre satisfaits. Un bloc vide, ou `*`, vaut `>=0.0.0`. Une plage invalide leve `RangeError`.

Comparateurs :
- `>=`, `<=`, `>`, `<`, `=`, ou aucun operateur (egalite), suivis d'une version ; les operateurs peuvent etre separes de la version par des espaces (`>= 1.2.3`).
- Version partielle, avec `x`, `X` ou `*` comme joker : `1`, `1.x`, `1.2`, `1.2.x`. Sans operateur ou avec `=` : `1` vaut `>=1.0.0 <2.0.0`, `1.2` vaut `>=1.2.0 <1.3.0`. Avec operateur : `>1.2` vaut `>=1.3.0`, `>=1.2` vaut `>=1.2.0`, `<1.2` vaut `<1.2.0`, `<=1.2` vaut `<1.3.0`, `>1` vaut `>=2.0.0`, `<=1` vaut `<2.0.0`, `<1` vaut `<1.0.0`.
- Caret `^` : `^1.2.3` vaut `>=1.2.3 <2.0.0` ; `^0.2.3` vaut `>=0.2.3 <0.3.0` ; `^0.0.3` vaut `>=0.0.3 <0.0.4` ; `^1.2` vaut `>=1.2.0 <2.0.0` ; `^0.0` vaut `>=0.0.0 <0.1.0` ; `^0` vaut `>=0.0.0 <1.0.0`. Avec prerelease, `^1.2.3-beta.2` vaut `>=1.2.3-beta.2 <2.0.0`.
- Tilde `~` : `~1.2.3` vaut `>=1.2.3 <1.3.0` ; `~1.2` vaut `>=1.2.0 <1.3.0` ; `~1` vaut `>=1.0.0 <2.0.0`.
- Tiret `A - B` (espaces obligatoires autour du tiret) : `A` partiel est complete par des zeros (`>=A`) ; `B` complet donne `<=B` ; `B` partiel donne la borne exclusive suivante : `1.2.3 - 2.3` vaut `>=1.2.3 <2.4.0`, `1.2.3 - 2` vaut `>=1.2.3 <3.0.0`.

## Regle des prereleases
Une version AVEC prerelease ne satisfait un bloc que si au moins un comparateur de ce bloc (apres traduction) porte la meme triplette MAJEUR.MINEUR.CORRECTIF ET possede lui-meme un prerelease ; sinon elle est rejetee, meme si elle est dans les bornes. Une version sans prerelease n'est pas concernee. Cette regle s'applique bloc par bloc.

## max_satisfying
`max_satisfying(versions, plage)` rend, parmi les chaines de `versions` qui satisfont la plage, celle de plus haute precedence, telle qu'ecrite dans la liste (a precedence egale, la premiere de la liste) ; `None` s'il n'y en a aucune. Une version invalide dans la liste leve `ValueError`.
