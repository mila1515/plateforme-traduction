# Corrections et mémoire de traduction

Le relecteur corrige la traduction dans l'application ; les passages qu'il
valide sont réutilisés ensuite sans appel au moteur. Fonctionne avec GPT
uniquement : DeepL traduit le fichier d'un bloc, sans correspondance passage
par passage.

## Corriger une traduction

1. Sous un résultat GPT, ouvrir **Corriger la traduction** : un tableau
   « N° | Original | Traduction », seule la colonne Traduction est modifiable.
2. Choisir ce qui entre dans la mémoire : les passages corrigés, toute la
   traduction (si elle a été entièrement relue), ou rien.
3. **Appliquer les corrections** reconstruit le fichier, sans appel payant, et
   recalcule les contrôles locaux. Le rapport indique les passages corrigés
   (`corrections`) ; un avis d'analyse du sens obtenu avant est retiré, car il
   portait sur l'ancienne traduction.

Un passage vide est refusé. Un passage non modifié garde sa traduction d'origine
et, pour Word, sa mise en forme exacte. Un paragraphe Word corrigé qui contenait
du gras ou un lien garde une mise en forme répartie proportionnellement.

## Réutiliser la mémoire

**Réutiliser la mémoire de traduction** est coché par défaut dès que la mémoire
contient des passages. Un passage source identique (espaces et variantes Unicode
ignorés, casse comprise), pour la même paire de langues, reprend la traduction
validée : il n'est pas envoyé au moteur. Le résultat indique les passages repris.

Un paragraphe Word mis en forme (gras, lien…) n'est jamais repris de la mémoire :
sa mise en forme ne pourrait pas être replacée. Il est retraduit normalement.

Mesure réelle : 10 phrases validées puis retraduites avec une nouvelle phrase,
les 10 sont reprises à l'identique et seule la nouvelle est envoyée
(4,9 s → 1,1 s). Aucun coût d'API supplémentaire : la mémoire en économise.

## Fichier et confidentialité

La mémoire est un fichier JSON local, `data/memory/translation_memory.json`
(chemin modifiable avec `TRANSLATION_MEMORY_PATH`). Il est ignoré par Git et
exclu de l'image Docker ; avec Docker Compose, le dossier `data/memory` est
monté pour survivre aux redémarrages. **Il contient des phrases des documents
traduits** : le traiter comme les documents eux-mêmes.

Sous **Gérer la mémoire de traduction** (bas de page) : nombre de passages,
téléchargement du JSON, et vidage après une case de confirmation. L'écriture
est atomique : un arrêt brutal ne corrompt pas le fichier. Un fichier abîmé est
signalé et la mémoire désactivée, sans bloquer la traduction.

## Limites

- Correspondance exacte uniquement : une phrase proche mais différente est
  retraduite (pas de suggestion approchante).
- Une traduction validée dans un contexte est reprise dans tous les documents :
  la mémoire ne distingue pas les domaines.
- Les tests (`tests/conftest.py`) utilisent toujours une mémoire temporaire,
  jamais celle du poste.
