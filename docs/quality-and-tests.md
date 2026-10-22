# Qualité de traduction et preuves disponibles

## Trois vérifications différentes

| Vérification | Moyen utilisé aujourd'hui | Ce qu'elle prouve |
| --- | --- | --- |
| Fonctionnement du logiciel | 198 tests automatisés avec clients fournisseurs simulés | Traitement des cas prévus : fichiers, Word corrompus, langues, contexte, erreurs, rapports, comparaison et avis IA structuré |
| Alertes sur une traduction | Comparaisons locales des nombres, références et termes | Détection de certains écarts dans le texte extractible |
| Qualité linguistique réelle | Corpus de 30 passages, essais réels et formulaire de relecture | Premier essai du 22 octobre 2026 (3 moteurs, pré-relecture IA) : voir [résultats](../evaluation/RESULTATS_2026-10-22.md) ; relecture humaine à faire |

La vérification du 22 octobre 2026 après l'audit a réussi avec Python local et
dans Docker : **130 tests**, sans appel fournisseur réel ; **133 tests** après
ajout des notes Word et du journal ; **167 tests** après nettoyage PDF,
protection des codes et contrôles par passage ; **181 tests** après l'essai
réel (corpus de 30 cas) et les balises Word ; **198 tests** après la fiche de
contexte, le repérage des ambiguïtés et le glossaire version 4. Les anciennes
mentions de 18, 52, 63, 82, 87, 90, 99, 104, 106, 110, 130, 133, 167 ou 181 tests sont des états historiques, pas le
nombre actuel. Le retrait d'une langue a supprimé des cas paramétrés ; un
nombre de tests plus élevé ne signifie pas automatiquement une meilleure qualité.

## Ce que fait un mock

Un mock remplace le client API dans les tests. Selon le scénario, il renvoie
une traduction écrite à l'avance, ajoute `Translated` devant le texte, ou
simule une réponse vide, incomplète ou un échec. Ces réponses sont contrôlées
par le test ; elles ne sont pas produites par une IA.

Par exemple, le test d'un tableau renvoie `Equipo` et `Puerta 3` pour vérifier
la réinsertion dans les bonnes cellules. Un autre test compare `RN 204 : porte 3`
à une sortie contenant `door 4` pour vérifier l'alerte numérique.
Une négation inversée contenant les mêmes nombres peut passer sans alerte :
un test documente précisément cette limite.

Dans l'application, cliquer sur **Traduire le lot** avec une clé configurée
utilise au contraire le fournisseur réel. Le mode simulé est réservé aux tests.
Le conteneur `tests` n'a ni clé ni accès réseau ; aucun crédit IA n'est consommé.

## Limites des contrôles automatiques

- Un passage présent et non vide peut être faux ou incomplet dans son sens.
- Les nombres sont comparés sans interprétation des signes, unités ou conversions.
  Les séparateurs de milliers et décimales sont harmonisés (« 1 500,50 », « 1,500.50 »
  et « 1.500,50 » sont égaux). Un séparateur unique suivi de trois chiffres est lu
  comme milliers : « 12,500 » au sens de 12,5 est signalé. Les dates reformatées
  peuvent produire des alertes légitimes, et une inversion jour/mois n'est pas détectée.
- Le glossaire vérifie la présence de variantes attendues dans le document,
  sans aligner chaque occurrence source et cible. Un terme présent ailleurs
  peut masquer une omission. Flexions, composés et paraphrases peuvent être signalés.
- Les 55 notions, version 4, restent proposées : aucune validation métier
  ni amélioration linguistique mesurée n'est revendiquée.
- La conservation du XML Word et des images ne garantit pas une pagination
  identique. Un texte plus long peut déplacer des pages ou déborder ; les
  styles mélangés peuvent se retrouver sur des mots différents.
- Les PDF GPT sont reconstruits simplement ; les tableaux complexes, plans,
  scans et textes d'images ne bénéficient pas de la conservation Word.
- Aucun score automatique n'est affiché comme une certification. L'absence
  d'alerte n'autorise pas une utilisation opérationnelle sans la relecture requise.

## Comment obtenir une preuve de qualité

1. Choisir avec le métier les documents, langues, volumes et erreurs critiques.
2. Compléter le corpus avec des exemples autorisés et des traductions approuvées.
3. Effectuer des essais réels GPT et DeepL, avec les mêmes sources et les mêmes
   règles. Consigner moteur, modèle si connu, instructions, version du glossaire,
   date, durée et coût observés. Garder les sorties exactes avant correction.
4. Faire relire à l'aveugle si possible par une personne bilingue, avec validation
   métier pour les passages techniques. Compter séparément contresens critiques,
   omissions/ajouts, terminologie, lisibilité et problèmes de présentation.
5. Comparer le temps total de traduction, relecture, corrections et reprises à
   la méthode habituelle. Ne pas confondre coût API faible et rentabilité.
6. Corriger une cause identifiée, refaire les mêmes essais et vérifier aussi
   des cas nouveaux. Une absence d'erreur critique sur ce corpus est un critère
   d'acceptation du pilote, pas une garantie universelle.

Le [protocole d'exécution](../evaluation/README.md) fournit les formulaires et
commandes. La nécessité de confronter les mesures automatiques à des jugements
humains est également soulignée dans les
[recommandations officielles OpenAI](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Améliorations proposées mais non implémentées

Conserver, après autorisation et anonymisation, des réponses réelles avec
leurs métadonnées pour les rejouer sans coût dans les tests. Cela vérifierait
les régressions de nos contrôles sur ces réponses conservées, sans mesurer
le comportement actuel du fournisseur. Le projet n'a pas encore de mécanisme
automatique d'enregistrement/rejeu de réponses réelles.

Un avis IA sur le sens est désormais disponible à la demande dans la
comparaison ; voir [son contrat et ses limites](semantic-review.md).
Ce juge reste à calibrer sur des jugements humains et peut lui-même se tromper.
Il ne remplace pas la validation métier. Une campagne réelle automatique et
une intégration continue GitHub Actions ne sont pas implémentées aujourd'hui.
