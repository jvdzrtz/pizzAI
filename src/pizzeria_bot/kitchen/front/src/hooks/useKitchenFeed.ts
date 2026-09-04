import { useCallback, useEffect, useRef, useState } from 'react'
import type { MensajeServidor, Ticket } from '../types'

interface KitchenFeed {
  tickets: Ticket[]
  /** El ticket que está "imprimiéndose" ahora mismo en la máquina, o null
   * si no hay ninguno en curso. Solo se rellena para tickets que llegan en
   * vivo (evento nuevo_ticket) - los del snapshot inicial no se reimprimen. */
  printingTicket: Ticket | null
  connected: boolean
  /** El componente Printer llama a esto cuando termina su animación de
   * impresión - es el momento en que el ticket pasa a formar parte de la
   * fila de pedidos de verdad, y arranca el siguiente de la cola si hay. */
  onPrintDone: () => void
  /** Mete un ticket en la cola de impresión. Si la impresora está libre,
   * empieza a imprimirlo ya; si no, espera su turno - lo usan tanto el
   * WebSocket (pedidos reales) como el simulador de desarrollo. */
  encolarTicket: (ticket: Ticket) => void
}

const RECONEXION_MS = 2000

export function useKitchenFeed(): KitchenFeed {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [printingTicket, setPrintingTicket] = useState<Ticket | null>(null)
  const [connected, setConnected] = useState(false)
  const printingRef = useRef<Ticket | null>(null)
  // Cola FIFO de tickets esperando turno para imprimirse. Sin esto, un
  // pedido que llega mientras otro se está imprimiendo pisa al que está en
  // curso: su animación se corta a medias y el ticket interrumpido
  // desaparece sin llegar nunca al corcho.
  const colaRef = useRef<Ticket[]>([])

  const imprimirSiguiente = useCallback(() => {
    const siguiente = colaRef.current.shift() ?? null
    printingRef.current = siguiente
    setPrintingTicket(siguiente)
  }, [])

  const encolarTicket = useCallback(
    (ticket: Ticket) => {
      if (printingRef.current) {
        colaRef.current.push(ticket)
      } else {
        printingRef.current = ticket
        setPrintingTicket(ticket)
      }
    },
    [],
  )

  const onPrintDone = useCallback(() => {
    const ticket = printingRef.current
    if (!ticket) return
    // Al final del array, no al principio: así el ticket nuevo se añade
    // "detrás" en el flujo del corcho sin desplazar los que ya estaban -
    // clave para que el corcho no se mueva cada vez que entra un pedido.
    setTickets((actuales) => [...actuales, ticket])
    imprimirSiguiente()
  }, [imprimirSiguiente])

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
          encolarTicket(data.ticket)
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
  }, [encolarTicket])

  return { tickets, printingTicket, connected, onPrintDone, encolarTicket }
}
