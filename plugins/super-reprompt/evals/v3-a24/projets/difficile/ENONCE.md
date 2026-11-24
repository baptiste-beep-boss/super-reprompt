# Projet difficile : planif

Module : `planif.py`

`planifier(taches, max_parallele) -> list[list[str]]` : `taches` associe chaque nom de tache a la liste de ses dependances. Rendre des vagues : chaque tache apparait une fois, apres toutes ses dependances (dans une vague strictement anterieure) ; une vague contient au plus `max_parallele` taches ; chaque tache part dans la premiere vague possible, a egalite par ordre alphabetique ; les vagues sont triees.
Erreurs : une dependance inconnue leve `KeyError` ; un cycle leve `CycleError` (sous-classe de `ValueError`, a definir dans le module) dont le message cite toutes les taches du cycle ; `max_parallele < 1` leve `ValueError`.
Bibliotheque standard seulement. Livrer `planif.py` et ses propres tests.
