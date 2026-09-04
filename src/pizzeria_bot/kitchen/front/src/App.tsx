import { ChatFAQ } from './components/chat/ChatFAQ'
import { DevSimulador } from './components/dev/DevSimulador'
import { Header } from './components/kitchen/Header'
import { Printer } from './components/kitchen/Printer'
import { TicketRail } from './components/kitchen/TicketRail'
import { useKitchenFeed } from './hooks/useKitchenFeed'

export function App() {
  const { tickets, printingTicket, connected, onPrintDone, encolarTicket } = useKitchenFeed()

  return (
    <>
      <Header connected={connected} />
      <main>
        <aside className="columna-impresora">
          <Printer ticket={printingTicket} onDone={onPrintDone} />
        </aside>
        <TicketRail tickets={tickets} />
      </main>
      <ChatFAQ />
      <DevSimulador onSimular={encolarTicket} />
    </>
  )
}
