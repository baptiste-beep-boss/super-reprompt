# Lot 5 — Relais : contrat ProviderAdapter (preuves, 25/11/2026)

## Livré (rupture 3, suite)
- `net/adapters.py` implémente le **contrat commun** du §11.1 du cahier :
  - attributs et méthodes : `provider_id`, `capabilities`, `models`, `availability(key)`, `estimate_cost`, `execute`, `health_check`, `timeout`, `cancel` (déclaré non pris en charge : appel synchrone borné par le délai), `usage_metadata`, `error_mapping` ;
  - classes d'erreur : `rate_limit`, `auth`, `server`, `client`, `network`, `timeout`, `truncated`, `empty`, `bad_response`, `refused`, chacune marquée récupérable ou non ;
  - réponse normalisée : texte, tokens, modèle effectif, latence, coût, statut, identifiant fournisseur ;
  - coût étiqueté `estimated`, avec la source et la date de vérification, ou `unavailable` quand aucun tarif n'est déclaré : il n'est jamais inventé.
- Deux implémentations : `OpenAICompatAdapter`, qui enveloppe `relais.call_provider` (pas de redirection suivie, scan de secret, plafond de taille), et `MockAdapter` pour les tests.
- **`relais run`** passe par l'adaptateur (`_adapter_call`). Un refus de confidentialité y reste un refus, pas une panne du fournisseur. **`relais connect`** vérifie la connexion par `health_check`.
- **`execute_with_policy`** :
  - nouvelles tentatives bornées, avec backoff exponentiel et jitter, sur les seules erreurs récupérables ;
  - circuit breaker par fournisseur (un 429 l'ouvre aussitôt) ;
  - repli **fini** : le fournisseur suivant, puis `local` ;
  - sans fournisseur, repli local immédiat, annoncé comme tel ;
  - chaque tentative est tracée.
- **Exécution de code produit par un modèle désactivée** (§11.4 du cahier) : `adapters.sandbox_available()` répond `False` tant qu'aucun vrai bac à sable n'est branché. `--exec` ne suffit plus (`run` et `bench`). Le test r3 est mis à jour en conséquence, et la règle est documentée dans `RELAIS.md`.

## Mission réelle
`py -3 dev/mission_lot5.py` : **8/8 PASS**. Elle tourne contre de faux fournisseurs OpenAI-compatibles sur 127.0.0.1, sans aucun réseau sortant ni fournisseur externe connecté.
- `health_check` d'un fournisseur sain : `ok`, 359 ms. D'un fournisseur injoignable : faux, classe `network`.
- `relais run` délègue la tâche `commit` par l'adaptateur et écrit la sortie.
- Deux fournisseurs dont un en panne : la mission continue. Le score a choisi d'emblée le fournisseur sain, donc la bascule n'est pas prouvée par cet essai-là ; elle l'est par le suivant et par `test_a14`.
- Panne de tous (500 et 429) : repli fini vers Claude (Haiku), code 3, sans boucle.
- Aucun fournisseur : repli local, aucune fausse délégation.
- Tâche qui exécuterait du code du modèle : refusée même avec `--exec`, et rien n'est envoyé au fournisseur.
- Registre de la mission : `alpha OK`, `alpha OK`, `beta ECHEC`, `gamma 429`.

## Tests
- `test_adapters` : 14 tests, rouge vu avant implémentation.
- `test_relais`, `test_relais_verify`, `test_adapters` et `test_v3_invariants` : 93 tests OK. L'invariant I2 tient : le réseau reste dans `net/`, et la mission charge le faux serveur des tests par `importlib`.
- `py -3 dev/accept.py` : A1 = 549 tests, 0 échec, 1 sauté. A12 (18 vérificateurs), A13 (0 secret sorti sur 50), A14 (panne d'un puis de tous) et A15 (aucun fournisseur exclu joignable) verts. Bilan : vert 19, rouge 1, non mesuré 4. A20 : 585 ms, pour un plancher de l'interpréteur à 176 ms (machine chargée).

## Critères V3.1
- A16 Relais sans fournisseur : **PASS**. Fonctionnement sûr, repli local annoncé, aucune fausse délégation.
- A17 ProviderAdapter : **PASS**. Contrat commun testé avec des doublures et `health_check`.
- A18 Confidentialité : **PASS**, déjà acquis en v3 (A13 : 50 tentatives, 0 secret sorti) et maintenu sur le chemin de l'adaptateur.
- A19 Fallback : **PASS**. Tentatives bornées, breaker, repli fini.
- A27 : aucune prétention de bac à sable. L'exécution est coupée, pas « isolée ».

## Non vérifié
- Aucun vrai fournisseur externe : la connexion est réservée à l'utilisateur et le budget est de 0 €.
- `LiteLLM` n'a pas été étudié : non nécessaire tant que tous les fournisseurs parlent OpenAI-compatible.
- `execute_with_policy` est testé, mais `run_task` garde sa propre boucle de repli, plus riche (vérificateurs, double passe), alignée sur le contrat par l'adaptateur et non remplacée.
