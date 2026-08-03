"""Utilidades compartidas del módulo rassa."""


def nombre_completo(usuario):
    """Retorna el nombre completo de un usuario a partir de su Persona.

    Usado por múltiples serializers (pagos, liquidaciones, etc.).
    """
    if usuario and usuario.fk_persona:
        p = usuario.fk_persona
        return f"{p.nombre} {p.apellido_paterno}".strip()
    return None
