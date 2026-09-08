import { useCallback, useRef, useState } from 'react'

interface ColaImpresion<T> {
  /** El item que está "imprimiéndose" ahora mismo en la máquina física, o
   * null si está libre. */
  actual: T | null
  /** Mete un item en la cola. Si la impresora está libre, empieza a
   * imprimirlo ya; si no, espera su turno detrás de lo que haya. */
  encolar: (item: T) => void
  /** El componente de la impresora llama a esto cuando termina su
   * animación - procesa el item que acaba de salir con `procesar` y
   * arranca el siguiente de la cola si hay. */
  onDone: (procesar: (item: T) => void) => void
}

/** Cola FIFO de una única impresora física compartida por varias fuentes
 * (pedidos por WebSocket, incidencias por polling, el simulador de
 * desarrollo...). Solo hay una máquina: si algo llega mientras se está
 * imprimiendo otra cosa, espera su turno en orden de llegada - nunca se
 * pisan ni se cortan animaciones a medias. */
export function useColaImpresion<T>(): ColaImpresion<T> {
  const [actual, setActual] = useState<T | null>(null)
  const actualRef = useRef<T | null>(null)
  const colaRef = useRef<T[]>([])

  const siguiente = useCallback(() => {
    const item = colaRef.current.shift() ?? null
    actualRef.current = item
    setActual(item)
  }, [])

  const encolar = useCallback((item: T) => {
    if (actualRef.current) {
      colaRef.current.push(item)
    } else {
      actualRef.current = item
      setActual(item)
    }
  }, [])

  const onDone = useCallback(
    (procesar: (item: T) => void) => {
      const item = actualRef.current
      if (!item) return
      procesar(item)
      siguiente()
    },
    [siguiente],
  )

  return { actual, encolar, onDone }
}
