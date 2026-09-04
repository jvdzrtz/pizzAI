"""
Indexado de documentos de políticas/FAQ del restaurante (rag_docs/) en una
base vectorial Chroma local, para que faq_chain.py pueda responder
preguntas de horarios, métodos de pago, zona de reparto, normas, etc.
usando solo el contenido real de esos documentos (RAG).

Módulo standalone (ver rag/README.md) - no lo usa ningún otro punto del
proyecto todavía.

Ejecutar como script suelto cada vez que cambien los documentos:
    python -m pizzeria_bot.rag.ingest
"""

import logging
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from pizzeria_bot.config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DOCS_DIR = BASE_DIR / "rag_docs"
CHROMA_DIR = BASE_DIR / ".chroma"
COLLECTION_NAME = "politicas_restaurante"

CHUNK_SIZE = 700
CHUNK_OVERLAP = 100

# Único modelo de embeddings documentado actualmente para
# GoogleGenerativeAIEmbeddings (docs.langchain.com/oss/python/integrations/
# embeddings/google_generative_ai, comprobado sept. 2026), sin prefijo
# "models/". Es un modelo "preview" - si Google publica una versión
# estable no-preview, actualizar aquí.
EMBEDDING_MODEL = "gemini-embedding-2-preview"

_TEXT_SUFFIXES = {".txt", ".md"}
_PDF_SUFFIXES = {".pdf"}


def _load_one(path: Path) -> list[Document]:
    if path.suffix.lower() in _PDF_SUFFIXES:
        return PyPDFLoader(str(path)).load()
    if path.suffix.lower() in _TEXT_SUFFIXES:
        # encoding="utf-8" explícito: TextLoader usa si no el encoding por
        # defecto del sistema (cp1252 en Windows), que rompe cualquier
        # tilde/ñ de un documento en español guardado como UTF-8.
        return TextLoader(str(path), encoding="utf-8").load()
    return []


def load_documents(docs_dir: Path = DOCS_DIR) -> list[Document]:
    """Carga todos los .pdf/.txt/.md de docs_dir. Cualquier otro tipo de
    archivo (p.ej. .gitkeep) se ignora sin fallar."""
    documents: list[Document] = []
    for path in sorted(docs_dir.iterdir()):
        if not path.is_file():
            continue
        documents.extend(_load_one(path))
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_documents(documents)


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    # google_api_key explícito: la librería solo mira GOOGLE_API_KEY/
    # GEMINI_API_KEY en os.environ por defecto, y nuestro .env se carga vía
    # pydantic-settings (settings.gemini_api_key), no hacia el entorno del
    # proceso - sin esto, GoogleGenerativeAIEmbeddings no encuentra la key
    # aunque el resto del proyecto sí la tenga.
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=settings.gemini_api_key)


def ingest(docs_dir: Path = DOCS_DIR, persist_dir: Path = CHROMA_DIR) -> Chroma:
    """Trocea e indexa todo lo que haya en docs_dir, sustituyendo el índice
    anterior por completo (reindexado limpio, no incremental) - así los
    documentos borrados o modificados no dejan restos obsoletos en Chroma."""
    documents = load_documents(docs_dir)
    chunks = split_documents(documents)

    embeddings = get_embeddings()
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )
    if vectorstore._collection.count() > 0:
        vectorstore.delete_collection()
        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(persist_dir),
        )

    if chunks:
        vectorstore.add_documents(chunks)

    logger.info(
        "Indexados %d chunks de %d documentos en %s", len(chunks), len(documents), persist_dir
    )
    return vectorstore


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    vectorstore = ingest()
    print(
        f"Reindexado completo: {vectorstore._collection.count()} chunks "
        f"en la colección '{COLLECTION_NAME}' ({CHROMA_DIR})"
    )
