# Évaluer la qualité avant de la promettre

Le [guide qualité et tests](../docs/quality-and-tests.md) distingue les mocks,
les alertes automatiques et les essais réels. Le protocole ci-dessous prépare
des preuves ; il ne lance pas de traduction et ne fournit pas de résultat validé.

Le corpus contient 20 passages fictifs français destinés à un premier essai
vers l'anglais britannique. Ce sont des cas de contrôle proposés, pas des
traductions de référence approuvées ni des procédures opérationnelles.
Le compléter avec les utilisateurs avant toute conclusion sur des documents réels.

## Préparer et effectuer un essai

Depuis la racine, créer le dossier local ignoré par Git et un formulaire :

```powershell
New-Item -ItemType Directory -Force evaluation/runs
.\.venv\Scripts\python.exe -B -m evaluation.run --output evaluation/runs/gpt-trial.json
```

Faire traduire les mêmes passages par le moteur choisi avec sa configuration
réelle, puis reporter les sorties exactes dans `translation`. Renseigner le
fournisseur, modèle si connu, date, version des instructions, coût et durée
observés dans `metadata`. L'outil ne lance aucun appel API. Ne pas remplacer
une sortie imparfaite par une correction avant de l'enregistrer.

Un réviseur bilingue examine chaque paire source/traduction. Faire intervenir
une personne compétente pour la terminologie métier. Examiner : fidélité du
sens, omissions/ajouts, obligations et négations, terminologie, nombres,
références, unités et lisibilité. Indiquer `accepted` ou `rejected`, le réviseur
et des notes expliquant les erreurs et leur gravité ; laisser `pending` sans
relecture. Toute inversion de négation, responsabilité ou valeur importante
doit entraîner un rejet dans ce pilote. Les décisions sont déclaratives.

Produire le rapport sans écraser les sorties originales :

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.run --trial evaluation/runs/gpt-trial.json --output evaluation/runs/gpt-report.json
```

Pour ajouter le contrôle des termes au même essai, renseigner les langues
source/cible dans `metadata`, puis créer un rapport distinct :

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.run --trial evaluation/runs/gpt-trial.json --glossary data/glossaries/technical.json --output evaluation/runs/gpt-glossary-report.json
```

Ce paramètre contrôle une sortie existante : il ne prouve pas que le moteur
a reçu le glossaire lors de la traduction. Consigner séparément son utilisation
dans la configuration de l'essai. Voir le [guide du glossaire](../docs/glossary.md).

Recommencer avec DeepL sur le même corpus et la même langue. Comparer les
décisions humaines, erreurs critiques, temps de correction, coût et durée.
Ne pas conclure qu'un moteur est meilleur à partir du seul nombre d'alertes.
Ces 20 passages ne suffisent pas à garantir toutes les langues ou les PDF longs.
Pour comparer les rendus PDF/Word, vérifier séparément tableaux, ordre de
lecture et caractères dans les fichiers exportés.

## Ce que prouvent les contrôles

Les tests simulés prouvent le comportement du logiciel face à des erreurs
connues. Les contrôles locaux comparent les occurrences de nombres et les
références majuscules du type `RN 204` ou `ST 2026 014`. La virgule décimale
et le point sont considérés équivalents ; espaces et tirets des références
aussi. Ils ne valident ni le sens, ni les signes, ni les unités. Le contrôle
optionnel du glossaire vérifie la présence de variantes cibles, sans certifier
leur bon emploi. Les nombres écrits en lettres, dates reformattées, séparateurs
de milliers ou en-têtes répétés peuvent produire des alertes légitimes.
Une inversion de négation peut passer sans alerte : un test le démontre.

Le rapport de l'application contrôle le texte extractible des fichiers, pas
les images ou les textes des graphiques. Les textes Word pris en charge
incluent désormais les en-têtes et pieds de page, hors champs automatiques.
Le contrôle n'ajoute aucun appel facturé et ne bloque
pas le téléchargement. Tous les résultats restent des brouillons à relire.

## Preuves utiles en entretien

Présenter un cas source, une sortie réelle erronée, l'analyse du réviseur,
la correction apportée et le résultat d'un nouvel essai. Conserver des cas
nouveaux pour vérifier que l'amélioration se généralise. Annoncer le nombre
de cas relus et rejetés, avec le périmètre exact, plutôt qu'un « taux de
fiabilité » universel. Aucun résultat réel n'est fourni dans ce dossier.

Mesurer l'intérêt économique avec le temps total : traduction, contrôle,
corrections et reprises. Comparer à la méthode habituelle de l'utilisateur.
Le coût API seul ne mesure pas la rentabilité ; les contrôles automatiques
peuvent aider à cibler la relecture sans la remplacer.

Les essais et rapports locaux sont ignorés par Git car ils peuvent contenir
des documents ou annotations confidentiels. Ne partager que des preuves
fictives ou autorisées.
