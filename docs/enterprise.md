# Passage du prototype à une utilisation entreprise

Les choix ci-dessous sont des recommandations pour ce projet, pas des
fonctionnalités déjà livrées. Aucun moteur n'a été démontré supérieur sur un
corpus métier représentatif. Les volumes, documents et contraintes de
l'organisation doivent guider la décision.

## Première étape recommandée

Conserver le prototype Python/Streamlit pour un pilote contrôlé. Faire valider
les 50 notions et définir les utilisateurs, langues prioritaires, familles
de documents, confidentialité, budget et responsable de relecture. Mesurer
la qualité réelle et le temps gagné avant une refonte importante.

Pour les documents européens Word/PDF, je commencerais la comparaison par
DeepL documentaire comme candidat principal, face au parcours GPT existant.
DeepL propose la conservation de la présentation des fichiers Word ; cela
reste à vérifier sur les documents de l'entreprise, sans garantie de rendu
parfait ou de meilleure traduction. [Présentation officielle DeepL](https://www.deepl.com/en/features/document-translation/word).

Conserver GPT comme alternative selon les résultats sur les termes, le
contexte, les coûts et la correction humaine. Ne pas envoyer automatiquement
chaque document aux deux moteurs : chaque envoi doit être justifié, autorisé
et comptabilisé. Le glossaire DeepL natif est une intégration future à vérifier
pour les langues et le compte ; le projet ne l'utilise pas actuellement.

## Architecture cible conseillée pour un portail partagé

| Besoin | Choix proposé | Raison dans ce projet |
| --- | --- | --- |
| Interface de pilote | Garder Streamlit | Réutiliser le parcours et apprendre des usages |
| Portail métier durable | API Python FastAPI, interface adaptée aux usages | Réutiliser les services Python et séparer les traitements longs de l'affichage |
| Identités | Connexion à l'annuaire de l'entreprise par OIDC/SSO | Éviter de gérer un second ensemble de comptes et définir des rôles |
| Métadonnées et historique | PostgreSQL | Documents versionnés, travaux, tentatives, révisions, glossaires et droits |
| Fichiers | Stockage objet privé déjà approuvé par l'organisation | Séparer les fichiers de leurs métadonnées et définir accès, sauvegarde et suppression |
| Traitements longs | Workers et file de tâches, par exemple Celery/Redis | Continuer le travail quand l'utilisateur ferme le navigateur |
| Validation | Comparaison source/traduction et approbation d'une version précise | Une sortie automatique reste un brouillon jusqu'à décision humaine |
| Exploitation | Conteneurs versionnés sur un hébergement géré par l'organisation | Déployer, surveiller, sauvegarder et revenir à une version connue |

Une API séparée et une file se justifient lorsque l'usage partagé exige des
travaux persistants et simultanés. Un pilote limité peut rester plus simple.
La file ne garantit pas un unique appel facturé : conserver des identifiants
de travaux et tentatives, gérer les doublons et les réponses réseau incertaines.

Les droits doivent être vérifiés côté serveur à chaque accès, y compris les
téléchargements. PostgreSQL propose des politiques de sécurité par ligne,
utiles comme protection supplémentaire ; les propriétaires et rôles privilégiés
peuvent les contourner selon la configuration. Elles ne remplacent pas les
autorisations applicatives. [Documentation PostgreSQL](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

## Priorités et critères concrets

| Priorité | Travail à réaliser | Preuve attendue |
| --- | --- | --- |
| Avant un pilote partagé | Autorisations, fournisseurs admis, budgets et règles de conservation | Aucun accès au document d'un autre périmètre ; lancement interdit avant tout appel non autorisé |
| Qualité | Glossaire approuvé et corpus représentatif relu | Résultats par langue, erreurs critiques, corrections et temps de relecture consignés |
| Validation | Statut brouillon, correction et approbation versionnée | Retrouver qui a approuvé quelle version ; ne pas confondre téléchargement et approbation |
| Persistance | Travaux, sources et résultats versionnés | Fermer la session ne perd pas le suivi et ne relance pas silencieusement une traduction |
| Fiabilité | Reprise, doublons, plafonds et supervision | Une interruption ne provoque pas une boucle d'appels facturés |
| Livraison | Tests automatisés en CI et essais réels contrôlés séparés | Tests simulés sur chaque changement ; résultats de campagne réelle datés |
| Documents complexes | OCR ou traitement documentaire spécialisé si besoin mesuré | Vérification visuelle et linguistique sur scans, plans et tableaux réels |

Définir avec l'organisation les lieux de traitement, contrats fournisseurs,
types de documents autorisés, accès, rétention, suppression et sauvegardes.
Choisir des langues européennes ou un fournisseur européen ne détermine pas
à lui seul où chaque donnée sera traitée ni les garanties du contrat retenu.
Ne pas consigner les clés ou textes complets dans les logs techniques.

## Mesurer l'intérêt économique

Comparer, sur le même travail, le coût du fournisseur, le temps de relecture,
les corrections, les reprises et l'exploitation avec la méthode actuelle.
Une traduction bon marché qui demande une réécriture complète peut coûter
plus cher au total. Définir les seuils avec le métier ; aucun pourcentage de
gain ou budget de production n'a encore été mesuré pour ce projet.

La prochaine amélioration à plus forte valeur est donc une **évaluation réelle
documentée avec validation humaine**, puis un circuit de révision. Ajouter une
base de données seule ne démontrerait pas une meilleure qualité de traduction.
