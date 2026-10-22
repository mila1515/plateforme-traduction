# Ambiguïtés de l'original et fiche de contexte

Deux options facultatives pour aider la traduction et la relecture. Aucune ne
valide le sens : elles réduisent le nombre de choix laissés au hasard et
signalent ceux qui restent.

## Fiche de contexte

Sous **Contexte du document (facultatif)**, l'utilisateur décrit le document
(domaine, public, termes imposés, 500 caractères au plus) et choisit un ton.

| Moteur | Description | Ton |
| --- | --- | --- |
| GPT | Ajoutée aux consignes de chaque lot | Ajouté aux consignes |
| DeepL | Non transmise | Option native de formalité (`prefer_more` / `prefer_less`) : vouvoiement en allemand, espagnol et français |

Pour GPT, la fiche oriente les mots et le registre ; elle ne passe jamais avant
la fidélité du sens, l'exhaustivité, les codes protégés ni les balises Word.
Elle est enregistrée dans le rapport de contrôle (`brief`) : c'est le texte de
l'utilisateur, pas celui du document. Version des consignes : `meaning-v5`.

## Repérer les ambiguïtés de l'original

Une phrase à double sens oblige le traducteur à choisir en silence. L'option
**Repérer les ambiguïtés de l'original** envoie le texte source seul à OpenAI,
dans un appel séparé et payant (`gpt-5.4` par défaut, réglable avec
`OPENAI_AMBIGUITY_MODEL`). Elle fonctionne aussi avec DeepL, si une clé OpenAI
est configurée. Cocher l'option vaut consentement à cet envoi.

Chaque doute indique le passage, une citation et les deux lectures possibles.
La citation est vérifiée dans le texte source ; un doute invérifiable est écarté.
Les doutes s'affichent avec les autres alertes sous **Comparer les textes** et
sont enregistrés dans le rapport (`category: ambiguity`). Si l'analyse échoue,
la traduction reste livrée et l'interface l'indique.

## Pourquoi un appel séparé

Mesure réelle du 22 octobre 2026, sur 6 phrases de test (4 ambiguës, 2 claires)
et sur le corpus de 30 phrases :

| Approche | Phrases de test | Corpus |
| --- | --- | --- |
| Doutes demandés à `gpt-4.1-mini` pendant la traduction | 1 ambiguïté sur 4, une explication erronée | Doutes sans objet (codes protégés, incertitude déjà explicite) |
| Analyse séparée avec `gpt-5.4` | 4 sur 4, aucun doute sur les phrases claires | « consignation » (deux sens techniques) toujours signalée ; 2 à 4 autres signalements, souvent pointilleux, variables d'un essai à l'autre |

Les doutes demandés pendant la traduction ont été abandonnés. L'analyse séparée
reste un signal pour la relecture : elle peut manquer une ambiguïté ou en
signaler une que le contexte métier lève.
