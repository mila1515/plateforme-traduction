from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
from pypdf import PdfReader

MAX_FILES = 5
MAX_BYTES = 5 * 1024 * 1024
MIMES = {'.pdf': 'application/pdf', '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}


def safe_name(name):
    return PurePosixPath(name.replace('\\', '/')).name


def validate_document(name, data):
    suffix = PurePosixPath(safe_name(name)).suffix.lower()
    if suffix not in MIMES:
        raise ValueError('Format accepté : PDF ou Word DOCX.')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Le fichier doit contenir entre 1 octet et 5 Mo.')
    try:
        if suffix == '.pdf':
            pdf = PdfReader(BytesIO(data))
            if pdf.is_encrypted:
                raise ValueError('Les PDF protégés ne sont pas acceptés.')
            if not any((page.extract_text() or '').strip() for page in pdf.pages):
                raise ValueError('PDF sans texte : les scans nécessitent un OCR.')
        else:
            with ZipFile(BytesIO(data)) as archive:
                if 'word/document.xml' not in archive.namelist():
                    raise ValueError('Ce fichier ne contient pas de document Word valide.')
                if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                    raise ValueError('Document Word trop volumineux après décompression.')
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Document illisible ou endommagé.') from exc
    return suffix


def output_name(name, language, index):
    path = PurePosixPath(safe_name(name))
    return f'{index:02d}_{path.stem}_{language}{path.suffix.lower()}'


def make_zip(files):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, data in files:
            archive.writestr(safe_name(name), data)
    return buffer.getvalue()
