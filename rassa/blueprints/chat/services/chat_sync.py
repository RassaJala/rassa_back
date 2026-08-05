"""Sincronización entre Familias y Chat (FASE 1).

Funciones puras de ORM: idempotentes, sin HTTP. Seguridad para llamarse
repetidamente. Usar transaction.atomic() donde muta varias filas.
"""

from django.db import transaction
from django.db.models import Case, Value, When

from rassa.models import Conversacion, Familia, FamiliaUsuario, Integrante, Usuario


def _get_or_reactivate_integrante(usuario, conversacion, *, rol="miembro"):
    """Crea o reactiva un Integrante preservando su rol existente.

    Al reactivar, actualiza el rol si se pasó uno distinto (necesario para que
    ``restore_family_chat``/asignar-jefe fijen el admin correctamente).

    ponytail: duplicated from views to avoid circular import.
    """
    integrante = Integrante.objects.filter(fk_usuario=usuario, fk_conversacion=conversacion).first()
    if integrante:
        if not integrante.estado or integrante.rol != rol:
            integrante.estado = True
            integrante.rol = rol
            integrante.save(update_fields=["estado", "rol"])
        return integrante
    return Integrante.objects.create(fk_usuario=usuario, fk_conversacion=conversacion, rol=rol)


@transaction.atomic
def ensure_family_chat(familia_pk, *, nombre=None, activo=True):
    """Devuelve la conversación grupal activa de la familia. Idempotente.

    Si activo=True y no existe, la crea y agrega como Integrantes a los
    miembros activos (FamiliaUsuario.estado=True). El jefe queda como admin.
    Si activo=False, NO crea: devolver None (archivar usa deactivate_*).
    """
    if not activo:
        return Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()

    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()
    if conv is None:
        if nombre is None:
            familia = Familia.objects.filter(pk=familia_pk).first()
            nombre = familia.nombre_familia if familia else ""
        conv = Conversacion.objects.create(tipo=True, nombre=nombre, fk_familia_id=familia_pk, estado=True)

    jefe_pk = None
    familia = Familia.objects.filter(pk=familia_pk).first()
    if familia and familia.fk_jefe_familia_id is not None:
        jefe_pk = familia.fk_jefe_familia_id

    for fu in FamiliaUsuario.objects.filter(fk_familia=familia_pk, estado=True):
        rol = "admin" if fu.fk_usuario_id == jefe_pk else "miembro"
        _get_or_reactivate_integrante(fu.fk_usuario, conv, rol=rol)

    return conv


@transaction.atomic
def sync_family_chat_name(familia_pk, nombre):
    """Si la conv familiar activa no tiene override, sincroniza su nombre."""
    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()
    if conv is None or conv.nombre_override:
        return
    conv.nombre = nombre
    conv.save(update_fields=["nombre"])


@transaction.atomic
def add_family_member(familia_pk, usuario_pk, *, jefe=False):
    """Asegura la conv familiar y agrega/reactiva un miembro con su rol."""
    conv = ensure_family_chat(familia_pk)
    if conv is None:
        return None
    usuario = Usuario.objects.filter(pk=usuario_pk).first()
    if usuario is None:
        return None
    _get_or_reactivate_integrante(usuario, conv, rol="admin" if jefe else "miembro")
    return conv


@transaction.atomic
def remove_family_member(familia_pk, usuario_pk):
    """Archiva (estado=False) el integrante de la conv familiar. Idempotente.

    También resetea el rol a miembro para evitar que un jefe removido conserve
    admin si la fila se reactivara.
    """
    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()
    if conv is None:
        return 0
    return Integrante.objects.filter(
        fk_conversacion=conv,
        fk_usuario_id=usuario_pk,
    ).update(estado=False, rol="miembro")


@transaction.atomic
def deactivate_family_chat(familia_pk):
    """Desactiva la conv familiar y todos sus integrantes. Idempotente."""
    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()
    if conv is None:
        return False
    Integrante.objects.filter(fk_conversacion=conv).update(estado=False)
    conv.estado = False
    conv.save(update_fields=["estado"])
    return True


@transaction.atomic
def restore_family_chat(familia_pk):
    """Reactiva la conv familiar y re-agrega a los miembros activos. Idempotente.

    Si no existe conv inactiva, delega en ``ensure_family_chat`` (crea una nueva).
    """
    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=False).first()
    if conv is None:
        return ensure_family_chat(familia_pk)
    conv.estado = True
    conv.save(update_fields=["estado"])

    jefe_pk = None
    familia = Familia.objects.filter(pk=familia_pk).first()
    if familia and familia.fk_jefe_familia_id is not None:
        jefe_pk = familia.fk_jefe_familia_id

    for fu in FamiliaUsuario.objects.filter(fk_familia=familia_pk, estado=True):
        rol = "admin" if fu.fk_usuario_id == jefe_pk else "miembro"
        _get_or_reactivate_integrante(fu.fk_usuario, conv, rol=rol)

    return conv


@transaction.atomic
def sync_family_roles(familia_pk):
    """Ajusta el rol de los Integrantes activos de la conv familiar según el jefe actual.

    Idempotente: no crea conv, no toca integrantes inactivos.
    """
    conv = Conversacion.objects.filter(fk_familia=familia_pk, estado=True).first()
    if conv is None:
        return
    jefe_pk = None
    familia = Familia.objects.filter(pk=familia_pk).first()
    if familia and familia.fk_jefe_familia_id is not None:
        jefe_pk = familia.fk_jefe_familia_id
    if jefe_pk:
        Integrante.objects.filter(fk_conversacion=conv, estado=True).update(
            rol=Case(
                When(fk_usuario_id=jefe_pk, then=Value("admin")),
                default=Value("miembro"),
            )
        )
    else:
        Integrante.objects.filter(fk_conversacion=conv, estado=True).update(rol="miembro")
