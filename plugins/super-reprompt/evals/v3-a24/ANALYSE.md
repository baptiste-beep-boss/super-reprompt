# Analyse : pourquoi v3 ne rend pas plus fort, et ce qui peut le faire

Redigee le 24/11/2026 apres le banc A24 reduit (`RESULTS.md`). Chiffres mesures, sauf mention « hypothese ».

## 1. Le constat
Sur deux projets de code, tests caches a 100 % pour Claude nu, v2.5 et v3 ; juge aveugle a egalite (35, 35, 34 sur 40) ;
v3 consomme +11 a +85 % de tokens. Rien de ce que v3 ajoute ne s'est traduit en qualite.

## 2. Les cinq causes, de la plus lourde a la plus legere

### 2.1 Le banc ne pouvait pas voir de gain (effet plafond)
Les tests caches d'origine font 3 et 4 cas. Claude nu les reussit tous : aucune methode ne peut depasser 100 %.
Le juge, lui, a trouve de vrais defauts (BOM, cycle mal cite, algorithme quadratique) qu'aucun test cache ne couvrait.
Une batterie etendue tiree de l'enonce (`batterie-etendue/`, 18 tests « spec » + 4 « robustesse ») les retrouve :
nu 18/18 + 3/4, v2.5 18/18 + 4/4, v3 17/18 + 1/4. **La marge de progres existe ; elle est dans la robustesse.**

### 2.2 v3 n'agit pas sur l'execution
v3 cadre, surveille, range, delegue et economise. Ce sont des fonctions de **gouvernance** : elles evitent des
accidents (pare-feu : `git push --force` bloque en essai reel) et organisent les longs projets. Aucune ne fait produire
un meilleur code a la session qui ecrit. Sur une invite courte, les hooks de cadrage restent silencieux par conception :
v3 se comporte alors comme Claude nu + 1,3 % de contexte.

### 2.3 Plus de regles n'est pas plus de capacite
Le modele planifie deja seul. Ajouter des consignes coute du contexte relu a chaque tour sans ajouter d'information
sur le probleme. C'est la meme lecon que le skill `mission` (273 k tokens pour cadrer une mission) : la structure
se paie, la capacite ne vient pas d'elle.

### 2.4 Ce qui fait reellement progresser un modele : du calcul de verification independant
Une equipe de developpement est forte surtout parce que **quelqu'un d'autre** relit et casse le travail. Le juge du
banc a joue ce role et a trouve en quelques minutes ce que l'auteur avait rate. Hypothese a tester : un testeur
adverse, en contexte neuf et en boite noire, suivi d'un correcteur, apporte le gain que v3 n'apporte pas.

### 2.5 L'economie de tokens suppose un fournisseur
Le Relais, cœur de l'economie, se replie sur Haiku tant qu'aucun fournisseur gratuit n'est connecte. Sur ce banc,
il n'a rien pu economiser.

## 3. La methode testee : contre-epreuve adverse
`dev/a24_adverse.py` : realisation (meme invite que les autres bras) → testeur adverse (session neuve, boite noire,
consigne generique qui ne cite aucun cas de la batterie) → correcteur (session neuve, ecarte un test faux en le disant).
Mesure sur la batterie etendue figee avant l'essai (empreintes dans `batterie-etendue/EMPREINTES.sha256`).
Resultats : voir section 4.

## 4. Resultats de la methode (24/11/2026)

Batterie etendue (spec 18 + robustesse 4 par paire de projets), tokens Claude totaux par essai :

| Bras | Essais | Spec | Robustesse | Tokens moyen | Tokens difficile |
|---|---|---|---|---|---|
| Claude nu | 2 | 36/36 | 7/8 | 279 k / 504 k | 660 k / 511 k |
| v2.5 | 1 | 18/18 | 4/4 | 332 k | 663 k |
| v3 sans Relais | 1 | 17/18 | 2/4 (1/4 au 1er passage : test de temps sensible a la charge) | 517 k | 733 k |
| Contre-epreuve adverse | 2 | 36/36 | **8/8** | 1 530 k / 1 561 k | 1 617 k / 1 853 k |

Lecture :
- **La contre-epreuve adverse est la seule methode sans aucun defaut** sur la batterie etendue, aux deux essais.
  Mais Claude nu fait deja 7/8 : sur des taches de cette taille, l'ecart est d'un seul test. Gain reel, faible.
- **Elle coute environ 3 fois plus de tokens** (trois sessions au lieu d'une).
- **La variance de Claude nu seul est enorme** : 279 k puis 504 k tokens pour le meme projet. Les ecarts de tokens a n = 1
  (dont le « +85 % » de v3) sont donc dans le bruit.
- **v3 est le seul bras qui echoue a un test de l'enonce** (message de cycle incomplet) : signal faible a n = 1.

## 5. Conclusion
1. Sur des taches courtes et bien specifiees, Claude seul est deja proche du maximum : aucune methode ne peut y montrer
   un « x3 ». Le gain d'une equipe se joue sur des taches longues, multi-fichiers, ambigues, ou Claude seul echoue.
2. Ce qui ajoute de la qualite, c'est la **verification independante** (contre-epreuve adverse), pas le cadrage ni les
   regles. Elle a corrige tous les defauts que l'auteur seul laissait passer.
3. Prochaine etape pour mesurer un vrai multiplicateur : un banc **difficile** (projet de plusieurs modules, specification
   longue, cas pieges nombreux) ou Claude nu echoue nettement, puis comparer nu, contre-epreuve adverse, et equipe
   parallele (worktrees). Sans ce banc, toute promesse de « x3 » reste non mesuree.

## 6. Suite (27/11/2026)
Contre-épreuve intégrée comme **option** (lot 11) et mesurée sur la tâche `semver`, n = 3 : aucun gain de qualité, surcoût de +43 % (Sonnet) à +69 % (Haiku) en tokens. Haiku seul égale Sonnet seul à 3,3 fois moins en équivalent API. Détail : `v32/RESULTATS.md`.
