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
