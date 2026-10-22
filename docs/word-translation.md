# Traduction Word avec conservation de la structure

Pour un fichier DOCX traduit avec GPT, le service conserve le document source
et remplace ses textes dans leurs emplacements. La voie PDF reste distincte :
elle extrait le texte et reconstruit un document simple.

## Étapes

1. Valider le fichier, puis ouvrir son archive OOXML en mémoire.
2. Parcourir les paragraphes du corps et des cellules, y compris les tableaux
   imbriqués, les en-têtes et pieds de page, les notes de bas de page et
   les notes de fin. Les cellules fusionnées
   ne sont pas dupliquées ; un en-tête partagé n'est traduit qu'une fois.
3. Envoyer chaque paragraphe **en entier**. Le texte dont la mise en forme
   diffère du reste du paragraphe (gras, italique, lien) est balisé
   `⟪1⟫…⟪/1⟫` ; tabulations, sauts de ligne, images et champs deviennent des
   marqueurs `⟪2/⟫`. Le texte affiché des liens hypertextes est traduit ; les
   autres champs (PAGE, sommaire, renvois) restent dynamiques et intacts.
4. Traduire les paragraphes dans les limites habituelles. Rejeter les réponses
   structurellement incomplètes. Réunir les morceaux des paragraphes longs.
5. Replacer chaque passage balisé dans ses nœuds d'origine : la mise en forme
   suit les mots traduits, même si leur ordre change (« bouton **rouge** » →
   « **red** button »). Si le modèle perd, ajoute ou déplace une balise, le
   paragraphe reste traduit en entier mais sa mise en forme est répartie
   proportionnellement ; ces cas sont comptés dans le journal.
6. Recopier les autres fichiers de l'archive à l'identique, puis proposer
   le DOCX et le rapport de contrôle habituel.

Le texte des en-têtes et pieds de page fait donc partie du contenu envoyé au
fournisseur choisi. Les images sont conservées localement, sans OCR ni traduction
de leur contenu. Aucun appel de mise en page ou de correction supplémentaire.

## Ce qui est conservé et ce qui reste à vérifier

Les tableaux, bordures, largeurs, fusions, images et propriétés de sections
restent dans le fichier source. Les tabulations et sauts explicites sont
conservés. Les fichiers de styles, médias et relations restent identiques.
Les champs autres que les liens restent dynamiques, avec leur contenu d'origine.
Les propriétés invisibles (langue de correction, « pas de vérification ») ne
créent pas de balise.

La pagination exacte n'est pas garantie : une traduction plus longue peut
agrandir des cellules, déplacer des pages ou déborder d'une zone de taille
fixe. Un mot composé allemand peut porter une mise en forme partielle
(« _Haupt_-Panel »). Les liens gardent leur destination ; vérifier leur
libellé traduit.

Mesure réelle du 22 octobre 2026 (document de test, anglais et allemand) :
`gpt-4.1-mini` a rendu toutes les balises (0 paragraphe raté sur 36) ;
`gpt-5.4-mini` en a raté 13 sur 36, dont un essai entier. Le repli garde ces
paragraphes traduits, mais avec une mise en forme approximative.

Le texte des commentaires, graphiques, SmartArt et objets embarqués n'est pas
pris en charge par ce parcours. Lorsque le document contient des commentaires
ou du texte affiché par des champs (sommaire, renvois), le rapport de
contrôle l'indique dans `untranslated_parts` et l'interface l'affiche sous
**Comparer les textes**. Les
éléments conservés peuvent donc encore contenir du texte dans la langue
source. Les révisions suivies et documents complexes exigent une vérification
dans Word. Les champs et tables des matières peuvent nécessiter une mise à jour
manuelle. Le texte des plans/images n'est pas traduit.

## Vérification

Les tests utilisent un client IA simulé. Ils vérifient la conservation du XML
hors texte et des ressources de l'archive, les fusions horizontales/verticales,
les tableaux imbriqués, les styles mélangés, les images, les sections, les
en-têtes partagés, les champs et les sauts. Un groupe long revient dans sa
cellule d'origine. Des passages source incohérents sont rejetés avant l'appel.

Ces contrôles structurels ne prouvent pas que toutes les pages ont le même
rendu. Avant une démonstration ou utilisation métier, ouvrir le Word source
et traduit et comparer chaque page : texte complet, images visibles, tableaux
lisibles, absence de débordement et sens correct. La conservation du fichier
ne constitue pas une certification visuelle ou linguistique.
