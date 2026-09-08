"""
Agente de gestión de incidencias/quejas sobre un PEDIDO ANTERIOR (llegó
tarde, frío, incompleto, cobro incorrecto...), implementado como grafo
LangGraph con dos agentes LLM reales que se pasan trabajo entre sí:

1. Agente FAQ (nodo `consultar_politica`): un wrapper fino sobre
   `rag.faq_chain.responder_faq()`, YA EXISTENTE - no se reimplementa RAG
   aquí, solo se reutiliza tal cual. Por debajo, responder_faq() ya hace
   una llamada real (retrieval + LLM), así que este nodo cuenta como el
   "segundo agente real" sin necesitar su propia llamada a un LLM aparte.
2. Agente de Quejas (nodo `clasificar_gravedad`): un ChatGoogleGenerativeAI
   que recibe la queja Y la política real (del nodo 1) y clasifica la
   gravedad ("menor"/"grave") con structured output - la política real
   manda, nunca un umbral fijo escrito en el prompt.

Caso de uso EXCLUSIVO: el cliente llama para reportar un problema con un
pedido anterior. Esta llamada nunca toma un pedido nuevo - eso lo sigue
haciendo agents/tools.py + domain/order.py, sin tocar ni un carácter.

Módulo nuevo y aislado, testeable sin llamadas reales (ver
tests/test_complaint_graph.py): tanto responder_faq como el LLM
clasificador son inyectables en build_graph(), mismo patrón que
rag/faq_chain.py usa en build_chain(retriever, llm).

Nota de diseño: este grafo NO tiene (ni necesita) un nodo "supervisor"
que decida si una llamada es una queja o un pedido normal - eso ya lo
hace el propio agente de voz (Gemini Live) como router vía function
calling: es él quien decide, turno a turno, si llama a gestionar_queja
o a una de las tools de pedido normal (agents/tools.py). Añadir un
supervisor aquí sería duplicar ese enrutado. Es una decisión de diseño
explícita, no un nodo que falte.
"""

import logging
import uuid
from collections.abc import Callable
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from pizzeria_bot.config import settings

logger = logging.getLogger(__name__)

# Mismo modelo que rag/faq_chain.py: "gemini-2.5-flash" (el recomendado
# por la documentación de LangChain) devuelve 404 en la práctica.
CHAT_MODEL = "gemini-3.6-flash"


class ClasificacionQueja(BaseModel):
    """Structured output del Agente de Quejas (nodo clasificar_gravedad)."""

    gravedad: Literal["menor", "grave"]
    tipo_incidencia: str = Field(
        description="Tipo de problema en pocas palabras, ej. 'retraso en la entrega', "
        "'pedido frío', 'pedido incompleto', 'cobro incorrecto'."
    )
    justificacion: str = Field(description="Por qué, citando la política real consultada.")
    compensacion_sugerida: str | None = Field(
        default=None,
        description="Solo si gravedad='menor' y la política prevé alguna compensación.",
    )


class Incidencia(BaseModel):
    """Una queja escalada a revisión humana. Solo los datos que de verdad
    hacen falta para que un humano la revise - nombre, pedido, tipo de
    incidencia y qué se decidió, nada de texto libre. Nombre y pedido son
    obligatorios (ver gestionar_queja): se piden como parámetros
    explícitos y validados, igual que domain/order.py exige nombre/
    dirección/teléfono antes de confirmar_pedido - no algo que un LLM
    "intente extraer" de texto libre y pueda pasar por alto. En memoria a
    propósito - igual que Order vive en memoria hoy (ver domain/order.py
    y su Roadmap): no hay base de datos real todavía, eso es un bloque
    aparte."""

    id: str
    nombre_cliente: str
    pedido: str
    tipo_incidencia: str
    decision_tomada: str
    estado: Literal["pendiente_revision"] = "pendiente_revision"


class EstadoQueja(TypedDict, total=False):
    descripcion: str
    nombre_cliente: str
    pedido: str
    # Descripciones de otras incidencias ya gestionadas en esta misma
    # llamada (ver gestionar_queja) - el agente de voz a veces las
    # menciona de pasada en la descripción de la incidencia nueva ("además
    # del cobro ya reportado"), y eso confundía al clasificador mezclando
    # la gravedad de dos problemas distintos en una sola decisión. Se le
    # pasan aquí explícitamente para que las excluya del análisis, en vez
    # de depender de que el agente de voz redacte una descripción
    # perfectamente aislada (poco fiable en la práctica).
    descripciones_previas: list[str]
    politica: str
    gravedad: Literal["menor", "grave"]
    tipo_incidencia: str
    justificacion: str
    compensacion_sugerida: str | None
    resultado: dict


# Incidencias graves escaladas, en memoria (un solo proceso, se pierden al
# reiniciar - mismo trade-off que kitchen/store.py). listar_incidencias_
# pendientes() la consume server.py (GET /incidencias/pendientes) para el
# panel de la pantalla de cocina (kitchen/front/) - por polling, no
# WebSocket: gestionar_queja corre en un hilo aparte (ver main.py:
# _TOOLS_LENTAS), así que un push en vivo desde ahí cruzaría threads sin
# necesidad real, no es un feed de alta frecuencia.
_incidencias_pendientes: list[Incidencia] = []


def listar_incidencias_pendientes() -> list[dict]:
    """Incidencias graves escaladas y aún sin revisar por un humano."""
    return [incidencia.model_dump() for incidencia in _incidencias_pendientes]


# Heurística determinista para traducir la queja del cliente en una
# pregunta concreta al Agente FAQ. No hace falta un LLM para este paso -
# el propio responder_faq() ya es la llamada real de este nodo.
_PALABRAS_CLAVE_POLITICA: list[tuple[tuple[str, ...], str]] = [
    (("tarde", "retraso", "demora", "demoró", "tardó", "tardo"), "por retraso en la entrega"),
    (("frío", "fria", "frio", "helad"), "por un pedido que llega frío"),
    (("incompleto", "falta", "faltó", "faltan"), "por un pedido incompleto"),
    (("cobro", "cargo", "factura", "cobrar", "cobrado"), "por un cobro incorrecto"),
]


def _pregunta_politica_desde_queja(descripcion: str) -> str:
    texto = descripcion.lower()
    for palabras, motivo in _PALABRAS_CLAVE_POLITICA:
        if any(palabra in texto for palabra in palabras):
            return f"¿Cuál es la política de compensación {motivo}?"
    return "¿Cuál es la política de compensación para incidencias con pedidos?"


def build_graph(
    responder_faq_fn: Callable[[str], str] | None = None,
    llm: Runnable | None = None,
) -> Runnable:
    """Construye el grafo compilado. responder_faq_fn y llm son
    inyectables a propósito: los tests los sustituyen por dobles
    deterministas para no depender de una API key real ni de llamadas de
    verdad a Gemini (ver rag/faq_chain.build_chain para el mismo patrón)."""
    if responder_faq_fn is None:
        # Import perezoso: así importar agents/complaint_graph.py (y por
        # tanto agents/tools.py, que lo usa) no obliga a tener instalado
        # el extra "rag" (LangChain/Chroma) salvo que de verdad se invoque
        # esta tool - igual que responder_faq() ya hace su propio import
        # perezoso equivalente en tools.py, ver más abajo.
        from pizzeria_bot.rag.faq_chain import responder_faq

        responder_faq_fn = responder_faq

    clasificador = llm or _build_clasificador()

    def consultar_politica(state: EstadoQueja) -> dict:
        pregunta = _pregunta_politica_desde_queja(state["descripcion"])
        politica = responder_faq_fn(pregunta)
        return {"politica": politica}

    def clasificar_gravedad(state: EstadoQueja) -> dict:
        descripciones_previas = state.get("descripciones_previas") or []
        aviso_previas = ""
        if descripciones_previas:
            lista = "\n".join(f"- {d}" for d in descripciones_previas)
            aviso_previas = (
                "\n\nEn esta misma llamada ya se han gestionado y resuelto, por separado, "
                f"estas otras incidencias (no las que clasificas ahora):\n{lista}\n"
                "La queja de abajo puede mencionarlas de pasada (p.ej. \"además del cobro ya "
                "reportado\") - IGNORA POR COMPLETO esas menciones. Clasifica la gravedad y "
                "decide la compensación ÚNICAMENTE en base al problema NUEVO, como si esas "
                "incidencias anteriores no existieran."
            )
        mensajes = [
            SystemMessage(
                content=(
                    "Eres el agente de gestión de incidencias de una pizzería. "
                    "Clasifica la queja del cliente como 'menor' o 'grave' aplicando "
                    "ÚNICAMENTE la política real que se te da como contexto - nunca "
                    "un criterio propio ni un umbral inventado. Si esa política prevé "
                    "una compensación para una incidencia como esta, indícala en "
                    "compensacion_sugerida; si la política no menciona ninguna "
                    "compensación, o la incidencia es grave, deja ese campo en null. "
                    "Resume también el tipo de incidencia en pocas palabras "
                    "(tipo_incidencia)." + aviso_previas
                )
            ),
            HumanMessage(
                content=(
                    f"QUEJA DEL CLIENTE:\n{state['descripcion']}\n\n"
                    f"POLÍTICA APLICABLE (según el restaurante):\n{state['politica']}"
                )
            ),
        ]
        clasificacion: ClasificacionQueja = clasificador.invoke(mensajes)
        return {
            "gravedad": clasificacion.gravedad,
            "tipo_incidencia": clasificacion.tipo_incidencia,
            "justificacion": clasificacion.justificacion,
            "compensacion_sugerida": clasificacion.compensacion_sugerida,
        }

    def resolver_automaticamente(state: EstadoQueja) -> dict:
        # compensacion_sugerida es None cuando la política real no prevé
        # ninguna compensación para este caso (ej. un retraso que no llega
        # al umbral que exige la política) - eso es una respuesta legítima,
        # NO una ausencia de dato que rellenar. Antes se caía a un mensaje
        # genérico ("una disculpa y prioridad") con un código de verdad,
        # lo que en la práctica inventaba una compensación que la política
        # nunca ofreció - justo lo que la tarea prohíbe explícitamente.
        compensacion = state.get("compensacion_sugerida")
        if compensacion:
            codigo = uuid.uuid4().hex[:6].upper()
            mensaje = (
                f"Lamentamos mucho lo ocurrido. Como compensación te ofrecemos {compensacion}. "
                f"Tu código es {codigo}, consérvalo para tu próximo pedido."
            )
        else:
            codigo = None
            mensaje = (
                "Lamentamos mucho lo ocurrido. Según nuestra política, este caso no tiene "
                "una compensación asociada, pero hemos tomado nota para mejorar."
            )
        return {
            "resultado": {
                "resuelto": True,
                "mensaje_para_cliente": mensaje,
                "detalle_interno": {
                    "gravedad": "menor",
                    "justificacion": state["justificacion"],
                    "politica_aplicada": state["politica"],
                    "codigo_compensacion": codigo,
                    "compensacion": compensacion,
                },
            }
        }

    def escalar_a_humano(state: EstadoQueja) -> dict:
        incidencia = Incidencia(
            id=str(uuid.uuid4()),
            nombre_cliente=state["nombre_cliente"],
            pedido=state["pedido"],
            tipo_incidencia=state["tipo_incidencia"],
            decision_tomada="Derivada a revisión humana, sin compensación automática.",
        )
        _incidencias_pendientes.append(incidencia)
        logger.info("Incidencia escalada a revisión humana: %s", incidencia.id)
        mensaje = (
            "Sentimos mucho lo ocurrido. Hemos registrado la incidencia y nuestro "
            "equipo se pondrá en contacto contigo lo antes posible para resolverlo."
        )
        return {
            "resultado": {
                "resuelto": False,
                "mensaje_para_cliente": mensaje,
                "detalle_interno": incidencia.model_dump(),
            }
        }

    def _rama_por_gravedad(state: EstadoQueja) -> str:
        return "menor" if state["gravedad"] == "menor" else "grave"

    grafo = StateGraph(EstadoQueja)
    grafo.add_node("consultar_politica", consultar_politica)
    grafo.add_node("clasificar_gravedad", clasificar_gravedad)
    grafo.add_node("resolver_automaticamente", resolver_automaticamente)
    grafo.add_node("escalar_a_humano", escalar_a_humano)

    grafo.add_edge(START, "consultar_politica")
    grafo.add_edge("consultar_politica", "clasificar_gravedad")
    grafo.add_conditional_edges(
        "clasificar_gravedad",
        _rama_por_gravedad,
        {"menor": "resolver_automaticamente", "grave": "escalar_a_humano"},
    )
    grafo.add_edge("resolver_automaticamente", END)
    grafo.add_edge("escalar_a_humano", END)

    return grafo.compile()


def _build_clasificador() -> Runnable:
    # Import perezoso por el mismo motivo que responder_faq_fn arriba:
    # no forzar el extra "rag" solo por importar este módulo.
    from langchain_google_genai import ChatGoogleGenerativeAI

    # google_api_key explícito: pydantic-settings no exporta .env a
    # os.environ, y esta librería solo mira el entorno por defecto (mismo
    # motivo documentado en rag/faq_chain.py e ingest.py).
    llm = ChatGoogleGenerativeAI(
        model=CHAT_MODEL, temperature=0, google_api_key=settings.gemini_api_key
    )
    return llm.with_structured_output(ClasificacionQueja)


def gestionar_queja(
    descripcion: str,
    nombre_cliente: str,
    pedido: str,
    descripciones_previas: list[str] | None = None,
) -> dict:
    """Punto de entrada público: gestiona de principio a fin una queja
    sobre un pedido anterior (consulta la política real → clasifica
    gravedad → resuelve automáticamente o escala a un humano) y devuelve
    el resultado listo para que el agente de voz se lo diga al cliente.

    nombre_cliente y pedido son obligatorios y se pasan tal cual (no se
    intentan adivinar del texto de descripcion) - la validación de que no
    vengan vacíos vive en agents/tools.py, igual que la validación de los
    datos del pedido normal vive en domain/order.py.

    descripciones_previas: descripciones de otras incidencias YA
    gestionadas en la misma llamada (ver agents/tools.py:
    ToolRouter._gestionar_queja) - se le pasan al clasificador para que
    ignore cualquier mención de pasada a ellas en la descripción actual,
    en vez de depender de que el agente de voz redacte una descripción
    perfectamente aislada del problema nuevo.

    Devuelve {"resuelto": bool, "mensaje_para_cliente": str,
    "detalle_interno": {...}}.
    """
    grafo = build_graph()
    estado_final = grafo.invoke(
        {
            "descripcion": descripcion,
            "nombre_cliente": nombre_cliente,
            "pedido": pedido,
            "descripciones_previas": descripciones_previas or [],
        }
    )
    return estado_final["resultado"]
