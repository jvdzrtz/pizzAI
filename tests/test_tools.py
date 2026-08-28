from pizzeria_bot.agents.tools import ToolRouter


def test_flujo_completo_via_tool_router():
    router = ToolRouter()

    r1 = router.call("consultar_menu", {})
    assert r1["ok"] is True
    assert "pepperoni" in r1["menu"]

    r2 = router.call("anadir_item_pedido", {"pizza": "pepperoni", "tamano": "mediana"})
    assert r2["ok"] is True
    assert r2["total_actual"] == 10.0

    r3 = router.call(
        "fijar_datos_entrega", {"direccion": "Av. Ciencias 35", "telefono": "600111222"}
    )
    assert r3["ok"] is True

    r4 = router.call("confirmar_pedido", {})
    assert r4["ok"] is True
    assert r4["resumen"]["total"] == 10.0


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
