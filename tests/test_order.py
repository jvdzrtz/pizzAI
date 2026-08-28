import pytest

from pizzeria_bot.domain.order import Order, OrderError


def test_anadir_item_calcula_subtotal_correctamente():
    order = Order()
    item = order.anadir_item("pepperoni", "mediana")
    assert item.subtotal == 10.0
    assert order.total == 10.0


def test_anadir_dos_items_suma_el_total():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.anadir_item("margarita", "familiar")
    assert order.total == 10.0 + 11.0


def test_pizza_inexistente_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.anadir_item("hawaiana", "mediana")


def test_anadir_item_tolera_prefijo_pizza():
    # El modelo de voz puede transcribir "pizza pepperoni" en vez de "pepperoni".
    order = Order()
    item = order.anadir_item("pizza pepperoni", "mediana")
    assert item.pizza == "pepperoni"
    assert item.subtotal == 10.0


def test_anadir_item_cantidad_no_positiva_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.anadir_item("pepperoni", "mediana", cantidad=0)


def test_anadir_item_con_cantidad_mayor_a_uno():
    # "ponme dos pepperoni" -> una sola línea con cantidad=2, no dos líneas.
    order = Order()
    item = order.anadir_item("pepperoni", "mediana", cantidad=2)
    assert len(order.items) == 1
    assert item.cantidad == 2
    assert item.subtotal == 20.0
    assert order.total == 20.0


def test_anadir_item_asigna_ids_secuenciales():
    order = Order()
    item1 = order.anadir_item("pepperoni", "mediana")
    item2 = order.anadir_item("margarita", "familiar")
    assert item1.item_id == 1
    assert item2.item_id == 2


def test_quitar_item_lo_elimina_y_actualiza_el_total():
    order = Order()
    item1 = order.anadir_item("pepperoni", "mediana")
    order.anadir_item("margarita", "familiar")
    quitado = order.quitar_item(item1.item_id)
    assert quitado.pizza == "pepperoni"
    assert len(order.items) == 1
    assert order.total == 11.0


def test_quitar_item_id_inexistente_lanza_error():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    with pytest.raises(OrderError):
        order.quitar_item(999)


def test_modificar_item_cambia_tamano_y_recalcula_precio():
    order = Order()
    item = order.anadir_item("pepperoni", "mediana")
    modificado = order.modificar_item(item.item_id, tamano="familiar")
    assert modificado.tamano == "familiar"
    assert modificado.subtotal == 13.0
    assert order.total == 13.0


def test_modificar_item_cambia_pizza_manteniendo_lo_demas():
    order = Order()
    item = order.anadir_item("pepperoni", "mediana", cantidad=2)
    modificado = order.modificar_item(item.item_id, pizza="margarita")
    assert modificado.pizza == "margarita"
    assert modificado.cantidad == 2
    assert modificado.subtotal == 16.0  # margarita mediana (8.0) x2


def test_modificar_item_id_inexistente_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.modificar_item(999, cantidad=2)


def test_fijar_datos_cliente_telefono_invalido_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_cliente(telefono="12345")


def test_fijar_datos_cliente_normaliza_telefono_con_separadores():
    order = Order()
    order.fijar_datos_cliente(telefono="600 111 222")
    assert order.telefono == "600111222"


def test_fijar_datos_cliente_direccion_vacia_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_cliente(direccion="")


def test_fijar_datos_cliente_direccion_sin_sentido_lanza_error():
    # Ej: el cliente responde "sí" o "vale" en vez de dar una dirección real.
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_cliente(direccion="sí")


def test_fijar_datos_cliente_nombre_vacio_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_cliente(nombre=" ")


def test_fijar_datos_cliente_por_separado_no_pierde_datos():
    # Si la llamada se corta a medias, lo ya dado no debe perderse - por eso
    # se puede llamar una vez por cada dato.
    order = Order()
    order.fijar_datos_cliente(nombre="Ana")
    assert order.nombre_cliente == "Ana"
    assert order.telefono is None

    order.fijar_datos_cliente(telefono="600111222")
    assert order.nombre_cliente == "Ana"
    assert order.telefono == "600111222"


def test_fijar_datos_cliente_sin_ningun_dato_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_cliente()


def test_fijar_tipo_entrega_valido():
    order = Order()
    order.fijar_tipo_entrega("domicilio")
    assert order.tipo_entrega == "domicilio"


def test_fijar_tipo_entrega_invalido_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_tipo_entrega("teletransporte")


def test_confirmar_sin_items_falla():
    order = Order()
    order.fijar_tipo_entrega("domicilio")
    order.fijar_datos_cliente(direccion="Calle Falsa 123", telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_sin_tipo_entrega_falla():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_datos_cliente(direccion="Calle Falsa 123", telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_domicilio_sin_direccion_falla():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("domicilio")
    order.fijar_datos_cliente(nombre="Ana", telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_recogida_sin_nombre_falla():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("recogida")
    order.fijar_datos_cliente(telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_domicilio_sin_nombre_falla():
    # El nombre se pide siempre, también en entregas a domicilio.
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("domicilio")
    order.fijar_datos_cliente(direccion="Calle Falsa 123", telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_sin_telefono_falla():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("recogida")
    order.fijar_datos_cliente(nombre="Ana")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_pedido_a_domicilio_funciona():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("domicilio")
    order.fijar_datos_cliente(nombre="Ana", direccion="Calle Falsa 123", telefono="600111222")
    resumen = order.confirmar()
    assert order.confirmado is True
    assert resumen["total"] == 10.0
    assert resumen["direccion"] == "Calle Falsa 123"


def test_confirmar_pedido_recogida_no_necesita_direccion():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("recogida")
    order.fijar_datos_cliente(nombre="Ana", telefono="600111222")
    resumen = order.confirmar()
    assert order.confirmado is True
    assert resumen["nombre_cliente"] == "Ana"
    assert resumen["direccion"] is None


def test_confirmado_bloquea_cualquier_modificacion():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_tipo_entrega("recogida")
    order.fijar_datos_cliente(nombre="Ana", telefono="600111222")
    order.confirmar()

    with pytest.raises(OrderError):
        order.anadir_item("margarita", "mediana")
    with pytest.raises(OrderError):
        order.quitar_item(1)
    with pytest.raises(OrderError):
        order.modificar_item(1, cantidad=2)
    with pytest.raises(OrderError):
        order.fijar_tipo_entrega("domicilio")
    with pytest.raises(OrderError):
        order.fijar_datos_cliente(telefono="600111222")
    with pytest.raises(OrderError):
        order.confirmar()
