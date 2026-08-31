# Troubleshooting — telefonía real (Twilio)

Problemas concretos encontrados montando el flujo de llamadas reales, con su causa y solución.

## El túnel cambia de URL cada vez que lo arranco

`devtunnel host -p 8000 --allow-anonymous` (sin más) crea un túnel nuevo
con URL aleatoria en cada ejecución — significa volver a actualizar el
webhook en Twilio cada sesión. Para evitarlo, crea un túnel con nombre fijo
**una sola vez**:

```bash
devtunnel create pizzai --allow-anonymous
devtunnel port create pizzai -p 8000
```

Y a partir de ahí, arráncalo siempre así (misma URL pública todas las
veces, no hace falta tocar Twilio de nuevo):

```bash
devtunnel host pizzai
```

Te da una URL fija tipo `https://xxxxx-8000.<region>.devtunnels.ms` (el
`xxxxx` es un identificador aparte del nombre del túnel, pero se mantiene
estable mientras reutilices `devtunnel host pizzai`).

Con ngrok en el plan gratuito la URL cambia en cada ejecución sí o sí —
hay que repetir el paso 3 del README cada vez que reinicies el túnel.

## `devtunnel`/`ngrok` no se encuentra tras instalarlo con winget

El PATH nuevo lo recoge un proceso de VS Code recién arrancado, no una
terminal nueva dentro del mismo VS Code ya abierto — **reinicia VS Code
entero** (no solo la pestaña de terminal). Mientras tanto, usa la ruta
completa: busca el `.exe` dentro de
`%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`.

## ngrok se queja de que la versión es insuficiente

El paquete de winget puede instalar una versión antigua (visto: 3.3.1,
insuficiente — ngrok pide ≥3.20.0). Actualízala con `ngrok update`. El
propio actualizador puede disparar un falso positivo de antivirus
(`Trojan:...!rfn`, detección heurística por reputación, no una firma
real) al reemplazar su propio `.exe` — restáuralo desde Windows Security
si te pasa, o usa devtunnel en su lugar.

## El servidor devuelve 403 a peticiones que sabes que son de Twilio de verdad

Los túneles (devtunnel, y a veces ngrok) pueden reescribir la cabecera
`Host` que le llega a tu app a algo interno (`localhost:8000`) en vez del
dominio público real, aunque sí reenvían el dominio público en
`X-Forwarded-Host`. El servidor ya usa `X-Forwarded-Host` cuando está
presente (`server.py: _public_host`), pero si cambias de túnel y vuelve a
fallar, es lo primero a revisar — los logs de `403` en
`voice_incoming`/`media_stream` imprimen `host_header` y
`x-forwarded-host` para diagnosticarlo.

Para el **handshake del WebSocket** específicamente (no el webhook POST),
Twilio a veces firma la URL con una barra final `/` aunque la URL real
(la del TwiML) no la lleve — es una inconsistencia conocida y documentada
por el propio Twilio, no un bug del proyecto. `media_stream` ya prueba la
firma con y sin barra final antes de rechazar.

## Twilio rechaza la llamada saliente con "Account not authorized... enable international permissions" (error 21215)

Es un permiso de cuenta, no un bug: por defecto las cuentas nuevas no
tienen habilitados todos los países para llamadas salientes (protección
antifraude). Actívalo en
[Geo Permissions](https://www.twilio.com/console/voice/calls/geo-permissions/low-risk)
→ busca tu país (España está en "Western Europe") → actívalo → guarda.
