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
    "confirme una pizza y su tamaño. Si pide varias unidades iguales a la vez (mismo tamaño), "
    "usa 'cantidad' en una sola llamada en vez de llamar varias veces.",
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

QUITAR_ITEM_PEDIDO = {
    "name": "quitar_item_pedido",
    "description": "Quita una pizza ya añadida al pedido. Necesitas el item_id, que se devuelve "
    "al añadir el ítem o al consultar el pedido actual.",
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "integer",
                "description": "Id del ítem a quitar. Uso interno para esta tool - nunca lo "
                "digas en voz alta al cliente, ni siquiera si te lo pide directamente.",
            },
        },
        "required": ["item_id"],
    },
}

MODIFICAR_ITEM_PEDIDO = {
    "name": "modificar_item_pedido",
    "description": "Cambia la pizza, el tamaño y/o la cantidad de un ítem ya añadido, sin "
    "quitarlo y volver a añadirlo. Solo pasa los campos que cambian; los demás se mantienen.",
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "integer",
                "description": "Id del ítem a modificar. Uso interno para esta tool - nunca lo "
                "digas en voz alta al cliente, ni siquiera si te lo pide directamente.",
            },
            "pizza": {"type": "string", "description": "Nuevo nombre de pizza (opcional)."},
            "tamano": {
                "type": "string",
                "enum": ["mediana", "familiar"],
                "description": "Nuevo tamaño (opcional).",
            },
            "cantidad": {"type": "integer", "description": "Nueva cantidad (opcional)."},
        },
        "required": ["item_id"],
    },
}

CONSULTAR_PEDIDO_ACTUAL = {
    "name": "consultar_pedido_actual",
    "description": "Devuelve el estado actual del pedido: ítems con su item_id, dirección, "
    "teléfono y total. Úsala si necesitas confirmar los item_id antes de quitar o modificar "
    "algo, o para repasar el pedido con el cliente.",
    "parameters": {"type": "object", "properties": {}},
}

FIJAR_TIPO_ENTREGA = {
    "name": "fijar_tipo_entrega",
    "description": "Guarda si el cliente quiere recoger el pedido en el local o que se lo "
    "llevemos a domicilio. Pregúntalo justo después de tener claro el pedido de pizzas, antes "
    "de pedir nombre o dirección — según la respuesta necesitarás una cosa u otra.",
    "parameters": {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["recogida", "domicilio"]},
        },
        "required": ["tipo"],
    },
}

FIJAR_DATOS_CLIENTE = {
    "name": "fijar_datos_cliente",
    "description": "Guarda nombre, dirección y/o el teléfono de contacto del cliente. Llama a "
    "esta función en cuanto tengas CUALQUIERA de esos datos, no esperes a tener todos — así no "
    "se pierde lo que el cliente ya dio si la llamada se corta antes de completar el resto. "
    "El nombre se pide siempre, sea recogida o domicilio. Si es a domicilio, pide además la "
    "dirección. El teléfono se pide siempre al final, independientemente del tipo de entrega.",
    "parameters": {
        "type": "object",
        "properties": {
            "nombre": {"type": "string"},
            "direccion": {"type": "string"},
            "telefono": {"type": "string"},
        },
    },
}

CONFIRMAR_PEDIDO = {
    "name": "confirmar_pedido",
    "description": "Cierra y confirma el pedido definitivamente. Solo llámala cuando ya haya "
    "al menos una pizza, el tipo de entrega, los datos que ese tipo requiere (nombre si es "
    "recogida, dirección si es domicilio), el teléfono, y el cliente haya confirmado "
    "explícitamente. Después de esto ya no se puede modificar el pedido.",
    "parameters": {"type": "object", "properties": {}},
}

FINALIZAR_LLAMADA = {
    "name": "finalizar_llamada",
    "description": "Cuelga la llamada. Llámala SOLO después de haberte despedido en voz alta "
    "del cliente (ej. dice 'gracias, adiós' y tú ya le has respondido con una despedida) y no "
    "quede nada pendiente. Nunca la llames antes de decir tu despedida — la llamada se corta "
    "en cuanto se ejecuta esta función.",
    "parameters": {"type": "object", "properties": {}},
}

TOOLS = [
    {
        "function_declarations": [
            CONSULTAR_MENU,
            ANADIR_ITEM_PEDIDO,
            QUITAR_ITEM_PEDIDO,
            MODIFICAR_ITEM_PEDIDO,
            CONSULTAR_PEDIDO_ACTUAL,
            FIJAR_TIPO_ENTREGA,
            FIJAR_DATOS_CLIENTE,
            CONFIRMAR_PEDIDO,
            FINALIZAR_LLAMADA,
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
        self.debe_colgar = False
        self._dispatch = {
            "consultar_menu": self._consultar_menu,
            "anadir_item_pedido": self._anadir_item_pedido,
            "quitar_item_pedido": self._quitar_item_pedido,
            "modificar_item_pedido": self._modificar_item_pedido,
            "consultar_pedido_actual": self._consultar_pedido_actual,
            "fijar_tipo_entrega": self._fijar_tipo_entrega,
            "fijar_datos_cliente": self._fijar_datos_cliente,
            "confirmar_pedido": self._confirmar_pedido,
            "finalizar_llamada": self._finalizar_llamada,
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

    def _quitar_item_pedido(self, item_id: int) -> dict:
        item = self.order.quitar_item(item_id)
        return {"ok": True, "item_quitado": item.model_dump(), "total_actual": self.order.total}

    def _modificar_item_pedido(
        self,
        item_id: int,
        pizza: str | None = None,
        tamano: str | None = None,
        cantidad: int | None = None,
    ) -> dict:
        item = self.order.modificar_item(item_id, pizza=pizza, tamano=tamano, cantidad=cantidad)
        return {"ok": True, "item_modificado": item.model_dump(), "total_actual": self.order.total}

    def _consultar_pedido_actual(self) -> dict:
        return {
            "ok": True,
            "items": [item.model_dump() for item in self.order.items],
            "tipo_entrega": self.order.tipo_entrega,
            "nombre_cliente": self.order.nombre_cliente,
            "direccion": self.order.direccion,
            "telefono": self.order.telefono,
            "total": self.order.total,
        }

    def _fijar_tipo_entrega(self, tipo: str) -> dict:
        self.order.fijar_tipo_entrega(tipo)
        return {"ok": True, "tipo_entrega": self.order.tipo_entrega}

    def _fijar_datos_cliente(
        self,
        nombre: str | None = None,
        direccion: str | None = None,
        telefono: str | None = None,
    ) -> dict:
        self.order.fijar_datos_cliente(nombre=nombre, direccion=direccion, telefono=telefono)
        return {
            "ok": True,
            "nombre_cliente": self.order.nombre_cliente,
            "direccion": self.order.direccion,
            "telefono": self.order.telefono,
        }

    def _confirmar_pedido(self) -> dict:
        resumen = self.order.confirmar()
        logger.info("PEDIDO CONFIRMADO: %s", resumen)
        return {"ok": True, "resumen": resumen}

    def _finalizar_llamada(self) -> dict:
        self.debe_colgar = True
        return {"ok": True}
