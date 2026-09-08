"""
Cadena de RAG para responder preguntas de FAQ/políticas del restaurante
(horarios, métodos de pago, zona de reparto, normas) usando SOLO el
contenido indexado en Chroma por rag/ingest.py.

Dos consumidores reales (ver rag/README.md): server.py llama a
responder_faq() directamente para el chatbot de FAQ
(POST /faq/preguntar), y agents/complaint_graph.py la reutiliza tal cual
en su nodo consultar_politica para preguntar la política real aplicable
antes de clasificar una queja - en ningún caso se reimplementa RAG fuera
de este módulo.
"""

from collections.abc import Sequence

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

from pizzeria_bot.config import settings
from pizzeria_bot.rag.ingest import CHROMA_DIR, COLLECTION_NAME, get_embeddings

# "gemini-2.5-flash" (el recomendado por la documentación de LangChain en
# sept. 2026) devuelve 404 en la práctica: la propia API de Google indica
# que ya no está disponible para usuarios nuevos y sugiere este modelo.
CHAT_MODEL = "gemini-3.6-flash"
RETRIEVER_K = 4

PROMPT = ChatPromptTemplate.from_template(
    """Eres el asistente de preguntas frecuentes de una pizzería. Responde
la pregunta del cliente usando SOLO la información del CONTEXTO de abajo,
que viene de los documentos de políticas reales del restaurante.

Reglas:
- Si el CONTEXTO no cubre la pregunta, dilo explícitamente (p.ej. "No tengo
  esa información, te recomiendo llamar directamente al restaurante") -
  NUNCA inventes ni asumas una política que no esté en el CONTEXTO.
- No menciones que estás usando un "contexto" o "documentos" - responde de
  forma natural, como si conocieras las políticas del restaurante.
- Respuestas breves y directas.

CONTEXTO:
{context}

PREGUNTA: {pregunta}
"""
)


def _formatear_contexto(documentos: Sequence[Document]) -> str:
    if not documentos:
        return "(sin contexto relevante encontrado)"
    return "\n\n".join(doc.page_content for doc in documentos)


def get_vectorstore() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def get_retriever(k: int = RETRIEVER_K) -> Runnable:
    return get_vectorstore().as_retriever(search_type="similarity", search_kwargs={"k": k})


def build_chain(retriever: Runnable | None = None, llm: Runnable | None = None) -> Runnable:
    """Construye la cadena RAG completa (retriever -> prompt -> llm -> texto).

    retriever y llm son inyectables a propósito: los tests los sustituyen
    por fakes deterministas para poder verificar el cableado de la cadena
    sin necesitar una API key real ni llamar a Gemini (ver tests/test_rag.py).
    """
    retriever = retriever or get_retriever()
    # google_api_key explícito por el mismo motivo que en ingest.py: la
    # librería no ve settings.gemini_api_key si no se le pasa a mano.
    llm = llm or ChatGoogleGenerativeAI(
        model=CHAT_MODEL, temperature=0, google_api_key=settings.gemini_api_key
    )

    return (
        {
            "context": retriever | _formatear_contexto,
            "pregunta": RunnablePassthrough(),
        }
        | PROMPT
        | llm
        | StrOutputParser()
    )


def responder_faq(pregunta: str) -> str:
    """Responde una pregunta de FAQ/políticas del restaurante usando RAG
    sobre rag_docs/ (indexado previamente con `python -m pizzeria_bot.rag.ingest`)."""
    # run_name solo afecta a cómo se ve la traza en LangSmith (si está
    # activado, ver config.py) - sin esto, cada llamada aparece como
    # "RunnableSequence" a secas, indistinguible de cualquier otra cadena.
    return build_chain().invoke(pregunta, config={"run_name": "responder_faq"})


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) != 2:
        print('Uso: python -m pizzeria_bot.rag.faq_chain "tu pregunta"')
        raise SystemExit(1)

    print(responder_faq(sys.argv[1]))
