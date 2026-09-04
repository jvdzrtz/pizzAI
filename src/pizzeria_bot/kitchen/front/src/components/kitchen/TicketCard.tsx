import type { CSSProperties } from 'react'
import type { Ticket } from '../../types'
import './TicketCard.css'

function formatearHora(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
}

/** Ángulo determinista en [-2, 2] grados derivado del id del ticket - da
 * el mismo look "puesto a mano" variado de antes, pero sin depender de
 * Math.random() durante el render (React desaconseja llamadas impuras ahí:
 * un mismo ticket podría re-renderizarse con un ángulo distinto). */
function anguloDesdeId(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) | 0
  }
  return ((hash % 40) / 10) - 2
}

interface Props {
  ticket: Ticket
  /** Ángulo de rotación en reposo (grados). Si no se pasa, se deriva del
   * id del ticket (ver anguloDesdeId) - el look de "puesto a mano" que ya
   * teníamos antes, pero determinista en vez de aleatorio. */
  giro?: number
  /** La impresora controla su propia animación de entrada (el papel
   * saliendo de la ranura) - cuando el ticket vive dentro de ella no debe
   * jugar también su animación de "caída" en la fila. */
  sinAnimacionEntrada?: boolean
}

export function TicketCard({ ticket, giro, sinAnimacionEntrada = false }: Props) {
  const { resumen } = ticket
  const esDomicilio = resumen.tipo_entrega === 'domicilio'
  const angulo = giro ?? anguloDesdeId(ticket.id)

  return (
    <div
      className={`ticket${sinAnimacionEntrada ? ' ticket--estatico' : ''}`}
      style={{ '--giro': `${angulo}deg` } as CSSProperties}
    >
      <div className="ticket-cabecera">
        <span className="ticket-hora">{formatearHora(ticket.creado_en)}</span>
        <span className={`badge ${esDomicilio ? '' : 'recogida'}`}>
          {esDomicilio ? 'A domicilio' : 'Recogida'}
        </span>
      </div>

      <ul className="items">
        {resumen.items.map((item) => (
          <li key={item.item_id}>
            <span>
              {item.cantidad}× {item.pizza} ({item.tamano})
            </span>
            <span>{item.subtotal.toFixed(2)}€</span>
          </li>
        ))}
      </ul>

      <div className="ticket-cliente">
        <div>
          <span className="etiqueta">Nombre</span>
          <br />
          {resumen.nombre_cliente ?? '-'}
        </div>
        {esDomicilio && resumen.direccion && (
          <div>
            <span className="etiqueta">Dirección</span>
            <br />
            {resumen.direccion}
          </div>
        )}
        <div>
          <span className="etiqueta">Teléfono</span>
          <br />
          {resumen.telefono ?? '-'}
        </div>
      </div>

      <div className="ticket-total">{resumen.total.toFixed(2)}€</div>
    </div>
  )
}
