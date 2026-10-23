# Glossaire multilingue : utilisation et entretien

## But et emplacement

Le fichier [technical.json](../data/glossaries/technical.json) regroupe 50
notions documentaires et techniques. Chaque notion contient ses termes et
variantes dans les quatre langues du projet : `FR`, `EN`, `ES`, `DE`.
Le code cible `EN-GB` est normalisé uniquement pour la
recherche dans le glossaire ; les codes envoyés aux moteurs restent inchangés.
Toutes les paires distinctes sont disponibles, y compris vers le français.

Ce sont des propositions de démonstration, pas une norme ferroviaire ni un
lexique certifié. Les ambiguïtés comme « consignation » sont volontairement
laissées à la validation métier plutôt que recevoir une traduction imposée.

## Étapes dans l'application

1. Choisir la langue du document, la langue souhaitée et le fournisseur.
2. Ouvrir **Voir le glossaire et son utilisation** pour consulter les
   correspondances et leur contexte.
3. Cocher **Utiliser le glossaire technique** pour l'activer. Il est désactivé
   par défaut tant que l'utilisateur ne choisit pas de s'en servir.
4. Importer le document, accepter l'envoi au fournisseur et lancer le lot.
5. Ouvrir **Contrôles** dans les résultats. Si un terme source reconnu n'a
   aucune variante cible attendue dans le document, une alerte `terminology`
   indique la notion et les termes attendus.
6. Télécharger le rapport JSON pour conserver la version exacte utilisée.
   Relire la traduction et corriger les alertes avec une personne compétente.

| Moteur | Action avant traduction | Contrôle après traduction |
| --- | --- | --- |
| GPT | Les entrées utiles sont ajoutées aux consignes de chaque lot | Présence des variantes cibles |
| DeepL | Aucun glossaire natif transmis dans cette version | Même contrôle de présence |

Il n'y a ni substitution automatique après traduction, ni appel de correction
supplémentaire. GPT reçoit un peu plus de texte en entrée, ce qui peut augmenter
le coût de l'appel existant. Seule une évaluation avant/après peut démontrer
une amélioration réelle. La structure du contexte suit le principe de consignes
et données distinctes décrit dans la
[documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/prompt-engineering).

## Valider le glossaire dans l'application

La page **Validation du glossaire** (menu latéral) affiche les notions dans les
quatre langues, avec recherche. Après vérification par une personne bilingue et
compétente sur le métier, saisir son nom et la date, cocher la confirmation et
valider : le statut passe à `approved` et le glossaire devient **utilisé par
défaut** dans la traduction. **Remettre le glossaire à valider** annule la
déclaration. Seuls le statut, le nom et la date changent ; les termes se
corrigent dans le fichier JSON. En Docker, le glossaire fait partie de l'image :
valider en local, puis committer le fichier.

## Ajouter ou corriger une notion

1. Ouvrir `data/glossaries/technical.json` en UTF-8. Copier la structure d'une
   entrée existante, avec un `id` unique et un contexte précis.
2. Renseigner les quatre langues. La première valeur de chaque liste est la
   traduction préférée ; les suivantes sont des variantes admises. Déclarer
   les pluriels ou flexions utiles, sans ajouter des mots de sens différent.
3. Éviter d'attribuer le même terme normalisé à deux notions différentes : le
   chargement le refusera. Éviter les termes trop génériques pour un contexte
   spécialisé. Le fichier est limité à 200 notions pour ce prototype.
4. Augmenter `version`, laisser ou remettre `status` à `proposed`, et remettre
   `reviewed_by` et `reviewed_at` à `null` après toute modification non relue.
5. Faire vérifier les quatre langues et les contextes par des personnes compétentes.
   Passer à `approved` seulement après cette validation, en renseignant
   `reviewed_by` et `reviewed_at` au format `AAAA-MM-JJ`. Cette validation porte
   sur le fichier entier ; elle est déclarative et ne remplace pas une relecture
   des documents. Pour des validations partielles, garder le statut `proposed`.
6. Relancer `tests` dans Docker Desktop. Après modification, reconstruire
   l'application avec `docker compose up -d --build` pour qu'elle utilise le
   nouveau fichier ; les tests lisent directement les fichiers locaux.
7. Vérifier des cas réels anonymisés avec et sans glossaire, y compris des
   mots nouveaux et des contre-exemples où le contexte ne convient pas.
   Committer ensuite les changements de données, tests et documentation.

## Limites à connaître

La détection ignore la casse, les variantes Unicode, les apostrophes courbes
et les espaces multiples. Les limites de mots évitent par exemple de trouver
« porte » dans « transporter ». Le contexte et la relecture restent nécessaires.

Ce contrôle ne fait pas d'analyse grammaticale. Des flexions non déclarées,
des mots composés allemands ou une paraphrase correcte peuvent produire une
alerte. Un terme cible trouvé ailleurs dans le document peut aussi masquer
une omission locale. Le résultat n'est pas un alignement des phrases ni un
contrôle de toutes les occurrences. Il ne détecte pas un contresens contenant
le bon vocabulaire. Il ne valide pas les termes imprimés dans des images.

Le glossaire guide GPT lorsqu'il trouve un contexte pertinent ; il ne force
pas le moteur à respecter chaque terme. Pour DeepL, il sert uniquement de
contrôle local. Une intégration native DeepL serait un travail séparé, à
vérifier selon les langues et capacités du compte utilisé.
