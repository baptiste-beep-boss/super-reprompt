# Projet moyen : dedup

Module : `dedup.py`

1. `dedup(lignes, cle) -> (gardees, rapport)` : `lignes` est une liste de dict, `cle` une liste de noms de colonnes. Deux lignes sont doublons si leurs valeurs de cle sont egales apres suppression des espaces autour et passage en minuscules. On garde la premiere occurrence, dans l'ordre d'origine. `rapport` vaut `{"lus": n, "gardes": k, "doublons": {tuple_cle_normalisee: nombre_de_copies_retirees}}`. Une colonne de cle absente leve `KeyError`.
2. `dedup_csv(entree, sortie, cle)` : meme regle sur un CSV (UTF-8, separateur virgule), en-tete et ordre des colonnes conserves ; rend le rapport.
Bibliotheque standard seulement. Livrer `dedup.py` et ses propres tests.
