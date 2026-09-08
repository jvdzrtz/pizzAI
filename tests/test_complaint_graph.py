"""
Tests del grafo de gestión de incidencias/quejas (agents/complaint_graph.py).

Igual que tests/test_rag.py con build_chain, se testea a través de
build_graph(responder_faq_fn, llm) en vez de la función pública
gestionar_queja() - así se pueden inyectar dobles deterministas y no
depender de una API key real ni de llamadas de verdad a Gemini.
"""

from langchain_core.runnables import RunnableLambda

from pizzeria_bot.agents.complaint_graph import (
    ClasificacionQueja,
    build_graph,
    listar_incidencias_pendientes,
)


def _fake_responder_faq(politica: str):
    def _fn(pregunta: str) -> str:
        return politica

    return _fn


def test_queja_menor_resuelve_con_compensacion_segun_la_politica_real():
    responder_faq_fn = _fake_responder_faq(
        "Si un pedido llega más de 15 minutos tarde, ofrecemos un 10% de "
        "descuento en el próximo pedido."
    )
    llm = RunnableLambda(
        lambda _mensajes: ClasificacionQueja(
            gravedad="menor",
            tipo_incidencia="retraso en la entrega",
            justificacion="Llegó 20 minutos tarde, la política prevé un 10% de descuento.",
            compensacion_sugerida="10% de descuento en el próximo pedido",
        )
    )
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    resultado = grafo.invoke(
        {"descripcion": "Mi pizza llegó 20 minutos tarde", "nombre_cliente": "Ana", "pedido": "1 pepperoni"}
    )["resultado"]

    assert resultado["resuelto"] is True
    assert "10% de descuento" in resultado["mensaje_para_cliente"]
    assert resultado["detalle_interno"]["gravedad"] == "menor"
    assert resultado["detalle_interno"]["codigo_compensacion"]
    # La política consultada de verdad debe llegar hasta el resultado final,
    # no una que el LLM se haya inventado.
    assert "10% de descuento" in resultado["detalle_interno"]["politica_aplicada"]


def test_queja_menor_sin_compensacion_en_la_politica_no_inventa_una():
    # Bug real visto en producción: un retraso de 30 min (la política solo
    # compensa a partir de 45) se clasificaba correctamente como "menor"
    # sin compensacion_sugerida, pero el nodo igualmente fabricaba un
    # código y decía "como compensación te ofrecemos una disculpa y
    # prioridad" - inventando una compensación que la política nunca dio,
    # justo lo que la tarea prohíbe explícitamente.
    responder_faq_fn = _fake_responder_faq(
        "Solo compensamos retrasos superiores a 45 minutos con un 10% de descuento."
    )
    llm = RunnableLambda(
        lambda _mensajes: ClasificacionQueja(
            gravedad="menor",
            tipo_incidencia="retraso en la entrega",
            justificacion="El retraso de 30 minutos no supera el umbral de 45 de la política.",
            compensacion_sugerida=None,
        )
    )
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    resultado = grafo.invoke(
        {
            "descripcion": "El repartidor llegó 30 minutos tarde",
            "nombre_cliente": "Javier",
            "pedido": "1 pepperoni",
        }
    )["resultado"]

    assert resultado["resuelto"] is True
    assert resultado["detalle_interno"]["compensacion"] is None
    assert resultado["detalle_interno"]["codigo_compensacion"] is None
    # No debe fabricar un código de compensación que la política no dio.
    assert "código" not in resultado["mensaje_para_cliente"].lower()


def test_queja_grave_escala_a_humano_y_queda_pendiente_de_revision():
    responder_faq_fn = _fake_responder_faq(
        "Los cobros incorrectos se revisan caso a caso con el responsable del local."
    )
    llm = RunnableLambda(
        lambda _mensajes: ClasificacionQueja(
            gravedad="grave",
            tipo_incidencia="cobro incorrecto",
            justificacion="Cobro incorrecto que requiere revisión manual según la política.",
            compensacion_sugerida=None,
        )
    )
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    resultado = grafo.invoke(
        {
            "descripcion": "Me han cobrado el doble en la tarjeta",
            "nombre_cliente": "Javi",
            "pedido": "1 margarita mediana",
        }
    )["resultado"]

    assert resultado["resuelto"] is False
    assert "equipo" in resultado["mensaje_para_cliente"].lower()
    # La incidencia guardada solo tiene los datos que hacen falta para que
    # un humano la revise: nombre, pedido, tipo de incidencia y decisión.
    detalle = resultado["detalle_interno"]
    assert detalle["nombre_cliente"] == "Javi"
    assert detalle["pedido"] == "1 margarita mediana"
    assert detalle["tipo_incidencia"] == "cobro incorrecto"
    assert detalle["decision_tomada"]
    assert detalle["estado"] == "pendiente_revision"

    incidencia_id = detalle["id"]
    pendientes = listar_incidencias_pendientes()
    assert any(i["id"] == incidencia_id for i in pendientes)
    assert any(i["estado"] == "pendiente_revision" for i in pendientes)


def test_pregunta_al_faq_se_deriva_del_contenido_de_la_queja():
    """El nodo consultar_politica no manda la queja tal cual al FAQ, sino
    una pregunta de política derivada de las palabras clave de la queja."""
    preguntas_recibidas = []

    def responder_faq_fn(pregunta: str) -> str:
        preguntas_recibidas.append(pregunta)
        return "Política de ejemplo."

    llm = RunnableLambda(
        lambda _mensajes: ClasificacionQueja(
            gravedad="menor", tipo_incidencia="retraso y frío", justificacion="ok"
        )
    )
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    grafo.invoke(
        {"descripcion": "La pizza llegó fría y tarde", "nombre_cliente": "Ana", "pedido": "1 margarita"}
    )

    assert len(preguntas_recibidas) == 1
    assert "retraso" in preguntas_recibidas[0] or "frío" in preguntas_recibidas[0]


def test_descripciones_previas_se_le_dicen_al_clasificador_para_que_las_ignore():
    # Bug real visto en producción: el agente de voz mezclaba en la
    # descripción de una incidencia nueva la mención de otra YA resuelta
    # en la misma llamada ("llegó fría, además del cobro ya reportado"),
    # y el clasificador combinaba la gravedad de ambos problemas en una
    # sola decisión (la incidencia nueva salía "grave" sin compensación,
    # cuando aislada habría sido "menor" con descuento). El clasificador
    # debe recibir la lista de incidencias previas explícitamente, con
    # instrucción de ignorarlas.
    responder_faq_fn = _fake_responder_faq("Pedido frío: 10% de descuento.")
    mensajes_capturados = []

    def _fake_llm(mensajes):
        mensajes_capturados.extend(mensajes)
        return ClasificacionQueja(
            gravedad="menor", tipo_incidencia="pedido frío", justificacion="ok"
        )

    llm = RunnableLambda(_fake_llm)
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    grafo.invoke(
        {
            "descripcion": "La pizza llegó fría, además del cobro ya reportado",
            "nombre_cliente": "Javi",
            "pedido": "1 pepperoni",
            "descripciones_previas": ["Le cobraron 30€ de más"],
        }
    )

    contenido_sistema = mensajes_capturados[0].content
    assert "Le cobraron 30€ de más" in contenido_sistema
    assert "ignora" in contenido_sistema.lower() or "IGNORA" in contenido_sistema


def test_sin_descripciones_previas_no_anade_el_aviso_de_ignorar():
    responder_faq_fn = _fake_responder_faq("Política de ejemplo.")
    mensajes_capturados = []

    def _fake_llm(mensajes):
        mensajes_capturados.extend(mensajes)
        return ClasificacionQueja(gravedad="menor", tipo_incidencia="tipo", justificacion="ok")

    llm = RunnableLambda(_fake_llm)
    grafo = build_graph(responder_faq_fn=responder_faq_fn, llm=llm)

    grafo.invoke(
        {"descripcion": "La pizza llegó fría", "nombre_cliente": "Javi", "pedido": "1 pepperoni"}
    )

    assert "IGNORA" not in mensajes_capturados[0].content
