"""
Tests del módulo rag/ (FAQ/políticas del restaurante). Ver rag/README.md
para el porqué de la separación entre tests unitarios (sin red, sin API
key) y el test de integración (con Gemini real).
"""

import pytest
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from pizzeria_bot.config import settings
from pizzeria_bot.rag.faq_chain import build_chain
from pizzeria_bot.rag.ingest import ingest, load_documents, split_documents

# ---------------------------------------------------------------------
# Unitarios: ingesta (carga + troceo). Sin red, sin API key.
# ---------------------------------------------------------------------


def test_load_documents_lee_txt_en_utf8(tmp_path):
    (tmp_path / "politicas.txt").write_text(
        "El restaurante abre de 12:00 a 23:30 todos los días.\n"
        "Aceptamos efectivo, tarjeta y Bizum.",
        encoding="utf-8",
    )

    documentos = load_documents(tmp_path)

    assert len(documentos) == 1
    # Si TextLoader usara el encoding por defecto del sistema en vez de
    # UTF-8 explícito, "días" saldría con mojibake ("dÃ­as").
    assert "días" in documentos[0].page_content
    assert "12:00 a 23:30" in documentos[0].page_content


def test_load_documents_ignora_archivos_no_soportados(tmp_path):
    (tmp_path / ".gitkeep").write_text("")
    (tmp_path / "notas.json").write_text("{}")

    assert load_documents(tmp_path) == []


def test_load_documents_carpeta_vacia_no_falla(tmp_path):
    assert load_documents(tmp_path) == []


def test_split_documents_trocea_un_documento_largo():
    texto_largo = "Política de reparto. " * 200  # bastante más que CHUNK_SIZE
    documento = Document(page_content=texto_largo)

    chunks = split_documents([documento])

    assert len(chunks) > 1
    assert all(isinstance(c, Document) for c in chunks)


# ---------------------------------------------------------------------
# Unitarios: cableado de la cadena RAG con retriever/llm falsos. Sin red,
# sin API key - verifican que el contexto recuperado y la pregunta llegan
# de verdad al prompt, y que la salida del LLM llega intacta al resultado.
# ---------------------------------------------------------------------


def test_build_chain_pasa_contexto_y_pregunta_al_prompt():
    capturado = {}

    def fake_retriever_fn(query: str) -> list[Document]:
        capturado["query"] = query
        return [Document(page_content="El restaurante abre de 12:00 a 23:30.")]

    def fake_llm_fn(prompt_value) -> str:
        capturado["prompt_text"] = prompt_value.to_string()
        return "Abrimos de 12:00 a 23:30."

    chain = build_chain(
        retriever=RunnableLambda(fake_retriever_fn),
        llm=RunnableLambda(fake_llm_fn),
    )
    resultado = chain.invoke("¿cuál es el horario?")

    assert resultado == "Abrimos de 12:00 a 23:30."
    assert capturado["query"] == "¿cuál es el horario?"
    assert "12:00 a 23:30" in capturado["prompt_text"]
    assert "cuál es el horario" in capturado["prompt_text"]


def test_build_chain_sin_contexto_relevante_lo_marca_en_el_prompt():
    """Si el retriever no encuentra nada, el prompt debe decir explícitamente
    que no hay contexto - así el LLM tiene la señal para responder "no lo sé"
    en vez de improvisar. (El comportamiento real del LLM ante eso se
    valida aparte, en el test de integración: esto solo prueba el cableado.)"""
    capturado = {}

    def fake_retriever_sin_resultados(query: str) -> list[Document]:
        return []

    def fake_llm_fn(prompt_value) -> str:
        capturado["prompt_text"] = prompt_value.to_string()
        return "No tengo esa información."

    chain = build_chain(
        retriever=RunnableLambda(fake_retriever_sin_resultados),
        llm=RunnableLambda(fake_llm_fn),
    )
    resultado = chain.invoke("¿tenéis wifi gratis?")

    assert resultado == "No tengo esa información."
    assert "sin contexto relevante encontrado" in capturado["prompt_text"]


# ---------------------------------------------------------------------
# Integración: ingesta real + Chroma real + Gemini real (embeddings y LLM).
# Se salta automáticamente si no hay GEMINI_API_KEY configurada (igual que
# el resto del proyecto no dispara llamadas reales sin credenciales) - usa
# un corpus mínimo y controlado en un directorio temporal, no rag_docs/ real.
# ---------------------------------------------------------------------

_motivo_skip = "Test de integración: necesita GEMINI_API_KEY real (embeddings + LLM de Gemini)."
_requiere_gemini = pytest.mark.skipif(not settings.gemini_api_key, reason=_motivo_skip)


@_requiere_gemini
def test_responder_faq_dice_que_no_sabe_fuera_de_contexto(tmp_path):
    (tmp_path / "politicas.txt").write_text(
        "El restaurante abre de 12:00 a 23:30 todos los días. "
        "Aceptamos efectivo, tarjeta y Bizum como métodos de pago.",
        encoding="utf-8",
    )
    vectorstore = ingest(docs_dir=tmp_path, persist_dir=tmp_path / ".chroma-test")
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    respuesta = build_chain(retriever=retriever).invoke(
        "¿Tenéis wifi gratis y aparcamiento para motos?"
    ).lower()

    marcadores_no_lo_se = ("no teng", "no dispongo", "no sé", "no se ", "recomiendo llamar")
    assert any(marcador in respuesta for marcador in marcadores_no_lo_se), (
        f"Se esperaba que el bot admitiera no tener esa información, respondió: {respuesta!r}"
    )


@_requiere_gemini
def test_responder_faq_responde_con_el_dato_real_si_esta_en_contexto(tmp_path):
    (tmp_path / "politicas.txt").write_text(
        "El restaurante abre de 12:00 a 23:30 todos los días. "
        "Aceptamos efectivo, tarjeta y Bizum como métodos de pago.",
        encoding="utf-8",
    )
    vectorstore = ingest(docs_dir=tmp_path, persist_dir=tmp_path / ".chroma-test-2")
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    respuesta = build_chain(retriever=retriever).invoke("¿A qué hora cerráis?").lower()

    assert "23:30" in respuesta
