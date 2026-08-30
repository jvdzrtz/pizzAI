"""
Dispara una llamada SALIENTE desde tu número de Twilio hacia un móvil real,
usando el mismo TwiML que las llamadas entrantes (server.py: /voice/incoming)
- Twilio no distingue si el TwiML es para una llamada entrante o saliente,
así que no hace falta ningún endpoint nuevo en el servidor.

Por qué existe: llamar TÚ a un número de Twilio desde fuera de EE.UU. suele
salir caro (tarifa internacional de tu operadora). Que sea Twilio quien te
llame a ti es mucho más barato: el coste corre por tu saldo de Twilio
(~$0.0486/min a un móvil español, por ejemplo), y recibir una llamada en tu
móvil es gratis, sea de donde sea. Ver la sección "Telefonía real (Twilio)"
del README para el desglose completo.
"""

import sys

from twilio.rest import Client

from pizzeria_bot.config import (
    require_twilio_account_sid,
    require_twilio_auth_token,
    require_twilio_phone_number,
)


def build_call_params(to_number: str, base_url: str) -> dict:
    """Construye los parámetros para client.calls.create(). Separado de
    main() para poder testear la construcción de la URL (p.ej. que una
    barra final en base_url no rompa nada) sin llamar a la API real."""
    twiml_url = f"{base_url.rstrip('/')}/voice/incoming"
    return {
        "to": to_number,
        "from_": require_twilio_phone_number(),
        "url": twiml_url,
    }


def main() -> None:
    if len(sys.argv) != 3:
        print("Uso: pizzai-call <numero_destino> <url_publica_del_servidor>")
        print("Ejemplo: pizzai-call +34612345678 https://xxxxx.devtunnels.ms")
        sys.exit(1)

    params = build_call_params(sys.argv[1], sys.argv[2])
    client = Client(require_twilio_account_sid(), require_twilio_auth_token())
    call = client.calls.create(**params)

    print(f"Llamada iniciada: SID={call.sid}")
    print(f"De {params['from_']} a {params['to']}")
    print(f"TwiML servido desde: {params['url']}")


if __name__ == "__main__":
    main()
