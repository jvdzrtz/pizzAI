"""
Tests de PizzeriaCallSession._handle_tool_call (main.py), en concreto el
guard que impide meter avisar_espera_incidencia y gestionar_queja en el
mismo lote de function calls.

Bug real visto en producción: Gemini metía las dos tools en un mismo
response.tool_call - como send_tool_response() solo se llama una vez al
final con TODAS las respuestas del lote juntas, el modelo nunca "oía" el
mensaje de espera antes de que la búsqueda real (10s) ya hubiera
terminado, así que decía las dos frases juntas al final. El guard rechaza
gestionar_queja si viene en el mismo lote que avisar_espera_incidencia,
forzando dos rondas separadas.
"""

import asyncio

from pizzeria_bot.agents.tools import ToolRouter
from pizzeria_bot.main import CallEndedByModel, PizzeriaCallSession


class _FakeFunctionCall:
    def __init__(self, fid: str, name: str, args: dict) -> None:
        self.id = fid
        self.name = name
        self.args = args


class _FakeToolCall:
    def __init__(self, function_calls: list[_FakeFunctionCall]) -> None:
        self.function_calls = function_calls


class _FakeSession:
    def __init__(self) -> None:
        self.lotes_enviados: list[list] = []

    async def send_tool_response(self, function_responses) -> None:
        self.lotes_enviados.append(function_responses)


def _crear_sesion() -> PizzeriaCallSession:
    sesion = PizzeriaCallSession(client=None, audio_io=None, tool_router=ToolRouter())
    sesion.session = _FakeSession()
    return sesion


def _por_nombre(respuestas) -> dict:
    return {r.name: r.response for r in respuestas}


def test_avisar_y_gestionar_en_el_mismo_lote_rechaza_gestionar_queja(monkeypatch):
    from pizzeria_bot.agents import complaint_graph

    llamadas_reales = []

    def _fake_gestionar_queja(descripcion, nombre_cliente, pedido, descripciones_previas=None):
        llamadas_reales.append(descripcion)
        return {"resuelto": True, "mensaje_para_cliente": "x", "detalle_interno": {}}

    monkeypatch.setattr(complaint_graph, "gestionar_queja", _fake_gestionar_queja)

    sesion = _crear_sesion()
    tool_call = _FakeToolCall(
        [
            _FakeFunctionCall(
                "1", "avisar_espera_incidencia", {"nombre_cliente": "Ana", "pedido": "1 margarita"}
            ),
            _FakeFunctionCall(
                "2",
                "gestionar_queja",
                {"descripcion": "llegó tarde", "nombre_cliente": "Ana", "pedido": "1 margarita"},
            ),
        ]
    )

    asyncio.run(sesion._handle_tool_call(tool_call))

    [respuestas] = sesion.session.lotes_enviados
    por_nombre = _por_nombre(respuestas)
    assert por_nombre["avisar_espera_incidencia"]["ok"] is True
    assert por_nombre["gestionar_queja"]["ok"] is False
    # La tool real nunca se llegó a invocar - se rechazó antes.
    assert llamadas_reales == []
    assert sesion.tool_router.queja_gestionada is False


def test_gestionar_queja_sola_en_su_lote_se_ejecuta_normal(monkeypatch):
    from pizzeria_bot.agents import complaint_graph

    monkeypatch.setattr(
        complaint_graph,
        "gestionar_queja",
        lambda descripcion, nombre_cliente, pedido, descripciones_previas=None: {
            "resuelto": True,
            "mensaje_para_cliente": "x",
            "detalle_interno": {},
        },
    )

    sesion = _crear_sesion()
    tool_call = _FakeToolCall(
        [
            _FakeFunctionCall(
                "1",
                "gestionar_queja",
                {"descripcion": "llegó tarde", "nombre_cliente": "Ana", "pedido": "1 margarita"},
            ),
        ]
    )

    asyncio.run(sesion._handle_tool_call(tool_call))

    [respuestas] = sesion.session.lotes_enviados
    assert _por_nombre(respuestas)["gestionar_queja"]["ok"] is True
    assert sesion.tool_router.queja_gestionada is True


class _FakeServerContent:
    def __init__(self, interrupted=False, output_transcription=None, input_transcription=None):
        self.interrupted = interrupted
        self.output_transcription = output_transcription
        self.input_transcription = input_transcription


class _FakeResponse:
    def __init__(self, data=None, tool_call=None, server_content=None):
        self.data = data
        self.tool_call = tool_call
        self.server_content = server_content


class _FakeAudioIO:
    async def write_chunk(self, data) -> None:
        pass

    async def wait_until_speaker_drained(self) -> None:
        pass

    def clear_output_buffer(self) -> None:
        pass


class _FakeReceiveSession:
    """Simula session.receive() devolviendo un turno (lista de responses)
    distinto cada vez que se llama - así se puede reproducir la secuencia
    real: turno 1 (avisar_espera_incidencia), turno 2 (lo que sea que
    venga después)."""

    def __init__(self, turnos: list[list[_FakeResponse]]) -> None:
        self._turnos = turnos
        self._indice = 0
        self.tool_responses_enviados: list = []
        self.realtime_inputs_de_texto: list[str] = []

    async def send_tool_response(self, function_responses) -> None:
        self.tool_responses_enviados.append(function_responses)

    async def send_realtime_input(self, text=None, audio=None) -> None:
        if text is not None:
            self.realtime_inputs_de_texto.append(text)

    def receive(self):
        turno = self._turnos[self._indice]
        self._indice += 1

        async def _generador():
            for respuesta in turno:
                yield respuesta

        return _generador()


def test_tras_avisar_espera_incidencia_empuja_a_gestionar_queja(monkeypatch):
    # Bug real visto en producción: tras decir el mensaje de espera, el
    # modelo se quedaba callado indefinidamente en vez de continuar solo
    # con gestionar_queja (se quedó más de un minuto sin hacer nada hasta
    # que el cliente volvió a hablar). _receive_and_play debe empujarlo
    # él mismo en cuanto termina el turno donde dijo el mensaje de espera.
    monkeypatch.setattr("pizzeria_bot.main.settings.hangup_grace_seconds", 0)
    from pizzeria_bot.agents import complaint_graph

    monkeypatch.setattr(
        complaint_graph,
        "gestionar_queja",
        lambda descripcion, nombre_cliente, pedido, descripciones_previas=None: {
            "resuelto": True,
            "mensaje_para_cliente": "x",
            "detalle_interno": {},
        },
    )

    sesion = PizzeriaCallSession(client=None, audio_io=_FakeAudioIO(), tool_router=ToolRouter())
    turno_1 = [
        _FakeResponse(
            tool_call=_FakeToolCall(
                [
                    _FakeFunctionCall(
                        "1",
                        "avisar_espera_incidencia",
                        {"nombre_cliente": "Javi", "pedido": "1 pepperoni"},
                    )
                ]
            )
        )
    ]
    turno_2 = [
        _FakeResponse(
            tool_call=_FakeToolCall(
                [
                    _FakeFunctionCall(
                        "2",
                        "gestionar_queja",
                        {
                            "descripcion": "llegó tarde",
                            "nombre_cliente": "Javi",
                            "pedido": "1 pepperoni",
                        },
                    )
                ]
            )
        )
    ]
    turno_3 = [_FakeResponse(tool_call=_FakeToolCall([_FakeFunctionCall("3", "finalizar_llamada", {})]))]
    sesion.session = _FakeReceiveSession([turno_1, turno_2, turno_3])

    try:
        asyncio.run(sesion._receive_and_play())
    except CallEndedByModel:
        pass

    nudges = sesion.session.realtime_inputs_de_texto
    assert len(nudges) == 1
    assert "gestionar_queja" in nudges[0]
    assert "Javi" in nudges[0]
    assert "1 pepperoni" in nudges[0]
