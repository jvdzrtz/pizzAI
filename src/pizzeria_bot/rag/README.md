# rag/ — FAQ de políticas del restaurante (RAG)

Módulo **aislado y standalone**: responde preguntas de horarios, métodos
de pago, zona de reparto y normas usando solo el contenido real de los
documentos que suba el dueño del restaurante — nunca inventa una política
que no esté en esos documentos.

No está conectado al agente de voz (`agents/tools.py`), a `server.py` ni
a Twilio todavía — eso es un paso posterior, deliberadamente fuera del
alcance de este módulo. El menú y los alérgenos tampoco pasan por aquí:
van con lógica determinista aparte.

## Instalar

```bash
uv pip install -e ".[rag]"
```

Necesita `GEMINI_API_KEY` en `.env` (la misma variable que ya usa el
resto del proyecto — ver `.env.example` en la raíz).

> Nota: `langchain-community` (de donde salen `PyPDFLoader`/`TextLoader`)
> avisa en cada import de que está "sunset" y recomienda paquetes de
> integración independientes. Sigue funcionando perfectamente; es solo un
> aviso de cara al futuro, no algo a lo que reaccionar ahora.

## 1. Añadir o actualizar documentos de políticas

Coloca tus `.pdf`, `.txt` o `.md` en `rag_docs/` (raíz del proyecto — no
en `docs/`, que ya se usa para documentación de desarrollador). Cualquier
otro tipo de archivo ahí dentro se ignora sin fallar.

Ya incluye `rag_docs/ejemplo-politicas.txt`, un documento de políticas
inventado pero extenso (horarios, pago, reparto, normas — ~10 chunks tras
trocear) para poder probar el módulo con retrieval real de verdad, no solo
con un texto tan corto que quepa entero en el top-k.

## 2. Indexar (o reindexar tras cambiar documentos)

```bash
python -m pizzeria_bot.rag.ingest
```

Cada ejecución **sustituye por completo** el índice anterior (no es
incremental) — así un documento borrado o editado no deja restos
obsoletos en la base vectorial. Se persiste en `.chroma/` en la raíz del
proyecto (no versionado — ver nota de `.gitignore` más abajo).

## 3. Probar `responder_faq()` de forma aislada

Desde línea de comandos:

```bash
python -m pizzeria_bot.rag.faq_chain "¿A qué hora cerráis?"
python -m pizzeria_bot.rag.faq_chain "¿Tenéis parking para autobuses?"
```

La primera responde con el dato real del documento; la segunda —al no
estar cubierta— responde que no tiene esa información, sin inventar nada.

Desde Python:

```python
from pizzeria_bot.rag.faq_chain import responder_faq

responder_faq("¿Aceptáis Bizum?")
# "Sí, aceptamos Bizum. También puedes pagar en efectivo o con
#  tarjeta de crédito/débito..."
```

## Tests

```bash
pytest tests/test_rag.py -v
```

Dos grupos:

- **Unitarios** (ingesta y cableado de la cadena): sin red, sin API key.
  Usan un retriever y un LLM falsos (`RunnableLambda`) para comprobar que
  el contexto recuperado y la pregunta llegan de verdad al prompt, y que
  la salida del LLM llega intacta al resultado — sin depender de cómo
  responda un modelo real.
- **Integración** (`test_responder_faq_...`): ingesta real + Chroma real +
  Gemini real (embeddings y LLM), sobre un corpus mínimo en un directorio
  temporal — no dependen de `rag_docs/` real. Se saltan automáticamente
  si no hay `GEMINI_API_KEY` configurada. Si los corres varias veces
  seguidas puedes toparte con `429 RESOURCE_EXHAUSTED` (límite de cuota
  de la API en llamadas de embeddings muy seguidas) — no es un fallo del
  código, solo espera unos segundos entre ejecuciones.

## Notas de implementación

- **Modelo de embeddings**: `gemini-embedding-2-preview` — el único
  documentado actualmente para `GoogleGenerativeAIEmbeddings`
  (comprobado en la documentación de LangChain, sept. 2026). Es un
  modelo "preview"; si Google publica una versión estable, actualizar
  `EMBEDDING_MODEL` en `ingest.py`.
- **Modelo de chat**: `gemini-3.6-flash`. La documentación de LangChain
  recomienda `gemini-2.5-flash`, pero la propia API de Google lo rechaza
  hoy con 404 para cuentas nuevas y sugiere este modelo — se confirmó
  contra la API real, no solo contra la documentación.
- **`google_api_key` explícito** en ambas clases (`ingest.py` y
  `faq_chain.py`): por defecto solo miran `GOOGLE_API_KEY`/`GEMINI_API_KEY`
  en el entorno del proceso, y este proyecto carga `.env` vía
  `pydantic-settings` (`config.py`) sin exportarlo a `os.environ` — sin
  pasarlo a mano, la librería no la encuentra aunque el resto del
  proyecto sí la tenga.
- **`retriever`/`llm` inyectables** en `build_chain()`: pensado para
  testear el cableado de la cadena con dobles deterministas, sin
  necesitar credenciales para esa parte.

## Pendiente (fuera de alcance de este módulo)

- Añadir `.chroma/` al `.gitignore` de la raíz del proyecto — no lo he
  tocado porque la tarea decía explícitamente "no toques ningún fichero
  existente" salvo `pyproject.toml`, pero sin esa línea, `.chroma/`
  (una base SQLite de Chroma) puede acabar commiteada por accidente.
- Conectar `responder_faq()` al agente de voz y/o a un endpoint HTTP —
  deliberadamente fuera de esta tarea.
