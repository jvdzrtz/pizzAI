import { useCallback, useEffect, useRef, useState } from 'react'
import type { Incidencia } from '../types'

interface IncidenciasFeed {
  incidencias: Incidencia[]
  /** Añade una incidencia ya impresa a la lista de verdad - lo llama el
   * padre cuando la impresora compartida termina de sacarla. */
  agregarIncidencia: (incidencia: Incidencia) => void
}

const POLL_MS = 10000

/** Solo el feed de incidencias (polling a /incidencias/pendientes + lista
 * asentada) - igual que useKitchenFeed, la impresión la gestiona la cola
 * compartida en App.tsx, no este hook. */
export function useIncidenciasFeed(onNuevaIncidencia: (incidencia: Incidencia) => void): IncidenciasFeed {
  const [incidencias, setIncidencias] = useState<Incidencia[]>([])
  const vistasRef = useRef<Set<string>>(new Set())
  const primeraCargaRef = useRef(true)

  const agregarIncidencia = useCallback((incidencia: Incidencia) => {
    setIncidencias((actuales) => [...actuales, incidencia])
  }, [])

  useEffect(() => {
    let cancelado = false

    async function cargar() {
      try {
        const respuesta = await fetch('/incidencias/pendientes')
        if (!respuesta.ok) return
        const datos: Incidencia[] = await respuesta.json()
        if (cancelado) return

        if (primeraCargaRef.current) {
          // Primera carga: las incidencias que ya existieran antes de abrir
          // el panel no son "nuevas" para esta sesión, así que se muestran
          // directamente sin pasar por la impresora (igual que el snapshot
          // inicial de tickets tampoco se reimprime).
          primeraCargaRef.current = false
          datos.forEach((i) => vistasRef.current.add(i.id))
          setIncidencias(datos)
          return
        }

        const nuevas = datos.filter((i) => !vistasRef.current.has(i.id))
        if (nuevas.length === 0) return
        nuevas.forEach((i) => vistasRef.current.add(i.id))
        nuevas.forEach(onNuevaIncidencia)
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
  }, [onNuevaIncidencia])

  return { incidencias, agregarIncidencia }
}
