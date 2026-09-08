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
        {/* Marca circular con degradado cálido (tipo horno de leña) en vez
         * de un icono plano - le da presencia y calidez de restaurante sin
         * caer en el cliché de un icono de pizza literal. */}
        <span className="marca-sello" aria-hidden="true">
          N
        </span>
        <h1 className="marca-texto">
          <span className="marca-nombre">Bella Napoli</span>
          <span className="marca-seccion">Cocina</span>
        </h1>
      </div>

      <div className="header-derecha">
        <span className="reloj">{hora}</span>
        <span className="divisor" aria-hidden="true" />
        <div className={`estado${connected ? ' conectado' : ''}`}>
          <span className="estado-punto" />
          {connected ? 'En línea' : 'Reconectando'}
        </div>
      </div>
    </header>
  )
}
