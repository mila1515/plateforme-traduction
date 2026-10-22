# Essai réel du 22 octobre 2026

Premier essai avec de vrais moteurs sur le corpus pilote (30 phrases fictives,
français → anglais britannique). **Les décisions humaines restent à faire** :
les constats ci-dessous sont une pré-relecture assistée par IA, à confirmer par
une personne bilingue et compétente sur le métier.

## Configuration

| Moteur | Accès | Consignes | Durée |
| --- | --- | --- | --- |
| `gpt-4.1-mini` (actuel) | Service de l'application, protection des codes | `meaning-v3` | 7,8 s |
| `gpt-5.4-mini` | Idem | `meaning-v3` | 5,8 s |
| DeepL | API texte (l'application utilise l'API documentaire) | — | 1,4 s |

Commandes : `python -B -m evaluation.live --engine gpt --model … --output … --confirm`,
puis `python -B -m evaluation.run --trial … --output …`. Coût total : quelques
centimes et environ 1 900 caractères du quota DeepL. Fichiers bruts dans
`evaluation/runs/` (ignoré par Git).

## Erreurs repérées à la relecture (à confirmer)

| Cas | Moteur | Sortie | Gravité proposée |
| --- | --- | --- | --- |
| C05 | DeepL | « L'intervention » → *The presentation* | Majeure : sens faux |
| C12 | DeepL | « La consignation » → *The entry* | Majeure : terme de sécurité perdu |
| C26 | gpt-5.4-mini | « peut, mais ne doit pas » → *may, but must not* | À trancher : la phrase source est ambiguë |
| C25 | gpt-4.1-mini | « ne doit être réalisée » → *should be carried out* | Mineure à majeure : interdiction affaiblie |
| C10, C15 | DeepL | « contrôle » → *audit* / *test* | Mineure : terme imprécis |
| C02 | gpt-5.4-mini | « il » → *he* | Mineure : genre ajouté |

Codes, lien et e-mail (C21), montants (C22), nombres, dates et heures sont
corrects pour les trois moteurs. Aucune consigne contenue dans le texte (C20)
n'a été suivie.

## Ce que valent les contrôles automatiques

**Contrôles par passage (mots-clés).** Au premier passage : 13 alertes, dont
11 fausses (« et non », « ne … que », « EUR 1 500 » pris pour une référence).
Règles corrigées et cas réels ajoutés aux tests : il reste **1 alerte, juste**
(C25), et **0 fausse alerte** sur les 90 traductions. Ces contrôles ne voient
pas les erreurs de vocabulaire (C05, C12).

**Analyse du sens par IA** (`gpt-4.1-mini` comme juge). Elle détecte les deux
erreurs majeures de DeepL, mais signale aussi trois écarts discutables (C06,
C16, C21) tous en « majeur », et ne voit pas C26. Elle aide à cibler la
relecture ; elle ne la remplace pas.

## Word : mise en forme balisée

Document de test (lien au milieu d'une phrase, saut de ligne entre une
négation et sa condition, mots en gras et italique, tableau, champ PAGE),
traduit 6 fois par modèle vers l'anglais et l'allemand :

| Modèle | Paragraphes balisés ratés |
| --- | --- |
| `gpt-4.1-mini` | 0 / 36 |
| `gpt-5.4-mini` | 13 / 36 (dont un essai entièrement raté) |

Avec `gpt-4.1-mini`, les phrases restent entières, le texte du lien est traduit
et reste un lien, le gras suit « red » / « rote » malgré le changement d'ordre
des mots, et le numéro de page reste dynamique.

## Conclusions provisoires (30 phrases, une seule paire de langues)

- Sur ce corpus, GPT traduit mieux les termes métier que DeepL, sans doute grâce
  aux consignes et au contexte. Le glossaire natif DeepL serait à tester pour
  « consignation ».
- `gpt-5.4-mini` n'apporte pas de gain net sur `gpt-4.1-mini` ici, et respecte
  mal les balises Word : garder `gpt-4.1-mini` par défaut.
- C26 est ambigu en français : le réécrire (« n'est pas obligé de ») ou le
  garder comme test d'ambiguïté, mais pas le noter comme erreur du moteur.
- Prochain essai : documents PDF/Word réels (sauts de page, liens), autres
  langues cibles, et relecture humaine renseignée dans les fichiers d'essai.
