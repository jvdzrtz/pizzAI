import { useEffect, useState } from 'react'
import './PanelIncidencias.css'

interface Incidencia {
  id: string
  nombre_cliente: string | null
  pedido: string | null
  tipo_incidencia: string
  decision_tomada: string
  estado: string
}

const POLL_MS = 10000

export function PanelIncidencias() {
  const [incidencias, setIncidencias] = useState<Incidencia[]>([])

  useEffect(() => {
    let cancelado = false

    async function cargar() {
      try {
        const respuesta = await fetch('/incidencias/pendientes')
        if (!respuesta.ok) return
        const datos: Incidencia[] = await respuesta.json()
        if (!cancelado) setIncidencias(datos)
      } catch {
        // Fallo de red puntual: se reintenta solo en el siguiente poll, no
        // hace falta molestar con un error - no es una acción del usuario.
      }
    }

    cargar()
    const intervalo = setInterval(cargar, POLL_MS)
    return () => {
      cancelado = true
      clearInterval(intervalo)
    }
  }, [])

  return (
    <aside className="panel-incidencias">
      <h2>Incidencias{incidencias.length > 0 ? ` (${incidencias.length})` : ''}</h2>
      {incidencias.length === 0 ? (
        <p className="incidencias-vacio">Sin incidencias pendientes de revisión.</p>
      ) : (
        <ul className="incidencias-lista">
          {incidencias.map((incidencia) => (
            <li key={incidencia.id} className="incidencia-card">
              <p className="incidencia-tipo">{incidencia.tipo_incidencia}</p>
              <p className="incidencia-dato">
                <span className="etiqueta">Cliente</span> {incidencia.nombre_cliente ?? '-'}
              </p>
              <p className="incidencia-dato">
                <span className="etiqueta">Pedido</span> {incidencia.pedido ?? '-'}
              </p>
              <p className="incidencia-decision">{incidencia.decision_tomada}</p>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
