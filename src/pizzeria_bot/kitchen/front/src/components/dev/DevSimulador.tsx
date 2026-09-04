import type { Ticket } from '../../types'

// Solo para desarrollo: Vite elimina este componente entero del build de
// producción (npm run build) gracias a `import.meta.env.DEV` - no hace
// falta acordarse de quitarlo a mano antes de publicar.

const EJEMPLOS: Ticket['resumen'][] = [
  {
    items: [
      { item_id: 1, pizza: 'pepperoni', tamano: 'familiar', cantidad: 1, precio_unidad: 13, subtotal: 13 },
      { item_id: 2, pizza: 'cuatro quesos', tamano: 'mediana', cantidad: 2, precio_unidad: 11, subtotal: 22 },
    ],
    tipo_entrega: 'domicilio',
    nombre_cliente: 'Javi',
    direccion: 'Avenida de las Ciencias, 35',
    telefono: '717700856',
    total: 35,
  },
  {
    items: [{ item_id: 1, pizza: 'margarita', tamano: 'mediana', cantidad: 1, precio_unidad: 8, subtotal: 8 }],
    tipo_entrega: 'recogida',
    nombre_cliente: 'Ana',
    direccion: null,
    telefono: '600111222',
    total: 8,
  },
]

interface Props {
  onSimular: (ticket: Ticket) => void
}

export function DevSimulador({ onSimular }: Props) {
  if (!import.meta.env.DEV) return null

  function simular() {
    const resumen = EJEMPLOS[Math.floor(Math.random() * EJEMPLOS.length)]
    onSimular({ id: crypto.randomUUID(), creado_en: new Date().toISOString(), resumen })
  }

  return (
    <button
      onClick={simular}
      style={{
        position: 'fixed',
        bottom: 20,
        right: 20,
        zIndex: 100,
        padding: '10px 16px',
        background: '#2563eb',
        color: '#fff',
        border: 'none',
        borderRadius: 6,
        fontFamily: 'sans-serif',
        fontSize: 13,
        cursor: 'pointer',
        boxShadow: '0 4px 10px rgba(0,0,0,0.4)',
      }}
    >
      🖨️ Simular pedido (dev)
    </button>
  )
}
