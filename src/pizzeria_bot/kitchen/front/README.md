# front/ — Pantalla de cocina (React)

Interfaz de la pantalla de cocina (`/kitchen`): la fila de tickets confirmados,
un chatbot de preguntas frecuentes y un panel de incidencias pendientes de
revisión. Consume el `WebSocket /kitchen/ws`, el `POST /faq/preguntar` y el
`GET /incidencias/pendientes` que ya expone `server.py` — este proyecto no
cambia el contrato del backend, solo cómo se renderiza.

Pedidos e incidencias comparten una única impresora física (igual que en una
cocina real solo hay una) — si llegan a la vez, uno espera su turno detrás
del otro en vez de imprimirse encima (ver `hooks/useColaImpresion.ts`).

## Desarrollo

Con el backend corriendo (`uvicorn pizzeria_bot.server:app --reload` desde la
raíz del proyecto, puerto 8000):

```bash
npm install
npm run dev
```

Abre la URL que imprima Vite (normalmente `http://localhost:5173`). El
WebSocket, el `POST /faq/preguntar` y el `GET /incidencias/pendientes` se
proxean automáticamente al backend en `:8000` (ver `vite.config.ts`), así
que no hace falta tocar nada para que funcione en desarrollo. El chatbot de
FAQ necesita además que el índice RAG esté generado
(`python -m pizzeria_bot.rag.ingest`, ver `rag/README.md`) y
`GEMINI_API_KEY` configurada — si no, el backend responde 502 a cada
pregunta.

## Build para producción

```bash
npm run build
```

El resultado se escribe directamente en
`../src/pizzeria_bot/kitchen/static/` (ver `outDir` en `vite.config.ts`) —
`server.py` lo sirve desde ahí en `GET /kitchen` (el HTML) y `GET /assets/*`
(JS/CSS), sin tocar nada más. Tras cambiar cualquier componente, hay que
volver a correr `npm run build` para que el backend sirva la versión nueva —
no se reconstruye solo.

## Estructura

`App.tsx` es quien orquesta todo: mantiene la única cola de impresión
compartida y decide qué tarjeta imprimir (ticket o incidencia) según lo que
toque.

- `src/hooks/`
  - `useColaImpresion.ts` — cola FIFO genérica de una sola impresora física.
    No sabe nada de tickets ni incidencias: cualquiera de los dos feeds de
    abajo le puede pedir turno con `encolar()`.
  - `useKitchenFeed.ts` — solo el feed de pedidos: conexión WebSocket,
    reconexión automática, lista de tickets ya asentados. Ya no imprime nada
    por su cuenta — cuando llega un pedido nuevo, se lo pasa a la cola
    compartida.
  - `useIncidenciasFeed.ts` — igual que el anterior pero para incidencias:
    polling cada 10s contra `GET /incidencias/pendientes`, detecta cuáles
    son nuevas (no las que ya había al cargar la página) y las manda a la
    misma cola compartida.
- `src/components/kitchen/`
  - `Header.tsx` — cabecera: marca (sello + nombre en serif, "Cocina" como
    sección), reloj en vivo y estado de conexión.
  - `ImpresoraAnimada.tsx` — la animación física de "imprimir" en sí
    (parpadeo de la luz → el papel sale de la ranura → se asienta), genérica
    sobre cualquier tipo de item. `App.tsx` monta una única instancia y
    decide qué tarjeta va dentro (`TicketCard` o `IncidenciaCard`) según lo
    que la cola compartida tenga en curso — no hay una impresora por tipo.
  - `TicketCard.tsx` / `TicketRail.tsx` — el ticket individual y el corcho
    donde se van pinchando.
- `src/components/chat/ChatFAQ.tsx` — asistente virtual (botón flotante +
  panel desplegable), habla contra `POST /faq/preguntar` (ver
  `rag/README.md`).
- `src/components/incidencias/`
  - `PanelIncidencias.tsx` — panel aparte (no mezclado con los tickets del
    corcho) que solo pinta la lista de incidencias graves ya asentadas — la
    detección de cuáles son nuevas y la impresión viven en `App.tsx` /
    `useIncidenciasFeed.ts`, no aquí.
  - `IncidenciaCard.tsx` — la tarjeta de una incidencia, mismo lenguaje
    visual que `TicketCard` (papel, chincheta, mono) con acentos propios
    (franja roja, "PENDIENTE") para distinguirla de un pedido de un vistazo.
- `src/components/dev/DevSimulador.tsx` — botón de solo desarrollo para
  simular pedidos sin necesitar una llamada real (eliminado del build de
  producción, ver el propio archivo).
