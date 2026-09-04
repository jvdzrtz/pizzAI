"""
Almacén en memoria de tickets confirmados + aviso en vivo por WebSocket a
la pantalla de cocina (server.py: /kitchen). Un pedido se convierte en
ticket en cuanto ToolRouter.confirmar_pedido() tiene éxito (ver
agents/tools.py) - no se espera a que el modelo se despida ni a que
cuelgue de verdad, porque el pedido ya queda cerrado en ese momento.

En memoria a propósito, no en base de datos: coherente con el resto del
proyecto ahora mismo (confirmar_pedido tampoco persiste todavía, ver
Roadmap del README) - los tickets desaparecen si se reinicia el servidor.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class _SendsJSON(Protocol):
    async def send_json(self, data: Any) -> None: ...


class Ticket(BaseModel):
    id: str
    creado_en: datetime
    resumen: dict  # mismo shape que Order.confirmar() devuelve


class TicketStore:
    """Puede haber varias pantallas de cocina abiertas a la vez (varias
    pestañas, varios dispositivos) - de ahí que sea un set de clientes,
    no uno solo."""

    def __init__(self) -> None:
        self._tickets: list[Ticket] = []
        self._clientes: set[_SendsJSON] = set()

    def snapshot(self) -> list[Ticket]:
        return list(self._tickets)

    def registrar_cliente(self, websocket: _SendsJSON) -> None:
        self._clientes.add(websocket)

    def desregistrar_cliente(self, websocket: _SendsJSON) -> None:
        self._clientes.discard(websocket)

    def anadir_ticket(self, resumen: dict) -> Ticket:
        """Síncrono a propósito: ToolRouter.call() despacha las tools de
        forma síncrona (ver agents/tools.py), y no queremos convertir todo
        ese dispatch a async solo por esto. Guarda el ticket al instante y
        lanza el aviso por WebSocket como tarea de fondo."""
        ticket = Ticket(id=str(uuid.uuid4()), creado_en=datetime.now(UTC), resumen=resumen)
        self._tickets.append(ticket)
        try:
            asyncio.get_running_loop().create_task(self._emitir(ticket))
        except RuntimeError:
            # Sin event loop corriendo (p.ej. un test que llama a
            # anadir_ticket directamente) - el ticket queda guardado igual,
            # simplemente no hay a quién avisar en vivo ahora mismo.
            logger.debug("Sin event loop activo, no se emite el ticket %s por WebSocket", ticket.id)
        return ticket

    async def _emitir(self, ticket: Ticket) -> None:
        payload = {"event": "nuevo_ticket", "ticket": ticket.model_dump(mode="json")}
        muertos = []
        for cliente in self._clientes:
            try:
                await cliente.send_json(payload)
            except Exception:
                logger.debug("Pantalla de cocina desconectada, se retira de la lista", exc_info=True)
                muertos.append(cliente)
        for cliente in muertos:
            self._clientes.discard(cliente)


store = TicketStore()
