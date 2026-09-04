import { useEffect, useRef, useState } from 'react'
import './ChatFAQ.css'

interface Mensaje {
  id: string
  autor: 'usuario' | 'bot'
  texto: string
  esError?: boolean
}

const MENSAJE_INICIAL: Mensaje = {
  id: 'inicial',
  autor: 'bot',
  texto:
    'Hola, soy tu asistente virtual. Pregúntame sobre horarios, métodos de pago, ' +
    'zona de reparto o normas de la casa.',
}

/** Icono de "chispa" - el motivo visual habitual para "asistente con IA"
 * en vez de un bot genérico, y como SVG en vez de emoji se ve igual de
 * nítido en cualquier sistema/navegador. Un único destello construido a
 * mano con simetría de 4 puntas exacta respecto al centro del viewBox
 * (12,12) - con dos chispas de tamaños distintos (la primera versión) el
 * "peso" visual quedaba descentrado hacia una esquina aunque el propio
 * <svg> estuviera centrado en el botón. */
function IconoChispa() {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path
        d="M12 2 Q14 10 22 12 Q14 14 12 22 Q10 14 2 12 Q10 10 12 2 Z"
        fill="currentColor"
      />
    </svg>
  )
}

function IconoCerrar() {
  return (
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2.3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function ChatFAQ() {
  const [abierto, setAbierto] = useState(false)
  const [mensajes, setMensajes] = useState<Mensaje[]>([MENSAJE_INICIAL])
  const [pregunta, setPregunta] = useState('')
  const [enviando, setEnviando] = useState(false)
  const finRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto) return
    finRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [mensajes, enviando, abierto])

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    const texto = pregunta.trim()
    if (!texto || enviando) return

    setMensajes((actuales) => [...actuales, { id: crypto.randomUUID(), autor: 'usuario', texto }])
    setPregunta('')
    setEnviando(true)

    try {
      const respuesta = await fetch('/faq/preguntar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: texto }),
      })

      if (!respuesta.ok) {
        throw new Error(`El servidor respondió ${respuesta.status}`)
      }

      const datos: { respuesta: string } = await respuesta.json()
      setMensajes((actuales) => [
        ...actuales,
        { id: crypto.randomUUID(), autor: 'bot', texto: datos.respuesta },
      ])
    } catch {
      setMensajes((actuales) => [
        ...actuales,
        {
          id: crypto.randomUUID(),
          autor: 'bot',
          esError: true,
          texto: 'No se pudo obtener respuesta ahora mismo. Inténtalo de nuevo en unos segundos.',
        },
      ])
    } finally {
      setEnviando(false)
    }
  }

  return (
    <>
      {abierto && (
        <div className="chat-faq-panel">
          <div className="chat-faq-cabecera">
            <h2>Asistente virtual</h2>
            <button
              type="button"
              className="chat-faq-cerrar"
              onClick={() => setAbierto(false)}
              aria-label="Cerrar asistente"
            >
              <IconoCerrar />
            </button>
          </div>

          <div className="chat-faq-mensajes">
            {mensajes.map((mensaje) => (
              <div
                key={mensaje.id}
                className={`chat-burbuja chat-burbuja--${mensaje.autor}${mensaje.esError ? ' chat-burbuja--error' : ''}`}
              >
                {mensaje.texto}
              </div>
            ))}
            {enviando && (
              <div className="chat-burbuja chat-burbuja--bot chat-burbuja--cargando">
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={finRef} />
          </div>

          <form className="chat-faq-formulario" onSubmit={enviar}>
            <input
              type="text"
              value={pregunta}
              onChange={(evento) => setPregunta(evento.target.value)}
              placeholder="¿Hacéis reparto a domicilio?"
              disabled={enviando}
            />
            <button type="submit" disabled={enviando || !pregunta.trim()}>
              Enviar
            </button>
          </form>
        </div>
      )}

      <button
        type="button"
        className={`chat-faq-boton${abierto ? '' : ' chat-faq-boton--pulso'}`}
        onClick={() => setAbierto((actual) => !actual)}
        aria-label={abierto ? 'Cerrar asistente virtual' : 'Abrir asistente virtual'}
      >
        {abierto ? <IconoCerrar /> : <IconoChispa />}
      </button>
    </>
  )
}
