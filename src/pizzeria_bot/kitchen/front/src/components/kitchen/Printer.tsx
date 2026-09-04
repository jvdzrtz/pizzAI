import { useEffect, useRef, useState } from 'react'
import type { Ticket } from '../../types'
import { TicketCard } from './TicketCard'
import './Printer.css'

interface Props {
  ticket: Ticket | null
  /** Se llama cuando termina toda la secuencia (parpadeo + papel +
   * pausa) - el padre mueve el ticket a la fila de pedidos en ese momento. */
  onDone: () => void
}

const PARPADEO_MS = 250
const SACAR_PAPEL_MS = 1900
const PAUSA_FINAL_MS = 350

export function Printer({ ticket, onDone }: Props) {
  const medidorRef = useRef<HTMLDivElement>(null)
  const [altura, setAltura] = useState(0)
  const [imprimiendo, setImprimiendo] = useState(false)
  const [saliendo, setSaliendo] = useState(false)

  useEffect(() => {
    if (!ticket) {
      setAltura(0)
      setImprimiendo(false)
      setSaliendo(false)
      return
    }

    setImprimiendo(true)
    setAltura(0)
    setSaliendo(false)

    // Fase 1 (parpadeo): un flash breve antes de sacar el papel, para que
    // se note que "empieza a imprimir" y no aparece de golpe. El ticket ya
    // está montado (oculto por altura: 0), así que medirlo aquí da su
    // altura real.
    const t1 = setTimeout(() => {
      setAltura(medidorRef.current?.scrollHeight ?? 0)
      setSaliendo(true)
    }, PARPADEO_MS)

    // Fase 2: el papel termina de salir - quitamos el temblor mecánico
    // (ya no tiene sentido una vez el papel está quieto y completo).
    const t2 = setTimeout(() => {
      setSaliendo(false)
    }, PARPADEO_MS + SACAR_PAPEL_MS)

    // Fase 3: tras una pequeña pausa, avisamos al padre - a partir de ahí
    // el ticket pasa a vivir en la fila de pedidos, con su propia
    // animación de caída al asentarse.
    const t3 = setTimeout(
      () => {
        setImprimiendo(false)
        onDone()
      },
      PARPADEO_MS + SACAR_PAPEL_MS + PAUSA_FINAL_MS,
    )

    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
    // Solo debe reiniciar la secuencia cuando cambia el ticket en sí, no
    // en cada render (onDone se recrea con cada snapshot de tickets).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket?.id])

  return (
    <div className="impresora">
      <div className={`impresora-cuerpo${imprimiendo ? ' imprimiendo' : ''}`}>
        <span className="impresora-etiqueta" />
        <span className="impresora-luz" />
      </div>
      <div className="impresora-bandeja">
        <div className="impresora-ranura" />
      </div>

      <div
        className={`impresora-papel${saliendo ? ' saliendo' : ''}`}
        style={{ height: altura, transitionDuration: `${SACAR_PAPEL_MS}ms` }}
      >
        {ticket && (
          <div ref={medidorRef}>
            <TicketCard ticket={ticket} giro={0} sinAnimacionEntrada />
          </div>
        )}
      </div>
    </div>
  )
}
