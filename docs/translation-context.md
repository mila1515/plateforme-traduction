# Traduire le sens et utiliser le contexte

Le moteur GPT ne reçoit pas une liste de mots à remplacer. Il traduit des
passages, avec une consigne explicite de fidélité au sens et de formulation
naturelle dans la langue cible. La version des consignes est `meaning-v2`,
enregistrée dans le rapport local des traductions GPT.

## Ce qui est demandé au moteur

Préserver négations, obligations et permissions, conditions, incertitude,
chronologie, acteurs, relations de cause à effet, valeurs et unités. Ne pas
transformer une hypothèse en certitude ni inventer un contexte manquant.
Le glossaire fournit des préférences selon leur contexte, sans imposer une
substitution incompatible avec la grammaire ou le sens.

## Découpage et contexte

Les passages courts restent entiers. Au-delà de 6 000 caractères, le code
privilégie une fin de phrase ou une ponctuation forte, puis un espace si
la phrase est trop longue. Une chaîne sans espace peut encore être coupée
à la limite. Cette méthode est une heuristique, pas une analyse linguistique
complète ; les abréviations et sources mal extraites peuvent la mettre en défaut.

Les lots contiennent jusqu'à 6 000 caractères de texte à traduire et 40
fragments. Chaque requête reçoit en plus le début du document (800 caractères
au maximum), un contexte précédent (800) et suivant (800). Ces extraits sont
des données de lecture uniquement : les consignes interdisent de les ajouter
au résultat. Seuls les blocs identifiés sont réinsérés. Les longs passages
reviennent dans leur paragraphe PDF ou emplacement Word d'origine.

Ce contexte est limité : il ne fournit pas tout le document à chaque appel
et ne garantit pas une cohérence parfaite à longue distance. Son ajout
augmente le texte envoyé et peut augmenter le coût. Le découpage peut aussi
modifier le nombre d'appels nécessaires, sans créer un appel séparé de résumé.

## Chunks et vecteurs : deux choses différentes

Un **chunk** est un morceau de texte. Ici, le découpage sert à borner les
requêtes et à garder une correspondance avec les emplacements du document.

Un **embedding** est une représentation numérique utilisée notamment pour
retrouver des textes proches. Le projet n'appelle pas d'API d'embeddings,
ne stocke pas de vecteurs et ne fait pas de recherche vectorielle. Il n'a
pas de pipeline RAG. Voir la [documentation des embeddings](https://developers.openai.com/api/docs/guides/embeddings).

Une recherche vectorielle pourrait plus tard retrouver des exemples ou des
documents métier pertinents dans un corpus validé. Ce n'est ni un traducteur
ni une preuve d'équivalence de sens ; elle ne suffirait pas à vérifier une
négation inversée. Pour ce prototype, le contexte voisin et les consignes
sont une première étape plus simple.

DeepL reçoit déjà le fichier complet via son API documentaire : notre code
ne lui applique pas de substitution mot à mot, et ne pilote pas ses mécanismes
internes. Les nouvelles consignes et le nouveau découpage concernent GPT.

## Fidélité demandée, qualité encore à mesurer

Une meilleure consigne ne démontre pas une meilleure traduction. Les tests
vérifient le découpage sans perte, la présence du contexte et l'absence de
duplication lors de la réinsertion. Ils utilisent des clients simulés.
Il faut encore comparer des sorties réelles avant/après sur le corpus métier
et les faire relire. L'[analyse du sens](semantic-review.md) reste un contrôle
IA séparé, explicite et payant, avec ses propres limites. Aucun nouveau score
de qualité réelle n'est revendiqué.

Les consignes et le contexte s'appuient sur le mécanisme décrit dans la
[documentation officielle OpenAI](https://developers.openai.com/api/docs/guides/prompt-engineering).
