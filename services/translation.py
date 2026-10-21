from pathlib import Path
from tempfile import TemporaryDirectory
import deepl
import openai

LANGUAGES = {'Anglais britannique': 'EN-GB', 'Espagnol': 'ES', 'Allemand': 'DE', 'Français': 'FR'}
SOURCE_LANGUAGES = {'Français': 'FR', 'Anglais': 'EN', 'Espagnol': 'ES', 'Allemand': 'DE'}
SOURCE_NAMES = {'FR': 'French', 'EN': 'English', 'ES': 'Spanish', 'DE': 'German'}


def validate_language_pair(source_language, target_language):
    if source_language not in SOURCE_LANGUAGES.values() or target_language not in LANGUAGES.values():
        raise ValueError('Langue non prise en charge.')
    if source_language == target_language.split('-')[0]:
        raise ValueError('Choisissez une langue de destination différente de la langue du document.')


def translate_document(data, suffix, language, api_key, client=None, source_language='FR'):
    validate_language_pair(source_language, language)
    if not api_key:
        raise ValueError('Configurez DEEPL_API_KEY dans le fichier .env.')
    client = client or deepl.DeepLClient(api_key)
    with TemporaryDirectory(prefix='traduction_') as directory:
        source = Path(directory) / f'source{suffix}'
        target = Path(directory) / f'resultat{suffix}'
        source.write_bytes(data)
        client.translate_document_from_filepath(str(source), str(target), source_lang=source_language, target_lang=language)
        return target.read_bytes()


def error_message(exc):
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, openai.AuthenticationError):
        return 'Clé OpenAI invalide. Vérifiez OPENAI_API_KEY dans .env.'
    if isinstance(exc, openai.RateLimitError):
        return 'Quota ou limite OpenAI atteint. Vérifiez le crédit API et la facturation de votre compte, puis réessayez plus tard.'
    if isinstance(exc, openai.NotFoundError):
        return 'Modèle OpenAI indisponible pour ce compte. Vérifiez OPENAI_MODEL dans .env.'
    if isinstance(exc, openai.PermissionDeniedError):
        return 'Accès OpenAI refusé. Vérifiez les permissions de la clé et du modèle.'
    if isinstance(exc, openai.APIConnectionError):
        return 'Connexion OpenAI interrompue. Vérifiez le réseau avant de relancer ; une requête peut déjà avoir été facturée.'
    if isinstance(exc, openai.APIError):
        return 'Erreur du service OpenAI. Vérifiez le compte et le modèle avant de relancer ; des requêtes du document peuvent déjà avoir été facturées.'
    if isinstance(exc, deepl.AuthorizationException):
        return 'Clé DeepL invalide ou accès non autorisé.'
    if isinstance(exc, deepl.QuotaExceededException):
        return 'Quota DeepL atteint. Vérifiez votre compte.'
    if isinstance(exc, deepl.DocumentTranslationException):
        return 'Échec après envoi à DeepL. Vérifiez votre compte avant une relance : une facturation peut déjà avoir eu lieu.'
    return 'Traduction impossible. Vérifiez la connexion, les limites du compte et le document avant de relancer.'
