import type { CSSProperties } from 'react'
import type { Incidencia } from '../../types'
import './IncidenciaCard.css'

/** Mismo truco que TicketCard.anguloDesdeId: ángulo determinista en
 * [-2, 2] grados derivado del id, para no depender de Math.random(). */
function anguloDesdeId(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return ((hash % 40) / 10) - 2
}

interface Props {
  incidencia: Incidencia
  giro?: number
  /** La impresora controla su propia animación de entrada - ver
   * TicketCard.sinAnimacionEntrada. */
  sinAnimacionEntrada?: boolean
}

export function IncidenciaCard({ incidencia, giro, sinAnimacionEntrada = false }: Props) {
  const angulo = giro ?? anguloDesdeId(incidencia.id)

  return (
    <div
      className={`incidencia-ticket${sinAnimacionEntrada ? ' incidencia-ticket--estatico' : ''}`}
      style={{ '--giro': `${angulo}deg` } as CSSProperties}
    >
      <div className="incidencia-ticket-cabecera">
        <span className="incidencia-ticket-alerta">⚠ Incidencia</span>
        <span className="incidencia-ticket-badge">Pendiente</span>
      </div>

      <p className="incidencia-ticket-tipo">{incidencia.tipo_incidencia}</p>

      <div className="incidencia-ticket-datos">
        <div>
          <span className="etiqueta">Cliente</span>
          <br />
          {incidencia.nombre_cliente ?? '-'}
        </div>
        <div>
          <span className="etiqueta">Pedido</span>
          <br />
          {incidencia.pedido ?? '-'}
        </div>
      </div>

      <p className="incidencia-ticket-decision">{incidencia.decision_tomada}</p>
    </div>
  )
}
