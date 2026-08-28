import re

from pydantic import BaseModel

from pizzeria_bot.domain.menu import MENU


class OrderItem(BaseModel):
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
    direccion: str | None = None
    telefono: str | None = None
    confirmado: bool = False

    @property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)

    def anadir_item(self, pizza: str, tamano: str, cantidad: int = 1) -> OrderItem:
        if cantidad < 1:
            raise OrderError(f"La cantidad debe ser al menos 1 (recibido: {cantidad}).")

        pizza_key = pizza.strip().lower()
        pizza_key = pizza_key.removeprefix("pizza ").strip()
        menu_item = MENU.get(pizza_key)
        if menu_item is None:
            disponibles = ", ".join(MENU.keys())
            raise OrderError(f"'{pizza}' no está en el menú. Disponibles: {disponibles}")

        precio_unidad = menu_item.precio(tamano)
        item = OrderItem(
            pizza=pizza_key,
            tamano=tamano,
            cantidad=cantidad,
            precio_unidad=precio_unidad,
            subtotal=precio_unidad * cantidad,
        )
        self.items.append(item)
        return item

    def fijar_datos_entrega(self, direccion: str, telefono: str) -> None:
        telefono_normalizado = re.sub(r"\D", "", telefono)
        if len(telefono_normalizado) != 9:
            raise OrderError(f"El teléfono '{telefono}' no es válido: debe tener 9 dígitos.")
        self.direccion = direccion
        self.telefono = telefono_normalizado

    def confirmar(self) -> dict:
        if not self.items:
            raise OrderError("No hay ninguna pizza en el pedido todavía.")
        if not self.direccion or not self.telefono:
            raise OrderError("Faltan dirección o teléfono antes de confirmar.")

        self.confirmado = True
        return {
            "items": [item.model_dump() for item in self.items],
            "direccion": self.direccion,
            "telefono": self.telefono,
            "total": self.total,
        }
