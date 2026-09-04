import './Header.css'

interface Props {
  connected: boolean
}

export function Header({ connected }: Props) {
  return (
    <header>
      <h1>
        Pizzería Bella Napoli <span>· Cocina</span>
      </h1>
      <div className="estado">
        <span className={`punto${connected ? ' conectado' : ''}`} />
        <span>{connected ? 'Conectado' : 'Desconectado, reintentando…'}</span>
      </div>
    </header>
  )
}
