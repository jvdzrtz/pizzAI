from pydantic import BaseModel


class PizzaMenuItem(BaseModel):
    nombre: str
    precio_mediana: float
    precio_familiar: float
    ingredientes: str

    def precio(self, tamano: str) -> float:
        if tamano == "mediana":
            return self.precio_mediana
        if tamano == "familiar":
            return self.precio_familiar
        raise ValueError(f"Tamaño desconocido: {tamano}")


MENU: dict[str, PizzaMenuItem] = {
    "margarita": PizzaMenuItem(
        nombre="margarita",
        precio_mediana=8.0,
        precio_familiar=11.0,
        ingredientes="tomate, mozzarella, albahaca",
    ),
    "pepperoni": PizzaMenuItem(
        nombre="pepperoni",
        precio_mediana=10.0,
        precio_familiar=13.0,
        ingredientes="tomate, mozzarella, pepperoni",
    ),
    "cuatro quesos": PizzaMenuItem(
        nombre="cuatro quesos",
        precio_mediana=11.0,
        precio_familiar=14.0,
        ingredientes="mozzarella, gorgonzola, parmesano, provolone",
    ),
    "vegetal": PizzaMenuItem(
        nombre="vegetal",
        precio_mediana=9.0,
        precio_familiar=12.0,
        ingredientes="pimiento, cebolla, champiñón, aceituna",
    ),
}


def menu_as_dict() -> dict:
    """Representación plana del menú, lista para devolver al modelo como resultado de tool."""
    return {nombre: item.model_dump() for nombre, item in MENU.items()}
