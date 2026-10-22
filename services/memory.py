"""Mémoire de traduction locale : réutiliser les passages validés par un relecteur.

Un passage source identique (après normalisation des espaces et de la typographie
Unicode), pour la même paire de langues, reprend la traduction validée sans
appel au moteur. Seules les traductions confirmées par une personne y entrent :
corrections saisies, ou traduction entièrement relue.

Le fichier contient des phrases des documents traduits : il reste sur le poste
(ignoré par Git et par l'image Docker) et doit être traité comme confidentiel.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unicodedata

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'memory' / 'translation_memory.json'
FORMAT_VERSION = 1


def normalize(text):
    """Comparer sans dépendre des espaces multiples ni des variantes Unicode ; la casse compte."""
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def _key(source, source_language, target_language):
    pair = f"{source_language}>{target_language.split('-')[0]}"
    return hashlib.sha256(f'{pair}\n{normalize(source)}'.encode('utf-8')).hexdigest()


def load_memory(path=DEFAULT_PATH):
    """Mémoire vide si le fichier n'existe pas encore ; erreur lisible s'il est abîmé."""
    path = Path(path)
    if not path.exists():
        return {'version': FORMAT_VERSION, 'entries': {}}
    try:
        memory = json.loads(path.read_text(encoding='utf-8'))
        if memory.get('version') != FORMAT_VERSION or not isinstance(memory.get('entries'), dict):
            raise ValueError
        for entry in memory['entries'].values():
            if not all(isinstance(entry.get(field), str) and entry[field].strip()
                       for field in ('source', 'target', 'source_language', 'target_language')):
                raise ValueError
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f'Mémoire de traduction illisible : vérifiez ou supprimez {path.name}.') from exc
    return memory


def save_memory(memory, path=DEFAULT_PATH):
    """Écriture atomique : un arrêt brutal ne laisse jamais un fichier à moitié écrit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.memoire_', suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(memory, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def lookup(memory, source, source_language, target_language):
    entry = memory['entries'].get(_key(source, source_language, target_language))
    return entry['target'] if entry else None


def remember(memory, pairs, source_language, target_language):
    """Ajouter ou remplacer des paires validées ; renvoie le nombre de passages enregistrés."""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    count = 0
    for source, target in pairs:
        if not source.strip() or not target.strip():
            continue
        memory['entries'][_key(source, source_language, target_language)] = {
            'source': normalize(source), 'target': target.strip(),
            'source_language': source_language, 'target_language': target_language.split('-')[0],
            'validated_at': now}
        count += 1
    return count
