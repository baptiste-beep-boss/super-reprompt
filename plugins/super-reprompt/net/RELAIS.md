# Relais — délégation bornée et vérifiable aux IA gratuites (lot L6)

Le Relais n'intercepte rien : un agent lui confie **un fichier**, il rend **un reçu de 6 lignes au plus** et écrit le
résultat dans un fichier. Claude lit le reçu, jamais la conversation avec le modèle gratuit.

```
py -3 net/relais.py plan  PLAN.json                    délégué / gardé + raison, par tâche
py -3 net/relais.py run   --task resume --in F --out G [--spec S]
py -3 net/relais.py batch lot.ndjson [--parallel 2]    reprise : les éléments OK ne sont pas rejoués
py -3 net/relais.py status | report <slug>
py -3 net/relais.py connect <fournisseur> | disconnect <fournisseur>
py -3 net/relais.py bench                              jeu figé (net/bench.py), 18 types par modèle
```

Codes de sortie : 0 OK · 2 gardé ou refusé · 3 repli Claude (Haiku, puis Sonnet) · 4 abandon · 5 incident.

## Chaîne d'une délégation
1. **Confidentialité** : la couleur **scellée** de la mission l'emporte (`--color` ne peut que durcir). Rouge : refus.
   Fichier rouge du scellé : refus. Orange : URL, e-mails, chemins, domaines, jetons et nom d'utilisateur remplacés par
   `[TYPE_n]`, restaurés dans la réponse ; fournisseurs qui s'entraînent sur les requêtes exclus.
   Puis **scan de secrets bloquant** (celui de la Vigie, `scripts/guard_core.py`) sur la source et la spec, quelle que
   soit la couleur, et une seconde fois sur la requête HTTP elle-même.
2. **Utilité** : déléguer si tokens économisés > 3 × (brief + reçu + vérification) et volume ≥ 1 500 tokens.
3. **Filtres durs** : exclus (par identifiant **et** par hôte), CGU, pays, arrêt net garanti, couleur, connexion,
   contexte, disjoncteur, couples coupés par l'auto-réglage (retouche > 15 % sur 20 essais).
4. **Score** explicable : qualité 0,35 · quota 0,25 · santé 0,15 · latence 0,10 · contexte 0,10 · diversité 0,05.
5. **Appel** : température 0, effort de raisonnement minimal, sortie JSON ; vide ou `finish_reason: length` = échec.
6. **Vérification** déterministe propre au type (`net/verify.py`).
7. **Échec** : un autre gratuit, une fois ; puis `REPLI haiku` ; puis `--after haiku` → `REPLI sonnet` ;
   `--after sonnet` → `ABANDON`. Jamais de boucle.
8. **Grand livre** `ledger.sqlite` (dans la mission scellée, sinon dans le foyer du Relais) ; les tokens Claude évités
   sont **estimés** et marqués comme tels.

## Clés
`relais connect groq` se tape **dans votre terminal** : adresse officielle, usage des données, puis saisie masquée,
appel de test, et la clé n'est gardée que si l'appel réussit. Stockage DPAPI (Windows) ou libsecret (Linux), sinon
refus (macOS : non pris en charge à ce jour). Jamais d'argument `--key`, jamais de variable d'environnement, jamais de
journal. La Vigie refuse la lecture des fichiers `*.dpapi`.

La clé est enregistrée **avec l'hôte** sur lequel l'appel de test a réussi : un fichier de fournisseurs modifié qui
garde l'identifiant mais change d'adresse ne reçoit pas la clé. Aucune redirection HTTP n'est suivie.

## Règles durcies après la revue sécurité (23/11/2026)
- Sans scellé, la couleur ne descend jamais sous **orange** (`--color vert` ne fait rien) ; scellé illisible ou couleur
  inconnue = **rouge**.
- Fichiers rouges comparés par sous-chaîne **et** par chemin résolu ; la spec en fichier passe la même porte.
- `--out` : dans le périmètre de la mission, jamais l'entrée, un lien, un fichier protégé ; écriture atomique.
- Entrée plafonnée à 400 ko ; expressions d'anonymisation bornées (temps linéaire).
- Les reçus ne recopient jamais de texte produit par le modèle (canal d'injection vers l'agent).
- Tâches **jamais déléguées** (architecture, sécurité, cryptographie, argent, acceptation…) : contrôlées par `run` et
  `batch` eux-mêmes, sur `--desc`, les champs texte de la spec et le `text` des lignes de lot, sans dépendre de `plan`.

## Limites assumées
- Les types dont la vérification **exécute du code produit par le modèle** (code répétitif, tests, regex/SQL/script,
  migration, erreur de build) ne partent qu'avec `--exec` **et** un projet vert. L'exécution se fait dans un processus
  `-I -S`, dossier jetable, environnement minimal et délai. **C'est une isolation, pas un bac à sable** : ce code peut
  lire les fichiers de l'utilisateur et ouvrir le réseau.
- Sans fournisseur connecté, la délégation externe vaut **zéro** : le Relais répond `REPLI haiku`.
- `providers.json` expire 30 jours après sa date : au-delà, aucun appel tant que les CGU n'ont pas été relues.
