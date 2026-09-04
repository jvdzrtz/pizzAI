import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// El build se escribe en kitchen/static/, al lado de este propio front/
// (mismo padre: kitchen/) - server.py lo sirve desde ahí sin más.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // En desarrollo (npm run dev), el WebSocket real vive en el
      // servidor FastAPI (puerto 8000, ver server.py) - lo proxeamos para
      // poder usar una URL relativa igual en dev y en producción.
      '/kitchen/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
      // Igual, pero para el POST del chatbot de FAQ (ver server.py:
      // /faq/preguntar, que llama a rag/faq_chain.responder_faq).
      '/faq': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
})
