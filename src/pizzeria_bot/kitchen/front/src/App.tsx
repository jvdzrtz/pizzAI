import { useCallback } from 'react'
import { ChatFAQ } from './components/chat/ChatFAQ'
import { DevSimulador } from './components/dev/DevSimulador'
import { IncidenciaCard } from './components/incidencias/IncidenciaCard'
import { PanelIncidencias } from './components/incidencias/PanelIncidencias'
import { Header } from './components/kitchen/Header'
import { ImpresoraAnimada } from './components/kitchen/ImpresoraAnimada'
import { TicketCard } from './components/kitchen/TicketCard'
import { TicketRail } from './components/kitchen/TicketRail'
import { useColaImpresion } from './hooks/useColaImpresion'
import { useIncidenciasFeed } from './hooks/useIncidenciasFeed'
import { useKitchenFeed } from './hooks/useKitchenFeed'
import type { Incidencia, ItemImprimible, Ticket } from './types'

function idDeItem(item: ItemImprimible): string {
  return item.tipo === 'ticket' ? item.ticket.id : item.incidencia.id
}

export function App() {
  // Una única impresora física para todo lo que sale de cocina - pedidos
  // e incidencias comparten cola, así que si llegan a la vez, una espera
  // a que la otra termine en vez de imprimirse encima.
  const cola = useColaImpresion<ItemImprimible>()

  // OJO: cola.encolar (no `cola`) como dependencia - `cola` es un objeto
  // nuevo en cada render, así que usarlo como dependencia rehace este
  // callback cada vez, lo que a su vez reinicia el efecto de conexión del
  // WebSocket/polling en cada render y nunca deja completarse (bucle de
  // reconexión infinito).
  const onNuevoTicket = useCallback(
    (ticket: Ticket) => cola.encolar({ tipo: 'ticket', ticket }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cola.encolar],
  )
  const onNuevaIncidencia = useCallback(
    (incidencia: Incidencia) => cola.encolar({ tipo: 'incidencia', incidencia }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cola.encolar],
  )
  const { tickets, connected, agregarTicket } = useKitchenFeed(onNuevoTicket)
  const { incidencias, agregarIncidencia } = useIncidenciasFeed(onNuevaIncidencia)

  function onPrintDone() {
    cola.onDone((item) => {
      if (item.tipo === 'ticket') agregarTicket(item.ticket)
      else agregarIncidencia(item.incidencia)
    })
  }

  function simularTicket(ticket: Ticket) {
    cola.encolar({ tipo: 'ticket', ticket })
  }

  return (
    <>
      <Header connected={connected} />
      <main>
        <aside className="columna-impresora">
          <ImpresoraAnimada item={cola.actual} idDe={idDeItem} onDone={onPrintDone}>
            {(item) =>
              item.tipo === 'ticket' ? (
                <TicketCard ticket={item.ticket} giro={0} sinAnimacionEntrada />
              ) : (
                <IncidenciaCard incidencia={item.incidencia} giro={0} sinAnimacionEntrada />
              )
            }
          </ImpresoraAnimada>
        </aside>
        <TicketRail tickets={tickets} />
        <PanelIncidencias incidencias={incidencias} />
      </main>
      <ChatFAQ />
      <DevSimulador onSimular={simularTicket} />
    </>
  )
}
