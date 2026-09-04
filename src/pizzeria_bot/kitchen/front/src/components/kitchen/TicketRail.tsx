import type { Ticket } from '../../types'
import { TicketCard } from './TicketCard'
import './TicketRail.css'

interface Props {
  tickets: Ticket[]
}

export function TicketRail({ tickets }: Props) {
  return (
    <div className="corcho">
      {tickets.length === 0 ? (
        <p className="rail-vacio">Sin pedidos todavía. En cuanto se confirme una llamada, aparece aquí.</p>
      ) : (
        <div className="rail">
          {tickets.map((ticket) => (
            <TicketCard key={ticket.id} ticket={ticket} />
          ))}
        </div>
      )}
    </div>
  )
}
