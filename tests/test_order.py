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


def test_fijar_datos_entrega_telefono_invalido_lanza_error():
    order = Order()
    with pytest.raises(OrderError):
        order.fijar_datos_entrega("Calle Falsa 123", "12345")


def test_fijar_datos_entrega_normaliza_telefono_con_separadores():
    order = Order()
    order.fijar_datos_entrega("Calle Falsa 123", "600 111 222")
    assert order.telefono == "600111222"


def test_confirmar_sin_items_falla():
    order = Order()
    order.fijar_datos_entrega("Calle Falsa 123", "600111222")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_sin_datos_entrega_falla():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    with pytest.raises(OrderError):
        order.confirmar()


def test_confirmar_pedido_completo_funciona():
    order = Order()
    order.anadir_item("pepperoni", "mediana")
    order.fijar_datos_entrega("Calle Falsa 123", "600111222")
    resumen = order.confirmar()
    assert order.confirmado is True
    assert resumen["total"] == 10.0
    assert resumen["direccion"] == "Calle Falsa 123"
