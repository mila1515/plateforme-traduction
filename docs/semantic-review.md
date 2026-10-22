# Analyse du sens à la demande

L'espace **Comparer les textes** permet de demander à OpenAI un avis sur la
fidélité de la traduction. Il distingue les reformulations correctes des
contresens potentiels : négations, obligations, conditions, responsabilités,
omissions, ajouts, valeurs et unités. Il ne modifie pas les documents.

## Utilisation

1. Traduire le document avec GPT ou DeepL, puis ouvrir **Comparer les textes**.
2. Lire le fournisseur et le modèle d'analyse affichés. Une clé OpenAI est
   nécessaire, même après une traduction DeepL.
3. Autoriser explicitement l'envoi de l'original et de la traduction à OpenAI.
4. Cliquer sur **Analyser le sens**. Le consentement seul ne lance aucun appel.
5. Lire l'avis et les passages suspects, puis les faire vérifier par une
   personne bilingue. Le rapport d'analyse peut être téléchargé séparément.

Le service utilise `OPENAI_REVIEW_MODEL` s'il est renseigné ; sinon il reprend
`OPENAI_MODEL`. Le modèle peut donc être le même que celui qui a traduit :
ce n'est pas une validation indépendante. L'analyse ajoute un appel payant
et n'est pas effectuée pendant les tests ni automatiquement après traduction.

## Contrat et limites

- Maximum 12 000 caractères pour chacun des deux textes. Au-delà, aucun appel
  n'est lancé ; les textes ne sont pas tronqués. La comparaison manuelle reste accessible.
- Un seul appel par analyse, sans relance automatique. En cas d'échec, un
  nouvel essai demande un clic explicite et peut être facturé à nouveau.
- Une analyse réussie reste dans le résultat en session. Afficher les textes,
  télécharger ou changer les sélections ne la relance pas. Le bouton est
  désactivé pour ce résultat après réussite.
- Les réponses refusées, incomplètes ou incohérentes sont rejetées. Un passage
  dont la citation est introuvable (après harmonisation des guillemets,
  apostrophes, espaces, casse et points de suspension) est écarté et compté ;
  les autres passages restent affichés. Si tous sont écartés, l'avis devient
  « ne peut pas conclure ». Une citation peut être vide du côté absent d'une
  omission ou d'un ajout, mais pas des deux côtés.
- Maximum 20 problèmes signalés et citations de 400 caractères. L'IA peut
  manquer des erreurs, mal apprécier le contexte ou signaler à tort une variante.
- Le rapport conserve fournisseur, modèle, langues, version des instructions,
  date UTC et empreinte de la paire de textes. Il contient les extraits cités,
  pas les documents complets, et doit être traité comme un contenu documentaire.
- Aucun statut « approuvé » ni pourcentage de fiabilité n'est produit. Les
  trois avis possibles sont « problèmes suspectés », « aucun problème signalé »
  et « analyse non concluante ». Tous nécessitent une validation humaine.
- L'analyse porte sur le texte extrait, pas sur la qualité d'extraction, les
  images, la mise en page ou les éléments Word non pris en charge.

Le JSON structuré contrôle la forme de l'avis, pas son exactitude ; voir la
[documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs).
La qualité de ce juge doit encore être mesurée sur des exemples métier avec
des jugements humains, selon les [principes d'évaluation](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
Les tests simulés vérifient le contrat, les citations et l'absence d'appels
automatiques ; ils ne prouvent pas la capacité réelle du modèle à détecter
un contresens. Aucun essai IA réel n'a été effectué pour cet ajout.
