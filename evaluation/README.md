# Évaluer la qualité avant de la promettre

Le [guide qualité et tests](../docs/quality-and-tests.md) distingue les mocks,
les alertes automatiques et les essais réels. Le protocole ci-dessous prépare
des preuves ; `run.py` ne lance aucune traduction, `live.py` lance un essai réel
payant sur confirmation. Aucun des deux ne fournit de résultat validé.

Premier essai réel : voir [RESULTATS_2026-10-22.md](RESULTATS_2026-10-22.md), et sa synthèse Word
[Bilan d'évaluation de la qualité](../docs/Bilan_evaluation_qualite_FR-EN.docx). Après la relecture
humaine, mettre à jour les constantes de `bilan_qualite.py` et le régénérer.

Le corpus contient 30 passages fictifs français destinés à un premier essai
vers l'anglais britannique. Les cas C21 à C30 ciblent les pièges ajoutés après
l'audit : codes et liens, milliers, négations liées à une condition,
interdictions, « ne … que », ellipses et abréviations. Ce sont des cas de contrôle proposés, pas des
traductions de référence approuvées ni des procédures opérationnelles.
Le compléter avec les utilisateurs avant toute conclusion sur des documents réels.

## Essai réel automatisé

Le script traduit tout le corpus et écrit le formulaire avec les décisions à
`pending`. GPT passe par le service de l'application ; DeepL par son API texte
(l'API documentaire facture au moins 50 000 caractères par fichier).

```powershell
.\.venv\Scripts\python.exe -B -m evaluation.live --engine gpt --model gpt-4.1-mini --output evaluation/runs/gpt.json --confirm
.\.venv\Scripts\python.exe -B -m evaluation.live --engine deepl --output evaluation/runs/deepl.json --confirm
```

Le rapport de `run.py` ajoute pour chaque cas les indices par passage de
l'application (`passage_alerts`), pour mesurer leurs vraies et fausses alertes.

## Relire un essai dans l'application

Lancer l'application en local (`start.ps1`), puis ouvrir **Relecture des essais**
dans le menu latéral. Chaque cas affiche l'original, la traduction et les alertes
automatiques ; choisir En attente, Acceptée ou Rejetée et enregistrer. Seuls la
décision, les notes, le nom du réviseur et la date sont ajoutés au fichier :
la traduction enregistrée n'est jamais modifiée. Accepter exige le nom du
réviseur ; rejeter exige aussi une note expliquant l'erreur. Le bilan croise
décisions et alertes : « rejetés sans alerte » mesure ce que les contrôles
automatiques ratent, « acceptés avec alerte » les fausses alertes.

## Préparer et effectuer un essai manuel

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
Ces 30 passages ne suffisent pas à garantir toutes les langues ou les PDF longs.
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

## Présenter les résultats

Présenter un cas source, une sortie réelle erronée, l'analyse du réviseur,
la correction apportée et le résultat d'un nouvel essai. Conserver des cas
nouveaux pour vérifier que l'amélioration se généralise. Annoncer le nombre
de cas relus et rejetés, avec le périmètre exact, plutôt qu'un « taux de
fiabilité » universel. Le premier essai réel est résumé dans
[RESULTATS_2026-10-22.md](RESULTATS_2026-10-22.md) ; ses décisions humaines restent à renseigner.

Mesurer l'intérêt économique avec le temps total : traduction, contrôle,
corrections et reprises. Comparer à la méthode habituelle de l'utilisateur.
Le coût API seul ne mesure pas la rentabilité ; les contrôles automatiques
peuvent aider à cibler la relecture sans la remplacer.

Les essais et rapports locaux sont ignorés par Git car ils peuvent contenir
des documents ou annotations confidentiels. Ne partager que des preuves
fictives ou autorisées.
