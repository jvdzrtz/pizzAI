import { useCallback, useEffect, useState } from 'react'
import type { MensajeServidor, Ticket } from '../types'

interface KitchenFeed {
  tickets: Ticket[]
  connected: boolean
  /** Añade un ticket ya impreso a la fila de pedidos de verdad - lo llama
   * el padre cuando la impresora compartida termina de sacarlo (ver
   * App.tsx y hooks/useColaImpresion.ts). */
  agregarTicket: (ticket: Ticket) => void
}

const RECONEXION_MS = 2000

/** Solo el feed de pedidos (WebSocket + lista asentada) - la impresión en
 * sí la gestiona una única cola compartida en App.tsx, porque pedidos e
 * incidencias salen de la misma máquina física. */
export function useKitchenFeed(onNuevoTicket: (ticket: Ticket) => void): KitchenFeed {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [connected, setConnected] = useState(false)

  const agregarTicket = useCallback((ticket: Ticket) => {
    // Al final del array, no al principio: así el ticket nuevo se añade
    // "detrás" en el flujo del corcho sin desplazar los que ya estaban -
    // clave para que el corcho no se mueva cada vez que entra un pedido.
    setTickets((actuales) => [...actuales, ticket])
  }, [])

  useEffect(() => {
    let ws: WebSocket | null = null
    let reintentoTimer: ReturnType<typeof setTimeout> | null = null
    let cerrado = false

    function conectar() {
      const protocolo = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${protocolo}://${location.host}/kitchen/ws`)

      ws.onopen = () => setConnected(true)

      ws.onmessage = (evento) => {
        const data: MensajeServidor = JSON.parse(evento.data)
        if (data.event === 'snapshot') {
          setTickets(data.tickets)
        } else if (data.event === 'nuevo_ticket') {
          onNuevoTicket(data.ticket)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        if (!cerrado) reintentoTimer = setTimeout(conectar, RECONEXION_MS)
      }

      ws.onerror = () => ws?.close()
    }

    conectar()

    return () => {
      cerrado = true
      if (reintentoTimer) clearTimeout(reintentoTimer)
      ws?.close()
    }
  }, [onNuevoTicket])

  return { tickets, connected, agregarTicket }
}
