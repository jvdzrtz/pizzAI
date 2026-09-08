import type { Incidencia } from '../../types'
import { IncidenciaCard } from './IncidenciaCard'
import './PanelIncidencias.css'

interface Props {
  incidencias: Incidencia[]
}

/** Solo pinta la lista ya asentada - la impresión pasa por la impresora
 * compartida en App.tsx (ver hooks/useIncidenciasFeed.ts y
 * hooks/useColaImpresion.ts), no por este componente. */
export function PanelIncidencias({ incidencias }: Props) {
  return (
    <aside className="panel-incidencias">
      <h2>Incidencias{incidencias.length > 0 ? ` (${incidencias.length})` : ''}</h2>

      {incidencias.length === 0 ? (
        <p className="incidencias-vacio">Sin incidencias pendientes de revisión.</p>
      ) : (
        <ul className="incidencias-lista">
          {incidencias.map((incidencia) => (
            <li key={incidencia.id}>
              <IncidenciaCard incidencia={incidencia} />
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
