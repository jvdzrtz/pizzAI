import { useEffect, useState } from 'react'
import './Header.css'

interface Props {
  connected: boolean
}

function useRelojEnVivo(): string {
  const [hora, setHora] = useState(() => new Date())

  useEffect(() => {
    const intervalo = setInterval(() => setHora(new Date()), 1000)
    return () => clearInterval(intervalo)
  }, [])

  return hora.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function Header({ connected }: Props) {
  const hora = useRelojEnVivo()

  return (
    <header>
      <div className="marca">
        <span className="marca-logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
            <path
              d="M12 4.2 20 18.4a9 9 0 0 1-16 0Z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
            <circle cx="12" cy="12.4" r="0.9" fill="currentColor" />
            <circle cx="9.4" cy="16" r="0.9" fill="currentColor" />
            <circle cx="14.6" cy="16" r="0.9" fill="currentColor" />
          </svg>
        </span>
        <div className="marca-texto">
          <span className="marca-eyebrow">Pizzería Bella Napoli</span>
          <h1>Panel de cocina</h1>
        </div>
      </div>

      <div className="header-derecha">
        <span className="reloj">{hora}</span>
        <span className="separador" aria-hidden="true" />
        <div className={`estado${connected ? ' conectado' : ''}`}>
          <span className="estado-punto" />
          {connected ? 'En línea' : 'Reconectando…'}
        </div>
      </div>
    </header>
  )
}
