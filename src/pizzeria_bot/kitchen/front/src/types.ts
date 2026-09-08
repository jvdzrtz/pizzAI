// Estos tipos reflejan exactamente lo que manda el backend (ver
// kitchen/store.py: Ticket, y domain/order.py: Order.confirmar()).

export type TipoEntrega = 'recogida' | 'domicilio'

export interface OrderItem {
  item_id: number
  pizza: string
  tamano: string
  cantidad: number
  precio_unidad: number
  subtotal: number
}

export interface Resumen {
  items: OrderItem[]
  tipo_entrega: TipoEntrega
  nombre_cliente: string | null
  direccion: string | null
  telefono: string | null
  total: number
}

export interface Ticket {
  id: string
  creado_en: string
  resumen: Resumen
}

export type MensajeServidor =
  | { event: 'snapshot'; tickets: Ticket[] }
  | { event: 'nuevo_ticket'; ticket: Ticket }

// Ver agents/complaint_graph.py: Incidencia - solo las quejas escaladas a
// revisión humana llegan a existir como tal (las menores se resuelven solas
// y no se guardan).
export interface Incidencia {
  id: string
  nombre_cliente: string | null
  pedido: string | null
  tipo_incidencia: string
  decision_tomada: string
  estado: string
}

// Pedidos e incidencias comparten una única impresora física (ver
// hooks/useColaImpresion.ts) - este tipo es lo que viaja por esa cola.
export type ItemImprimible =
  | { tipo: 'ticket'; ticket: Ticket }
  | { tipo: 'incidencia'; incidencia: Incidencia }
