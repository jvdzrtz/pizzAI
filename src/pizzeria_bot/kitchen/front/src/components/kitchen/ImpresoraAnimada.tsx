import { useEffect, useRef, useState, type ReactNode } from 'react'
import './Printer.css'

interface Props<T> {
  item: T | null
  idDe: (item: T) => string
  /** Se llama cuando termina toda la secuencia (parpadeo + papel +
   * pausa) - el padre mueve el item a su lista definitiva en ese momento. */
  onDone: () => void
  children: (item: T) => ReactNode
}

const PARPADEO_MS = 250
const SACAR_PAPEL_MS = 1900
const PAUSA_FINAL_MS = 350

/** La impresora física (Printer.tsx la usaba en exclusiva para tickets de
 * pedido) generalizada para imprimir cualquier cosa que se pueda "sacar en
 * papel" - ahora también las incidencias (ver PanelIncidencias.tsx). La
 * mecánica de la animación es idéntica, solo cambia qué se dibuja dentro. */
export function ImpresoraAnimada<T>({ item, idDe, onDone, children }: Props<T>) {
  const medidorRef = useRef<HTMLDivElement>(null)
  const [altura, setAltura] = useState(0)
  const [imprimiendo, setImprimiendo] = useState(false)
  const [saliendo, setSaliendo] = useState(false)

  useEffect(() => {
    if (!item) {
      setAltura(0)
      setImprimiendo(false)
      setSaliendo(false)
      return
    }

    setImprimiendo(true)
    setAltura(0)
    setSaliendo(false)

    // Fase 1 (parpadeo): un flash breve antes de sacar el papel, para que
    // se note que "empieza a imprimir" y no aparece de golpe. El contenido
    // ya está montado (oculto por altura: 0), así que medirlo aquí da su
    // altura real.
    const t1 = setTimeout(() => {
      setAltura(medidorRef.current?.scrollHeight ?? 0)
      setSaliendo(true)
    }, PARPADEO_MS)

    // Fase 2: el papel termina de salir - quitamos el temblor mecánico
    // (ya no tiene sentido una vez el papel está quieto y completo).
    const t2 = setTimeout(() => {
      setSaliendo(false)
    }, PARPADEO_MS + SACAR_PAPEL_MS)

    // Fase 3: tras una pequeña pausa, avisamos al padre - a partir de ahí
    // el item pasa a vivir en su lista, con su propia animación de caída
    // al asentarse.
    const t3 = setTimeout(
      () => {
        setImprimiendo(false)
        onDone()
      },
      PARPADEO_MS + SACAR_PAPEL_MS + PAUSA_FINAL_MS,
    )

    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
    // Solo debe reiniciar la secuencia cuando cambia el item en sí, no en
    // cada render (onDone se recrea con cada snapshot).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item ? idDe(item) : null])

  return (
    <div className="impresora">
      <div className={`impresora-cuerpo${imprimiendo ? ' imprimiendo' : ''}`}>
        <span className="impresora-etiqueta" />
        <span className="impresora-luz" />
      </div>
      <div className="impresora-bandeja">
        <div className="impresora-ranura" />
      </div>

      <div
        className={`impresora-papel${saliendo ? ' saliendo' : ''}`}
        style={{ height: altura, transitionDuration: `${SACAR_PAPEL_MS}ms` }}
      >
        {item && <div ref={medidorRef}>{children(item)}</div>}
      </div>
    </div>
  )
}
