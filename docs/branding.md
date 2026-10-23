# Adapter l'application à l'identité d'une entreprise

L'interface ne contient aucune marque codée en dur. Nom, logos, couleurs et
mode sombre se règlent dans deux fichiers, sans modifier le code.

## Nom et logos : `.env`

| Variable | Rôle | Valeur par défaut |
| --- | --- | --- |
| `APP_NAME` | Titre de l'onglet du navigateur | Traduction de documents |
| `APP_TAGLINE` | Slogan, réservé à un usage futur | Traduire, contrôler, relire |
| `APP_LOGO` | Logo affiché en haut à gauche sur fond clair | `assets/logo.svg` |
| `APP_LOGO_DARK` | Logo lisible sur fond sombre | `assets/logo_dark.svg` |
| `APP_LOGO_ICON` | Pictogramme de l'onglet du navigateur | `assets/logo_icon.svg` |

Les chemins sont relatifs à la racine du projet ou absolus. SVG, PNG et JPG sont
acceptés. Le logo s'affiche avec une hauteur de 32 pixels : prévoir un format
horizontal (environ 7 pour 1). Sans logo sombre, le logo principal sert dans
les deux modes. Un fichier introuvable est remplacé par une icône neutre, sans
erreur. Le plus simple est de remplacer les trois fichiers de `assets/` en
gardant leurs noms.

Le logo fourni est **provisoire et neutre** (deux bulles et une coche) : le
remplacer par celui de l'entreprise avant tout usage partagé.

## Couleurs et polices : `.streamlit/config.toml`

- `[theme.light]` et `[theme.dark]` : couleur principale (boutons, liens,
  éléments actifs), fonds, texte, bordures et couleurs d'état. Définir les deux
  modes permet à chaque utilisateur de choisir clair ou sombre dans le menu ⋮.
- `primaryColor` doit rester assez foncée pour un texte blanc sur les boutons
  (contraste d'au moins 4,5 pour 1).
- `font = "sans-serif"` utilise la police servie par Streamlit lui-même : aucun
  appel à un service externe de polices, ce qui convient à un usage en entreprise.
  Une police d'entreprise peut être ajoutée en fichiers locaux (`[[theme.fontFaces]]`).
- `toolbarMode = "minimal"` masque les menus réservés aux développeurs.

Les couleurs se mettent à jour au rechargement de la page ; un changement de
police ou de `.env` demande de redémarrer l'application (avec Docker :
`docker compose up -d --build`).

## Organisation des pages

`app.py` applique l'identité et affiche le menu en haut de page. Les pages sont
dans `app_pages/` : **Traduire** (page par défaut) et le groupe **Qualité**
(Relecture des essais, Validation du glossaire). Pour ajouter une page, créer
un fichier dans `app_pages/` et le déclarer dans `st.navigation` de `app.py`.

## Limite connue

Le bouton d'import de fichiers affiche « Upload » et « 5MB per file » en anglais :
ces textes appartiennent à Streamlit et ne se traduisent pas par la configuration.
