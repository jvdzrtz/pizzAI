import type { Ticket } from '../../types'
import { ImpresoraAnimada } from './ImpresoraAnimada'
import { TicketCard } from './TicketCard'

interface Props {
  ticket: Ticket | null
  onDone: () => void
}

export function Printer({ ticket, onDone }: Props) {
  return (
    <ImpresoraAnimada item={ticket} idDe={(t) => t.id} onDone={onDone}>
      {(t) => <TicketCard ticket={t} giro={0} sinAnimacionEntrada />}
    </ImpresoraAnimada>
  )
}
