"""
Tools que el modelo de voz puede invocar, y su conexión con el dominio (Order).
Esta capa traduce entre "lo que entiende Gemini" (JSON schemas, function calls)
y "lo que entiende nuestro negocio" (Order, OrderError).
"""

import logging

from pizzeria_bot.domain.menu import menu_as_dict
from pizzeria_bot.domain.order import Order, OrderError
from pizzeria_bot.kitchen.store import store as kitchen_store

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
    "description": "Guarda nombre, dirección y/o el teléfono de contacto del cliente. Si el dato "
    "estaba claro y no pediste confirmación, guárdalo en cuanto lo oigas. Si sí pediste que lo "
    "confirmara (dato ambiguo, o el teléfono, que siempre se confirma), espera a un 'sí' real "
    "antes de llamar a esta función — repetirlo en voz alta no es lo mismo que confirmado. Llama "
    "a esta función en cuanto tengas CUALQUIERA de esos datos listo, no esperes a tener todos — "
    "así no se pierde lo que el cliente ya dio si la llamada se corta antes de completar el resto. "
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

_PARAMETROS_DATOS_INCIDENCIA = {
    "nombre_cliente": {
        "type": "string",
        "description": "Nombre del cliente. OBLIGATORIO: si no te lo ha dado ya, pregúntaselo "
        "antes de llamar a esta tool - nunca la llames sin tenerlo.",
    },
    "pedido": {
        "type": "string",
        "description": "Qué había pedido en el pedido afectado. Formato SIEMPRE "
        "'<cantidad> <pizza>' (ej. '1 pepperoni', '2 margaritas medianas') - nunca en las "
        "palabras textuales del cliente ('una pepperoni', 'pedí una de peperoni'), normalízalo "
        "tú al número + nombre de la pizza. No metas aquí detalles del problema (eso va en "
        "descripcion) - este campo es solo qué pizza(s) y cuántas. OBLIGATORIO: si no te lo ha "
        "dado ya, pregúntaselo antes de llamar a esta tool - nunca la llames sin tenerlo.",
    },
}

AVISAR_ESPERA_INCIDENCIA = {
    "name": "avisar_espera_incidencia",
    "description": "PRIMER PASO, obligatorio, antes de gestionar_queja: avisa al cliente de que "
    "vas a revisar su incidencia y que espere un momento. Es instantánea (no hace ninguna "
    "consulta real todavía). No la llames hasta tener el nombre del cliente y qué había pedido "
    "(pregúntaselos si no te los ha dado) - son datos obligatorios para registrar la "
    "incidencia. IMPORTANTE: llama a esta tool SOLA, en su propia respuesta, sin llamar a "
    "gestionar_queja a la vez - necesitas decir su mensaje_para_cliente en voz alta y que el "
    "cliente lo oiga ANTES de lanzar la búsqueda real. Solo cuando ya hayas dicho ese mensaje, "
    "en tu siguiente respuesta, llama a gestionar_queja (esa sí tarda de verdad).",
    "parameters": {
        "type": "object",
        "properties": _PARAMETROS_DATOS_INCIDENCIA,
        "required": ["nombre_cliente", "pedido"],
    },
}

GESTIONAR_QUEJA = {
    "name": "gestionar_queja",
    "description": "SEGUNDO PASO: gestiona de verdad una incidencia sobre un PEDIDO ANTERIOR "
    "(llegó tarde, frío, incompleto, cobro incorrecto, etc.). Solo se puede llamar DESPUÉS de "
    "haber llamado a avisar_espera_incidencia Y haber dicho su mensaje en voz alta - nunca en "
    "la misma respuesta que avisar_espera_incidencia (se rechazará si lo intentas), siempre en "
    "una respuesta aparte, posterior. Esta llamada es exclusivamente para la incidencia, nunca "
    "tomes un pedido nuevo en la misma llamada. Pásale los mismos nombre_cliente y pedido que "
    "ya usaste en avisar_espera_incidencia.",
    "parameters": {
        "type": "object",
        "properties": {
            "descripcion": {
                "type": "string",
                "description": "Lo que cuenta el cliente sobre ESTE problema en concreto, en "
                "tus propias palabras (qué pedido, qué falló). Si ya gestionaste otra "
                "incidencia distinta en esta misma llamada, no la menciones ni la mezcles aquí "
                "- esta descripción es solo del problema nuevo, se clasifica por separado.",
            },
            **_PARAMETROS_DATOS_INCIDENCIA,
        },
        "required": ["descripcion", "nombre_cliente", "pedido"],
    },
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
            AVISAR_ESPERA_INCIDENCIA,
            GESTIONAR_QUEJA,
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
        # Igual que order.confirmado: "no queda nada pendiente en esta
        # llamada" pero para el flujo de incidencias en vez del de pedido
        # (ver main.py: _idle_watchdog usa nada_pendiente para decidir si
        # empujar al modelo a colgar rápido en vez de preguntar "¿sigues
        # ahí?" con los tiempos largos de una llamada aún en curso).
        self.queja_gestionada = False
        # Se pone a True en cuanto arranca una incidencia nueva
        # (avisar_espera_incidencia) y a False cuando se resuelve
        # (gestionar_queja) - nada_pendiente NO debe ser true mientras
        # esto esté en marcha. Sin esto, tras resolver una primera
        # incidencia, nada_pendiente se quedaba en true para siempre, y si
        # el cliente reportaba una SEGUNDA incidencia en la misma llamada,
        # el watchdog seguía usando los tiempos cortos de "despídete" -
        # empujando al modelo a colgar mientras la segunda incidencia
        # todavía se estaba gestionando de verdad (visto en producción:
        # se interrumpía justo al terminar gestionar_queja, antes de que
        # el modelo llegara a contar la resolución de la segunda).
        self.queja_en_curso = False
        # Resultado de la última incidencia resuelta - se usa para
        # detectar un reintento redundante de gestionar_queja (ver más
        # abajo). Deduplicar comparando el texto de la descripción es
        # frágil (dos frases distintas para la MISMA incidencia no
        # coinciden tal cual, y dos incidencias DISTINTAS sobre el mismo
        # pedido comparten casi todas las palabras de contexto) - lo
        # fiable es el estado real del protocolo: si no ha habido un
        # avisar_espera_incidencia nuevo desde la última resolución,
        # cualquier llamada a gestionar_queja es un reintento de LO MISMO,
        # nunca una incidencia nueva.
        self._ultimo_resultado_queja: dict | None = None
        # Descripciones de las incidencias YA resueltas en esta llamada
        # (no la actual) - se le pasan al clasificador de la siguiente
        # para que ignore cualquier mención de pasada a ellas (el agente
        # de voz a veces mezcla "además del cobro ya reportado" en la
        # descripción de una incidencia nueva, y eso confundía la
        # clasificación de gravedad/compensación de la nueva).
        self._descripciones_previas: list[str] = []
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
            "avisar_espera_incidencia": self._avisar_espera_incidencia,
            "gestionar_queja": self._gestionar_queja,
        }

    def call(self, name: str, args: dict) -> dict:
        handler = self._dispatch.get(name)
        if handler is None:
            logger.warning("Tool desconocida invocada por el modelo: %s", name)
            return {"ok": False, "error": f"tool '{name}' no implementada"}
        try:
            return handler(**args)
        except (OrderError, ValueError) as e:
            # ValueError: validaciones fuera de Order (ver
            # _validar_datos_incidencia) que también son errores de
            # negocio recuperables, no bugs - mismo tratamiento que
            # OrderError, se lo contamos al modelo tal cual.
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
        kitchen_store.anadir_ticket(resumen)
        return {"ok": True, "resumen": resumen}

    def _finalizar_llamada(self) -> dict:
        # Bug real visto en producción: el modelo llamaba a
        # avisar_espera_incidencia y, en vez de seguir con gestionar_queja,
        # se despedía y colgaba directamente - la incidencia se quedaba a
        # medias para siempre (nunca se consultó la política real, así que
        # nunca hubo compensación que ofrecer). Colgar con una incidencia
        # ya avisada pero sin resolver no puede pasar nunca.
        if self.queja_en_curso:
            raise ValueError(
                "No puedes colgar todavía: le dijiste al cliente que ibas a revisar su "
                "incidencia (avisar_espera_incidencia) pero aún no has llamado a "
                "gestionar_queja para resolverla de verdad - hazlo antes de despedirte."
            )
        self.debe_colgar = True
        return {"ok": True}

    @staticmethod
    def _validar_datos_incidencia(nombre_cliente: str, pedido: str) -> None:
        # Obligatorios de verdad, no "si el modelo se acuerda": misma idea
        # que domain/order.py validando nombre/dirección/teléfono antes de
        # confirmar_pedido. Si el modelo llama a la tool sin haberlos
        # preguntado, se lo decimos para que pueda recuperarse pidiéndolos
        # en vez de seguir como si nada.
        if not nombre_cliente or not nombre_cliente.strip():
            raise ValueError("Falta el nombre del cliente para registrar la incidencia.")
        if not pedido or not pedido.strip():
            raise ValueError("Falta qué había pedido el cliente para registrar la incidencia.")
        # Visto en producción: el cliente nunca llegó a dar su nombre y el
        # modelo, en vez de volver a preguntarlo, rellenó el parámetro
        # obligatorio con un placeholder tipo "[Nombre del cliente]" - no
        # vacío, así que colaba la validación de arriba sin más. Los
        # corchetes son una señal fiable de que es un hueco sin rellenar,
        # no un dato real que un cliente diría en voz alta.
        if "[" in nombre_cliente or "]" in nombre_cliente:
            raise ValueError(
                f"'{nombre_cliente}' no es un nombre real, parece un valor de relleno - "
                "pregunta el nombre del cliente de verdad antes de continuar."
            )
        if "[" in pedido or "]" in pedido:
            raise ValueError(
                f"'{pedido}' no es un pedido real, parece un valor de relleno - pregunta "
                "qué había pedido de verdad antes de continuar."
            )

    def _avisar_espera_incidencia(self, nombre_cliente: str, pedido: str) -> dict:
        # Instantánea a propósito, sin tocar red ni RAG: el "primer paso"
        # de gestionar_queja. Narrar el resultado de una tool sí funciona
        # de forma fiable con Gemini Live (se ve en todas las tools) - lo
        # que no funciona fiablemente es hacer que el modelo hable ANTES
        # de invocar una tool lenta. Separando la espera en su propia tool
        # instantánea, el modelo la "narra" como cualquier otro resultado
        # en vez de tener que decidir hablar por su cuenta antes de llamar
        # a gestionar_queja - y como es instantánea, no hay silencio real
        # detrás de esta llamada en sí.
        # Exige nombre_cliente/pedido también aquí (no solo en
        # gestionar_queja): así el modelo no puede ni siquiera decir "dame
        # un momento" sin haberlos preguntado antes.
        self._validar_datos_incidencia(nombre_cliente, pedido)
        self.queja_en_curso = True
        return {
            "ok": True,
            "mensaje_para_cliente": "Vale, dame un momento que reviso tu caso.",
        }

    def _gestionar_queja(self, descripcion: str, nombre_cliente: str, pedido: str) -> dict:
        # Si no hay una incidencia "en curso" (es decir, no hubo un
        # avisar_espera_incidencia nuevo desde la última vez que se
        # resolvió una), esta llamada es un reintento redundante de la
        # incidencia YA resuelta - no una nueva, por distinto que suene el
        # texto de la descripción (bug real visto en producción: la misma
        # incidencia registrándose dos veces con la descripción reformulada
        # ligeramente, sin que el cliente hubiera dicho nada nuevo).
        if not self.queja_en_curso and self._ultimo_resultado_queja is not None:
            # A propósito SIN mensaje_para_cliente: si se lo devolviéramos
            # tal cual (como antes), el modelo lo narraba de nuevo entero
            # - "lamentamos mucho lo ocurrido... tu código es X..." una
            # segunda vez, sonando repetido y raro (bug real visto en
            # producción). Un aviso explícito de "no lo repitas" en vez del
            # mensaje evita la re-narración.
            return {
                "ok": True,
                "aviso": "Esta incidencia ya se gestionó y ya le contaste el resultado al "
                "cliente antes en esta misma llamada - NO lo repitas. Sigue la conversación "
                "con normalidad (pregúntale si necesita algo más, o despídete si ya dijo "
                "que no).",
            }

        self._validar_datos_incidencia(nombre_cliente, pedido)

        # Import perezoso: gestionar_queja usa el grafo de LangGraph +
        # RAG (extras "rag" y "complaints", ver pyproject.toml), que no
        # son dependencias del bot de voz base — así importar tools.py
        # (y ejecutar el resto de tools, o los tests existentes) sigue
        # sin necesitar esos paquetes instalados salvo que esta tool en
        # concreto se invoque de verdad.
        from pizzeria_bot.agents.complaint_graph import gestionar_queja

        resultado = gestionar_queja(
            descripcion,
            nombre_cliente=nombre_cliente,
            pedido=pedido,
            descripciones_previas=list(self._descripciones_previas),
        )
        logger.info("Queja gestionada: %s", resultado.get("detalle_interno"))
        self._descripciones_previas.append(descripcion)
        self._ultimo_resultado_queja = resultado
        self.queja_gestionada = True
        self.queja_en_curso = False
        return {"ok": True, **resultado}

    @property
    def nada_pendiente(self) -> bool:
        """Ya no queda nada por hacer en esta llamada (pedido confirmado, o
        incidencia ya gestionada) - lo usa main.py para saber si empujar al
        modelo a colgar rápido en vez de preguntar "¿sigues ahí?" con los
        tiempos largos de una llamada aún en curso. queja_en_curso excluye
        el rato entre avisar_espera_incidencia y gestionar_queja de una
        SEGUNDA incidencia en la misma llamada - si no, tras resolver la
        primera esto se quedaba en true para siempre, y el watchdog
        empujaba a colgar mientras la segunda aún se estaba gestionando
        de verdad."""
        return self.order.confirmado or (self.queja_gestionada and not self.queja_en_curso)
