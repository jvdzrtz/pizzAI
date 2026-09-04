# front/ — Pantalla de cocina (React)

Interfaz de la pantalla de cocina (`/kitchen`): la fila de tickets confirmados,
la animación de la impresora y un chatbot de preguntas frecuentes. Consume el
`WebSocket /kitchen/ws` y el `POST /faq/preguntar` que ya expone `server.py` —
este proyecto no cambia el contrato del backend, solo cómo se renderiza.

## Desarrollo

Con el backend corriendo (`uvicorn pizzeria_bot.server:app --reload` desde la
raíz del proyecto, puerto 8000):

```bash
npm install
npm run dev
```

Abre la URL que imprima Vite (normalmente `http://localhost:5173`). El
WebSocket y el `POST /faq/preguntar` se proxean automáticamente al backend
en `:8000` (ver `vite.config.ts`), así que no hace falta tocar nada para
que funcione en desarrollo. El chatbot de FAQ necesita además que el índice
RAG esté generado (`python -m pizzeria_bot.rag.ingest`, ver `rag/README.md`)
y `GEMINI_API_KEY` configurada — si no, el backend responde 502 a cada
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

- `src/hooks/useKitchenFeed.ts` — conexión WebSocket, cola de impresión,
  reconexión automática, estado de tickets.
- `src/components/kitchen/` — la pantalla de cocina en sí:
  - `Header.tsx` — cabecera con el estado de conexión.
  - `Printer.tsx` — la animación de "imprimir" un ticket nuevo (parpadeo de
    la luz → el papel sale de la ranura → se asienta en el corcho).
  - `TicketCard.tsx` / `TicketRail.tsx` — el ticket individual y el corcho
    donde se van pinchando.
- `src/components/chat/ChatFAQ.tsx` — asistente virtual (botón flotante +
  panel desplegable), habla contra `POST /faq/preguntar` (ver
  `rag/README.md`).
- `src/components/dev/DevSimulador.tsx` — botón de solo desarrollo para
  simular pedidos sin necesitar una llamada real (eliminado del build de
  producción, ver el propio archivo).
