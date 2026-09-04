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
