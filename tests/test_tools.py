from pizzeria_bot.agents.tools import ToolRouter


def test_flujo_completo_via_tool_router():
    router = ToolRouter()

    r1 = router.call("consultar_menu", {})
    assert r1["ok"] is True
    assert "pepperoni" in r1["menu"]

    r2 = router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    assert r2["ok"] is True
    assert r2["total_actual"] == 10.0

    r3 = router.call("fijar_tipo_entrega", {"tipo": "domicilio"})
    assert r3["ok"] is True

    r4 = router.call(
        "fijar_datos_cliente",
        {"nombre": "Ana", "direccion": "Av. Ciencias 35", "telefono": "600111222"},
    )
    assert r4["ok"] is True

    r5 = router.call("confirmar_pedido", {})
    assert r5["ok"] is True
    assert r5["resumen"]["total"] == 10.0


def test_tool_desconocida_no_rompe_la_sesion():
    router = ToolRouter()
    result = router.call("tool_que_no_existe", {})
    assert result["ok"] is False


def test_confirmar_sin_datos_devuelve_error_controlado():
    router = ToolRouter()
    result = router.call("confirmar_pedido", {})
    assert result["ok"] is False
    assert "error" in result


def test_anadir_item_sin_tamano_devuelve_error_controlado():
    # Ej: el cliente dice "pizza pepperoni" sin tamaño y el modelo llama a la
    # tool sin ese argumento. No debe reventar el ToolRouter (ni la sesión).
    router = ToolRouter()
    result = router.call("anadir_item_pedido", {"pizza": "pepperoni"})
    assert result["ok"] is False
    assert "error" in result


def test_quitar_y_modificar_item_via_tool_router():
    router = ToolRouter()
    r1 = router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    item_id = r1["item_anadido"]["item_id"]

    r2 = router.call(
        "modificar_item_pedido", {"item_id": item_id, "tamano": "familiar", "cantidad": 2}
    )
    assert r2["ok"] is True
    assert r2["item_modificado"]["subtotal"] == 26.0  # pepperoni familiar (13.0) x2

    r3 = router.call("consultar_pedido_actual", {})
    assert r3["ok"] is True
    assert len(r3["items"]) == 1
    assert r3["total"] == 26.0

    r4 = router.call("quitar_item_pedido", {"item_id": item_id})
    assert r4["ok"] is True
    assert r4["total_actual"] == 0.0

    r5 = router.call("consultar_pedido_actual", {})
    assert r5["items"] == []


def test_quitar_item_inexistente_devuelve_error_controlado():
    router = ToolRouter()
    result = router.call("quitar_item_pedido", {"item_id": 999})
    assert result["ok"] is False
    assert "error" in result


def test_fijar_datos_cliente_por_separado_no_pierde_datos():
    # Reproduce el caso real: el cliente da la dirección, la llamada se
    # corta antes de dar el teléfono -> la dirección debe seguir guardada.
    router = ToolRouter()
    r1 = router.call("fijar_datos_cliente", {"direccion": "Calle C, 2"})
    assert r1["ok"] is True
    assert r1["direccion"] == "Calle C, 2"
    assert r1["telefono"] is None

    r2 = router.call("fijar_datos_cliente", {"telefono": "600111222"})
    assert r2["ok"] is True
    assert r2["direccion"] == "Calle C, 2"
    assert r2["telefono"] == "600111222"


def test_fijar_tipo_entrega_via_tool_router():
    router = ToolRouter()
    result = router.call("fijar_tipo_entrega", {"tipo": "recogida"})
    assert result["ok"] is True
    assert result["tipo_entrega"] == "recogida"


def test_fijar_tipo_entrega_invalido_devuelve_error_controlado():
    router = ToolRouter()
    result = router.call("fijar_tipo_entrega", {"tipo": "en globo"})
    assert result["ok"] is False


def test_confirmar_pedido_recogida_via_tool_router():
    router = ToolRouter()
    router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    router.call("fijar_tipo_entrega", {"tipo": "recogida"})
    router.call("fijar_datos_cliente", {"nombre": "Ana", "telefono": "600111222"})
    result = router.call("confirmar_pedido", {})
    assert result["ok"] is True
    assert result["resumen"]["nombre_cliente"] == "Ana"


def test_no_se_puede_modificar_tras_confirmar_via_tool_router():
    router = ToolRouter()
    router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    router.call("fijar_tipo_entrega", {"tipo": "recogida"})
    router.call("fijar_datos_cliente", {"nombre": "Ana", "telefono": "600111222"})
    router.call("confirmar_pedido", {})

    result = router.call("anadir_item_pedido", {"pizza": "margarita", "tamano": "mediana"})
    assert result["ok"] is False


def test_finalizar_llamada_marca_debe_colgar():
    router = ToolRouter()
    assert router.debe_colgar is False
    result = router.call("finalizar_llamada", {})
    assert result["ok"] is True
    assert router.debe_colgar is True


def test_finalizar_llamada_rechazada_con_incidencia_en_curso():
    # Bug real visto en producción: el modelo llamaba a
    # avisar_espera_incidencia y, en vez de seguir con gestionar_queja, se
    # despedía y colgaba directamente - la incidencia se quedaba a medias
    # para siempre (nunca se consultó la política real, nunca hubo
    # compensación que ofrecer). No se puede colgar con una incidencia
    # avisada pero sin resolver.
    router = ToolRouter()
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})

    result = router.call("finalizar_llamada", {})

    assert result["ok"] is False
    assert router.debe_colgar is False


def test_avisar_espera_incidencia_es_instantanea_y_no_toca_nada():
    # Primer paso del flujo de queja: instantánea, sin red, sin marcar
    # nada_pendiente (eso lo hace gestionar_queja, el segundo paso real).
    router = ToolRouter()
    result = router.call(
        "avisar_espera_incidencia", {"nombre_cliente": "Ana", "pedido": "1 margarita"}
    )

    assert result["ok"] is True
    assert "mensaje_para_cliente" in result
    assert router.nada_pendiente is False


def test_avisar_espera_incidencia_sin_nombre_o_pedido_falla_controlado():
    # nombre_cliente y pedido son obligatorios de verdad: si el modelo
    # llama a la tool sin haberlos preguntado antes, debe recibir un error
    # que pueda leer y corregir, no un fallo silencioso ni una incidencia
    # a medias.
    router = ToolRouter()

    sin_nombre = router.call("avisar_espera_incidencia", {"nombre_cliente": "", "pedido": "1 margarita"})
    assert sin_nombre["ok"] is False

    sin_pedido = router.call("avisar_espera_incidencia", {"nombre_cliente": "Ana", "pedido": ""})
    assert sin_pedido["ok"] is False


def test_avisar_espera_incidencia_rechaza_valores_de_relleno():
    # Bug real visto en producción: el cliente nunca dio su nombre y el
    # modelo, en vez de volver a preguntarlo, lo rellenó con un
    # placeholder tipo "[Nombre del cliente]" - no vacío, así que la
    # validación de "obligatorio y no vacío" por sí sola no lo pillaba.
    router = ToolRouter()
    result = router.call(
        "avisar_espera_incidencia",
        {"nombre_cliente": "[Nombre del cliente]", "pedido": "1 margarita"},
    )
    assert result["ok"] is False


def test_gestionar_queja_marca_queja_en_curso_mientras_no_se_resuelve(monkeypatch):
    # Un cliente puede reportar una SEGUNDA incidencia distinta en la
    # misma llamada. Mientras esa segunda se está gestionando (entre
    # avisar_espera_incidencia y que gestionar_queja termine),
    # nada_pendiente debe volver a false - si no, el watchdog empuja a
    # colgar con los tiempos cortos mientras la incidencia sigue en curso
    # de verdad (bug real: se interrumpía justo antes de contar la
    # resolución de la segunda incidencia).
    from pizzeria_bot.agents import complaint_graph

    monkeypatch.setattr(
        complaint_graph,
        "gestionar_queja",
        lambda descripcion, nombre_cliente, pedido, descripciones_previas=None: {
            "resuelto": True,
            "mensaje_para_cliente": "x",
            "detalle_interno": {},
        },
    )

    router = ToolRouter()

    # Primera incidencia: se resuelve, nada_pendiente pasa a true.
    router.call(
        "avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"}
    )
    router.call(
        "gestionar_queja",
        {"descripcion": "cobro incorrecto", "nombre_cliente": "Javi", "pedido": "1 pepperoni"},
    )
    assert router.nada_pendiente is True

    # Segunda incidencia (mismo pedido): en cuanto arranca, nada_pendiente
    # debe volver a false mientras se gestiona de verdad.
    router.call(
        "avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"}
    )
    assert router.nada_pendiente is False

    router.call(
        "gestionar_queja",
        {"descripcion": "llegó fría", "nombre_cliente": "Javi", "pedido": "1 pepperoni"},
    )
    assert router.nada_pendiente is True


def test_confirmar_pedido_marca_nada_pendiente():
    # nada_pendiente es lo que usa main.py (_idle_watchdog) para saber si
    # empujar al modelo a colgar rápido en vez de preguntar "¿sigues ahí?"
    # con los tiempos largos de una llamada aún en curso.
    router = ToolRouter()
    assert router.nada_pendiente is False

    router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    router.call("fijar_tipo_entrega", {"tipo": "recogida"})
    router.call("fijar_datos_cliente", {"nombre": "Ana", "telefono": "600111222"})
    router.call("confirmar_pedido", {})

    assert router.nada_pendiente is True


def test_gestionar_queja_marca_nada_pendiente(monkeypatch):
    # Reproduce un bug real visto en llamadas de verdad: tras gestionar una
    # queja, el watchdog seguía tratando la llamada como "en curso" (mismos
    # tiempos largos que un pedido a medias) y acababa preguntando "¿sigues
    # ahí?" de la nada aunque el modelo ya se hubiera despedido.
    from pizzeria_bot.agents import complaint_graph

    monkeypatch.setattr(
        complaint_graph,
        "gestionar_queja",
        lambda descripcion, nombre_cliente, pedido, descripciones_previas=None: {
            "resuelto": True,
            "mensaje_para_cliente": "mensaje de prueba",
            "detalle_interno": {},
        },
    )

    router = ToolRouter()
    assert router.nada_pendiente is False

    result = router.call(
        "gestionar_queja",
        {"descripcion": "el pedido llegó tarde", "nombre_cliente": "Ana", "pedido": "1 margarita"},
    )

    assert result["ok"] is True
    assert router.nada_pendiente is True


def test_gestionar_queja_sin_nombre_o_pedido_falla_controlado():
    router = ToolRouter()
    result = router.call(
        "gestionar_queja", {"descripcion": "cobro incorrecto", "nombre_cliente": "", "pedido": ""}
    )

    assert result["ok"] is False
    assert router.nada_pendiente is False


def test_gestionar_queja_repetida_tal_cual_no_duplica_la_incidencia(monkeypatch):
    # Bug real visto en llamadas de verdad: el modelo llamaba a
    # gestionar_queja dos veces seguidas con la MISMA descripción exacta
    # (p.ej. dudando si la primera "coló"). La segunda llamada no debe
    # invocar el grafo otra vez ni crear una segunda incidencia - y
    # tampoco debe llevar mensaje_para_cliente, para que el modelo no
    # vuelva a narrar el mismo "lamentamos mucho lo ocurrido..." una
    # segunda vez (bug real: se repetía la resolución completa dos veces).
    from pizzeria_bot.agents import complaint_graph

    llamadas = []

    def _fake_gestionar_queja(descripcion: str, nombre_cliente: str, pedido: str, descripciones_previas=None) -> dict:
        llamadas.append(descripcion)
        return {
            "resuelto": True,
            "mensaje_para_cliente": f"resultado para: {descripcion}",
            "detalle_interno": {},
        }

    monkeypatch.setattr(complaint_graph, "gestionar_queja", _fake_gestionar_queja)

    router = ToolRouter()
    args = {"descripcion": "cobro de 30€ de más", "nombre_cliente": "Jaime", "pedido": "1 margarita"}
    r1 = router.call("gestionar_queja", args)
    r2 = router.call("gestionar_queja", dict(args))

    assert len(llamadas) == 1  # el grafo solo se invocó una vez
    assert "mensaje_para_cliente" in r1
    assert "mensaje_para_cliente" not in r2  # no repite la resolución
    assert r2["ok"] is True
    assert "no lo repitas" in r2["aviso"].lower()


def test_gestionar_queja_dos_incidencias_distintas_con_su_propio_aviso_se_registran_las_dos(
    monkeypatch,
):
    # Bug real visto en llamadas de verdad: un cliente reportó el cobro
    # incorrecto Y, más tarde en la misma llamada, que la pizza había
    # llegado fría - la segunda queja se perdía silenciosamente, o se
    # duplicaba la primera con una descripción reformulada. El flujo
    # correcto es un avisar_espera_incidencia nuevo por cada incidencia -
    # eso es lo que distingue "incidencia nueva" de "reintento de la
    # misma", no el texto de la descripción (frágil: dos formas de
    # describir LO MISMO no coinciden tal cual, y dos incidencias
    # DISTINTAS sobre el mismo pedido comparten casi todo el contexto).
    from pizzeria_bot.agents import complaint_graph

    llamadas = []

    def _fake_gestionar_queja(descripcion: str, nombre_cliente: str, pedido: str, descripciones_previas=None) -> dict:
        llamadas.append(descripcion)
        return {
            "resuelto": True,
            "mensaje_para_cliente": f"resultado para: {descripcion}",
            "detalle_interno": {"descripcion": descripcion},
        }

    monkeypatch.setattr(complaint_graph, "gestionar_queja", _fake_gestionar_queja)

    router = ToolRouter()
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})
    r1 = router.call(
        "gestionar_queja",
        {"descripcion": "cobro de 30€ de más", "nombre_cliente": "Javi", "pedido": "1 pepperoni"},
    )
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})
    r2 = router.call(
        "gestionar_queja",
        {"descripcion": "la pizza llegó fría", "nombre_cliente": "Javi", "pedido": "1 pepperoni"},
    )

    assert len(llamadas) == 2  # las dos quejas invocaron el grafo de verdad
    assert r1 != r2
    assert r1["detalle_interno"]["descripcion"] == "cobro de 30€ de más"
    assert r2["detalle_interno"]["descripcion"] == "la pizza llegó fría"


def test_gestionar_queja_pasa_las_descripciones_previas_al_clasificador(monkeypatch):
    # Bug real visto en producción: el agente de voz mezclaba el problema
    # ya resuelto en la descripción de la incidencia nueva ("llegó fría,
    # además del cobro incorrecto ya reportado"), y el clasificador
    # combinaba la gravedad de ambos problemas en una sola decisión (sin
    # compensación). ToolRouter debe pasarle al grafo la lista de
    # descripciones YA gestionadas en la llamada, para que el clasificador
    # las excluya explícitamente en vez de depender de que la descripción
    # llegue perfectamente aislada.
    from pizzeria_bot.agents import complaint_graph

    previas_recibidas = []

    def _fake_gestionar_queja(descripcion, nombre_cliente, pedido, descripciones_previas=None):
        previas_recibidas.append(list(descripciones_previas or []))
        return {"resuelto": True, "mensaje_para_cliente": "x", "detalle_interno": {}}

    monkeypatch.setattr(complaint_graph, "gestionar_queja", _fake_gestionar_queja)

    router = ToolRouter()
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})
    router.call(
        "gestionar_queja",
        {"descripcion": "cobro de 30€ de más", "nombre_cliente": "Javi", "pedido": "1 pepperoni"},
    )
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})
    router.call(
        "gestionar_queja",
        {
            "descripcion": "la pizza llegó fría, además del cobro ya reportado",
            "nombre_cliente": "Javi",
            "pedido": "1 pepperoni",
        },
    )

    assert previas_recibidas[0] == []  # la primera no tiene nada previo
    assert previas_recibidas[1] == ["cobro de 30€ de más"]  # la segunda sí


def test_gestionar_queja_sin_aviso_nuevo_reutiliza_la_ultima_resolucion(monkeypatch):
    # Reintento redundante: el modelo llama a gestionar_queja otra vez
    # (reformulando la descripción) sin que haya habido un
    # avisar_espera_incidencia nuevo de por medio - eso significa que es
    # la MISMA incidencia ya resuelta, así que se devuelve lo mismo de
    # antes en vez de crear una segunda incidencia (bug real: la misma
    # incidencia registrándose dos veces, con la descripción reformulada).
    from pizzeria_bot.agents import complaint_graph

    llamadas = []

    def _fake_gestionar_queja(descripcion: str, nombre_cliente: str, pedido: str, descripciones_previas=None) -> dict:
        llamadas.append(descripcion)
        return {
            "resuelto": True,
            "mensaje_para_cliente": f"resultado para: {descripcion}",
            "detalle_interno": {"descripcion": descripcion},
        }

    monkeypatch.setattr(complaint_graph, "gestionar_queja", _fake_gestionar_queja)

    router = ToolRouter()
    router.call("avisar_espera_incidencia", {"nombre_cliente": "Javi", "pedido": "1 pepperoni"})
    r1 = router.call(
        "gestionar_queja",
        {
            "descripcion": "le cobraron 50€ de más en su margarita",
            "nombre_cliente": "Javi",
            "pedido": "1 pepperoni",
        },
    )
    # Reformulado, sin avisar_espera_incidencia de por medio - es un
    # reintento de lo mismo, no una incidencia nueva.
    r2 = router.call(
        "gestionar_queja",
        {
            "descripcion": "le cobraron 50€ de más del total",
            "nombre_cliente": "Javi",
            "pedido": "1 pepperoni",
        },
    )

    assert len(llamadas) == 1  # el grafo solo se invocó una vez
    assert "mensaje_para_cliente" in r1
    assert "mensaje_para_cliente" not in r2  # no repite la resolución
