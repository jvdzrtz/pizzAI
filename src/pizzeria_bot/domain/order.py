import re
from typing import Literal

from pydantic import BaseModel

from pizzeria_bot.domain.menu import MENU

TipoEntrega = Literal["recogida", "domicilio"]


class OrderItem(BaseModel):
    item_id: int
    pizza: str
    tamano: str
    cantidad: int = 1
    precio_unidad: float
    subtotal: float


class OrderError(Exception):
    """Error de negocio al manipular un pedido (pizza inexistente, falta de datos, etc.)."""


class Order(BaseModel):
    """
    Un pedido en curso. Es dominio puro: no sabe nada de Gemini, audio,
    ni telefonía. Esto es lo que la hace fácil de testear y de reutilizar
    si mañana cambiamos de proveedor de voz.
    """

    items: list[OrderItem] = []
    tipo_entrega: TipoEntrega | None = None
    nombre_cliente: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    confirmado: bool = False
    _next_item_id: int = 1

    @property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)

    def _asegurar_no_confirmado(self) -> None:
        if self.confirmado:
            raise OrderError("El pedido ya está confirmado, no se puede modificar.")

    def _normalizar_pizza(self, pizza: str) -> str:
        pizza_key = pizza.strip().lower()
        pizza_key = pizza_key.removeprefix("pizza ").strip()
        if pizza_key not in MENU:
            disponibles = ", ".join(MENU.keys())
            raise OrderError(f"'{pizza}' no está en el menú. Disponibles: {disponibles}")
        return pizza_key

    def _buscar_item(self, item_id: int) -> OrderItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        ids_disponibles = ", ".join(str(i.item_id) for i in self.items) or "ninguno"
        raise OrderError(
            f"No hay ningún ítem con id {item_id}. IDs en el pedido: {ids_disponibles}."
        )

    def anadir_item(self, pizza: str, tamano: str, cantidad: int = 1) -> OrderItem:
        self._asegurar_no_confirmado()
        if cantidad < 1:
            raise OrderError(f"La cantidad debe ser al menos 1 (recibido: {cantidad}).")

        pizza_key = self._normalizar_pizza(pizza)
        precio_unidad = MENU[pizza_key].precio(tamano)
        item = OrderItem(
            item_id=self._next_item_id,
            pizza=pizza_key,
            tamano=tamano,
            cantidad=cantidad,
            precio_unidad=precio_unidad,
            subtotal=precio_unidad * cantidad,
        )
        self._next_item_id += 1
        self.items.append(item)
        return item

    def quitar_item(self, item_id: int) -> OrderItem:
        self._asegurar_no_confirmado()
        item = self._buscar_item(item_id)
        self.items.remove(item)
        return item

    def modificar_item(
        self,
        item_id: int,
        pizza: str | None = None,
        tamano: str | None = None,
        cantidad: int | None = None,
    ) -> OrderItem:
        self._asegurar_no_confirmado()
        item = self._buscar_item(item_id)

        nueva_pizza = self._normalizar_pizza(pizza) if pizza is not None else item.pizza
        nuevo_tamano = tamano if tamano is not None else item.tamano
        nueva_cantidad = cantidad if cantidad is not None else item.cantidad
        if nueva_cantidad < 1:
            raise OrderError(f"La cantidad debe ser al menos 1 (recibido: {nueva_cantidad}).")

        precio_unidad = MENU[nueva_pizza].precio(nuevo_tamano)
        item.pizza = nueva_pizza
        item.tamano = nuevo_tamano
        item.cantidad = nueva_cantidad
        item.precio_unidad = precio_unidad
        item.subtotal = precio_unidad * nueva_cantidad
        return item

    def fijar_tipo_entrega(self, tipo: str) -> None:
        self._asegurar_no_confirmado()
        if tipo not in ("recogida", "domicilio"):
            raise OrderError(f"'{tipo}' no es válido: debe ser 'recogida' o 'domicilio'.")
        self.tipo_entrega = tipo

    def fijar_datos_cliente(
        self,
        nombre: str | None = None,
        direccion: str | None = None,
        telefono: str | None = None,
    ) -> None:
        """Guarda nombre, dirección y/o teléfono - cualquiera de los tres por
        separado a propósito: en una llamada real la información llega en
        trozos, y si exigimos varios a la vez se pierde lo que el cliente ya
        dio si la llamada se corta antes de completar el resto."""
        self._asegurar_no_confirmado()
        if nombre is None and direccion is None and telefono is None:
            raise OrderError("Hay que dar al menos un dato: nombre, dirección o teléfono.")

        if nombre is not None:
            nombre_normalizado = nombre.strip()
            if len(nombre_normalizado) < 2:
                raise OrderError(f"'{nombre}' no parece un nombre válido.")
            self.nombre_cliente = nombre_normalizado

        if direccion is not None:
            direccion_normalizada = direccion.strip()
            if len(direccion_normalizada) < 6 or not any(
                c.isdigit() for c in direccion_normalizada
            ):
                raise OrderError(
                    f"'{direccion}' no parece una dirección válida: debe incluir calle y número."
                )
            self.direccion = direccion_normalizada

        if telefono is not None:
            telefono_normalizado = re.sub(r"\D", "", telefono)
            if len(telefono_normalizado) != 9:
                raise OrderError(f"El teléfono '{telefono}' no es válido: debe tener 9 dígitos.")
            self.telefono = telefono_normalizado

    def confirmar(self) -> dict:
        self._asegurar_no_confirmado()
        if not self.items:
            raise OrderError("No hay ninguna pizza en el pedido todavía.")
        if self.tipo_entrega is None:
            raise OrderError("Falta saber si es recogida en el local o entrega a domicilio.")
        if not self.nombre_cliente:
            raise OrderError("Falta el nombre del cliente.")
        if self.tipo_entrega == "domicilio" and not self.direccion:
            raise OrderError("Falta la dirección de entrega.")
        if not self.telefono:
            raise OrderError("Falta el teléfono de contacto.")

        self.confirmado = True
        return {
            "items": [item.model_dump() for item in self.items],
            "tipo_entrega": self.tipo_entrega,
            "nombre_cliente": self.nombre_cliente,
            "direccion": self.direccion,
            "telefono": self.telefono,
            "total": self.total,
        }
