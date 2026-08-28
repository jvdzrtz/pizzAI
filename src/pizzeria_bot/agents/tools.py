"""
Tools que el modelo de voz puede invocar, y su conexión con el dominio (Order).
Esta capa traduce entre "lo que entiende Gemini" (JSON schemas, function calls)
y "lo que entiende nuestro negocio" (Order, OrderError).
"""

import logging

from pizzeria_bot.domain.menu import menu_as_dict
from pizzeria_bot.domain.order import Order, OrderError

logger = logging.getLogger(__name__)

CONSULTAR_MENU = {
    "name": "consultar_menu",
    "description": "Devuelve la lista de pizzas disponibles con precios e ingredientes. "
    "Úsala si el cliente pregunta qué hay, precios, o ingredientes de alguna pizza.",
    "parameters": {"type": "object", "properties": {}},
}

ANADIR_ITEM_PEDIDO = {
    "name": "anadir_item_pedido",
    "description": "Añade una pizza al pedido actual. Llama a esta función en cuanto el cliente "
    "confirme una pizza y su tamaño.",
    "parameters": {
        "type": "object",
        "properties": {
            "pizza": {
                "type": "string",
                "description": "Nombre de la pizza tal y como está en el menú.",
            },
            "tamano": {"type": "string", "enum": ["mediana", "familiar"]},
            "cantidad": {"type": "integer", "description": "Unidades. Por defecto 1."},
        },
        "required": ["pizza", "tamano"],
    },
}

FIJAR_DATOS_ENTREGA = {
    "name": "fijar_datos_entrega",
    "description": "Guarda la dirección y el teléfono de contacto del cliente para la entrega.",
    "parameters": {
        "type": "object",
        "properties": {
            "direccion": {"type": "string"},
            "telefono": {"type": "string"},
        },
        "required": ["direccion", "telefono"],
    },
}

CONFIRMAR_PEDIDO = {
    "name": "confirmar_pedido",
    "description": "Cierra y confirma el pedido definitivamente. Solo llámala cuando ya haya "
    "al menos una pizza, dirección y teléfono, y el cliente haya confirmado explícitamente.",
    "parameters": {"type": "object", "properties": {}},
}

TOOLS = [
    {
        "function_declarations": [
            CONSULTAR_MENU,
            ANADIR_ITEM_PEDIDO,
            FIJAR_DATOS_ENTREGA,
            CONFIRMAR_PEDIDO,
        ]
    }
]


class ToolRouter:
    """
    Ejecuta las tool calls que llegan de Gemini contra un Order concreto.
    Una instancia de ToolRouter = una llamada/sesión en curso.
    """

    def __init__(self) -> None:
        self.order = Order()
        self._dispatch = {
            "consultar_menu": self._consultar_menu,
            "anadir_item_pedido": self._anadir_item_pedido,
            "fijar_datos_entrega": self._fijar_datos_entrega,
            "confirmar_pedido": self._confirmar_pedido,
        }

    def call(self, name: str, args: dict) -> dict:
        handler = self._dispatch.get(name)
        if handler is None:
            logger.warning("Tool desconocida invocada por el modelo: %s", name)
            return {"ok": False, "error": f"tool '{name}' no implementada"}
        try:
            return handler(**args)
        except OrderError as e:
            logger.info("Error de negocio en tool %s: %s", name, e)
            return {"ok": False, "error": str(e)}
        except TypeError as e:
            # Argumentos faltantes o de más (ej. el cliente no dio el tamaño
            # todavía). Se lo decimos al modelo para que pueda recuperarse
            # preguntando de nuevo, en vez de dejarlo sin saber qué pasó.
            logger.info("Argumentos inválidos en tool %s(%s): %s", name, args, e)
            return {"ok": False, "error": f"faltan o sobran argumentos para '{name}': {e}"}
        except Exception:
            logger.exception("Error inesperado ejecutando tool %s", name)
            return {"ok": False, "error": "error interno"}

    def _consultar_menu(self) -> dict:
        return {"ok": True, "menu": menu_as_dict()}

    def _anadir_item_pedido(self, pizza: str, tamano: str, cantidad: int = 1) -> dict:
        item = self.order.anadir_item(pizza, tamano, cantidad)
        return {"ok": True, "item_anadido": item.model_dump(), "total_actual": self.order.total}

    def _fijar_datos_entrega(self, direccion: str, telefono: str) -> dict:
        self.order.fijar_datos_entrega(direccion, telefono)
        return {"ok": True}

    def _confirmar_pedido(self) -> dict:
        resumen = self.order.confirmar()
        logger.info("PEDIDO CONFIRMADO: %s", resumen)
        return {"ok": True, "resumen": resumen}
