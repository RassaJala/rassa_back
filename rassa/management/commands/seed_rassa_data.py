# pylint: disable=too-many-lines
"""Django management command para cargar datos de prueba (seeders).

Equivalente a los INSERT de db/rassa_jala.sql pero usando Django ORM.
Ejecuta: python manage.py seed_rassa_data

Flags:
  --clear   Elimina todos los datos antes de insertar (fresh start).
"""

import math
import struct
import wave
import zlib
from datetime import datetime as dt
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from rassa.models import (
    CategoriaProducto,
    Conversacion,
    Corte,
    DecisionMerma,
    DetallePedido,
    Documento,
    EstadoPedido,
    Familia,
    FamiliaUsuario,
    HistorialEstadoPedido,
    Integrante,
    LimiteCliente,
    Liquidacion,
    Localidad,
    Log,
    Mensaje,
    MensajeDocumento,
    Merma,
    Municipio,
    Pago,
    PedidoCabecera,
    Persona,
    Producto,
    ProductoImagen,
    ProductoSemanal,
    PublicacionSemanal,
    Recibo,
    Recoleccion,
    Rol,
    TipoPago,
    Unidad,
    Usuario,
)


def _write_tone_wav(path: Path, seconds: float = 3.0, freq: int = 440, rate: int = 22050) -> None:
    """Genera un tono WAV (mono, 16-bit PCM) para el audio demo del seed."""
    if path.exists():
        return
    frames = []
    for i in range(int(rate * seconds)):
        value = int(0.4 * 32767 * math.sin(2 * math.pi * freq * i / rate))
        frames.append(struct.pack("<h", value))
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"".join(frames))


def _write_solid_png(path: Path, rgb: tuple[int, int, int], size: int = 320) -> None:
    """Genera un PNG solido (truecolor) para las imagenes demo del seed."""
    if path.exists():
        return

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)

    row = b"\x00" + bytes(rgb) * size
    raw = row * size
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw)))
        f.write(chunk(b"IEND", b""))


class Command(BaseCommand):
    """Carga datos de prueba para las 32 tablas de Rassa."""

    help = "Carga datos de prueba para las 32 tablas de Rassa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            dest="clear",
            default=False,
            help="Elimina todos los datos antes de insertar.",
        )

    def handle(self, *args, **options):
        clear = options["clear"]

        if clear:
            self.stdout.write("Eliminando datos existentes...")
            self._clear_all()

        self.stdout.write("Cargando datos de prueba...")

        with transaction.atomic():
            self._seed_roles()
            self._seed_categorias()
            self._seed_unidades()
            self._seed_estados_pedido()
            self._seed_decisiones_merma()
            self._seed_tipos_pago()
            self._seed_municipios()
            self._seed_localidades()
            self._seed_personas()
            self._seed_usuarios()
            self._seed_familias()
            self._seed_familia_usuarios()
            self._seed_limites_cliente()
            self._seed_productos()
            self._seed_publicaciones_semanales()
            self._seed_productos_semanales()
            self._seed_pedidos()
            self._seed_detalles_pedido()
            self._seed_pagos()
            self._seed_cortes()
            self._seed_historial_estado_pedido()
            self._seed_mermas()
            self._seed_logs()
            self._seed_conversaciones()
            self._seed_integrantes()
            self._seed_mensajes()
            self._seed_documentos()
            self._seed_mensajes_documentos()
            self._seed_producto_imagenes()
            self._seed_recoleccion()
            self._seed_recibos()
            self._seed_liquidaciones()

        self.stdout.write(self.style.SUCCESS("Datos de prueba cargados exitosamente."))

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_all(self):
        models = [
            Liquidacion,
            Recibo,
            Recoleccion,
            ProductoImagen,
            MensajeDocumento,
            Documento,
            Mensaje,
            Integrante,
            Conversacion,
            Merma,
            HistorialEstadoPedido,
            Corte,
            Pago,
            DetallePedido,
            PedidoCabecera,
            ProductoSemanal,
            PublicacionSemanal,
            Producto,
            LimiteCliente,
            FamiliaUsuario,
            Familia,
            Log,
            Usuario,
            Persona,
            Localidad,
            Municipio,
            TipoPago,
            DecisionMerma,
            EstadoPedido,
            Unidad,
            CategoriaProducto,
            Rol,
        ]
        User = get_user_model()
        for model in models:
            model.objects.all().delete()
        User.objects.all().delete()

    # ------------------------------------------------------------------
    # 1. TABLAS BASE
    # ------------------------------------------------------------------

    def _seed_roles(self):
        roles = [
            {
                "id_rol": 1,
                "nombre_rol": "Admin",
                "descripcion": ("Administrador del sistema. " + "Acceso total a todas las funciones."),
            },
            {
                "id_rol": 2,
                "nombre_rol": "Vendedor",
                "descripcion": ("Personal de la universidad. Gestiona pedidos, pagos, mermas y recolección."),
            },
            {
                "id_rol": 3,
                "nombre_rol": "Agricultor",
                "descripcion": ("Productor del campo. Publica sus productos los lunes y coordina la recolección."),
            },
            {
                "id_rol": 4,
                "nombre_rol": "Cliente",
                "descripcion": ("Comprador. Ve productos, " + "compra y chatea con agricultores."),
            },
        ]
        for r in roles:
            Rol.objects.update_or_create(id_rol=r["id_rol"], defaults=r)
        self.stdout.write("  Roles: OK")

    def _seed_categorias(self):
        cats = [
            {
                "id_categoria": 1,
                "nombre": "Verduras",
                "descripcion": "Verduras frescas del campo",
            },
            {
                "id_categoria": 2,
                "nombre": "Frutas",
                "descripcion": "Frutas de temporada",
            },
            {
                "id_categoria": 3,
                "nombre": "Lácteos",
                "descripcion": "Quesos, crema, leche y derivados",
            },
            {
                "id_categoria": 4,
                "nombre": "Legumbres",
                "descripcion": "Frijol, lenteja, garbanzo y similares",
            },
            {
                "id_categoria": 5,
                "nombre": "Hierbas y Especias",
                "descripcion": "Cilantro, perejil, hierbabuena, etc.",
            },
            {
                "id_categoria": 6,
                "nombre": "Tubérculos",
                "descripcion": "Papa, camote, zanahoria, betabel",
            },
        ]
        for c in cats:
            CategoriaProducto.objects.update_or_create(id_categoria=c["id_categoria"], defaults=c)
        self.stdout.write("  Categorías: OK")

    def _reset_pk_sequence(self, model):
        """Ajusta la secuencia de PostgreSQL tras insertar IDs fijos."""
        if connection.vendor != "postgresql":
            return

        table = connection.ops.quote_name(model._meta.db_table)
        pk = connection.ops.quote_name(model._meta.pk.column)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE((SELECT MAX({pk}) FROM {table}), 1), true)",
                [model._meta.db_table, model._meta.pk.column],
            )

    def _seed_unidades(self):
        unidades = [
            {
                "id_unidad": 1,
                "tipo": "Kilogramo",
                "nombre": "Kilogramo",
                "abreviatura": "kg",
            },
            {
                "id_unidad": 2,
                "tipo": "Pieza",
                "nombre": "Pieza",
                "abreviatura": "pz",
            },
            {
                "id_unidad": 3,
                "tipo": "Manojo",
                "nombre": "Manojo",
                "abreviatura": "mj",
            },
            {
                "id_unidad": 4,
                "tipo": "Litro",
                "nombre": "Litro",
                "abreviatura": "L",
            },
            {
                "id_unidad": 5,
                "tipo": "Docena",
                "nombre": "Docena",
                "abreviatura": "doc",
            },
        ]
        for u in unidades:
            Unidad.objects.update_or_create(id_unidad=u["id_unidad"], defaults=u)
        self._reset_pk_sequence(Unidad)
        self.stdout.write("  Unidades: OK")

    def _seed_estados_pedido(self):
        estados = [
            {
                "id_estado": 1,
                "tipo_estado": "pendiente",
                "descripcion": "El cliente realizó el pedido, esperando confirmación",
            },
            {
                "id_estado": 2,
                "tipo_estado": "confirmado",
                "descripcion": "El vendedor confirmó el pedido",
            },
            {
                "id_estado": 3,
                "tipo_estado": "en_preparacion",
                "descripcion": "El vendedor está preparando los productos",
            },
            {
                "id_estado": 4,
                "tipo_estado": "listo_para_retirar",
                "descripcion": "El pedido está listo, el cliente puede pasar por él",
            },
            {
                "id_estado": 5,
                "tipo_estado": "entregado",
                "descripcion": "El cliente recogió el pedido",
            },
            {
                "id_estado": 6,
                "tipo_estado": "cancelado",
                "descripcion": "El pedido fue cancelado",
            },
            {
                "id_estado": 7,
                "tipo_estado": "activo",
                "descripcion": "El apartado/pedido está activo en el sistema",
            },
        ]
        for e in estados:
            EstadoPedido.objects.update_or_create(id_estado=e["id_estado"], defaults=e)
        self.stdout.write("  Estados de pedido: OK")

    def _seed_decisiones_merma(self):
        decisiones = [
            {"id_decision": 1, "decision": "Donar"},
            {"id_decision": 2, "decision": "Desechar"},
            {"id_decision": 3, "decision": "Vender más barato"},
            {"id_decision": 4, "decision": "Compostar"},
        ]
        for d in decisiones:
            DecisionMerma.objects.update_or_create(id_decision=d["id_decision"], defaults=d)
        self.stdout.write("  Decisiones de merma: OK")

    def _seed_tipos_pago(self):
        tipos = [
            {"id_tipo_pago": 1, "nombre": "Efectivo"},
            {"id_tipo_pago": 2, "nombre": "Transferencia"},
            {"id_tipo_pago": 3, "nombre": "Depósito"},
        ]
        for t in tipos:
            TipoPago.objects.update_or_create(id_tipo_pago=t["id_tipo_pago"], defaults=t)
        self.stdout.write("  Tipos de pago: OK")

    # ------------------------------------------------------------------
    # 2. MUNICIPIO Y LOCALIDAD (Nayarit)
    # ------------------------------------------------------------------

    def _seed_municipios(self):
        municipios = [
            {"id_municipio": 1, "nombre": "Acaponeta"},
            {"id_municipio": 2, "nombre": "Ahuacatlán"},
            {"id_municipio": 3, "nombre": "Amatlán de Cañas"},
            {"id_municipio": 4, "nombre": "Bahía de Banderas"},
            {"id_municipio": 5, "nombre": "Compostela"},
            {"id_municipio": 6, "nombre": "Del Nayar"},
            {"id_municipio": 7, "nombre": "Huajicori"},
            {"id_municipio": 8, "nombre": "Ixtlán del Río"},
            {"id_municipio": 9, "nombre": "Jala"},
            {"id_municipio": 10, "nombre": "La Yesca"},
            {"id_municipio": 11, "nombre": "Rosamorada"},
            {"id_municipio": 12, "nombre": "Ruiz"},
            {"id_municipio": 13, "nombre": "San Blas"},
            {"id_municipio": 14, "nombre": "San Pedro Lagunillas"},
            {"id_municipio": 15, "nombre": "Santa María del Oro"},
            {"id_municipio": 16, "nombre": "Santiago Ixcuintla"},
            {"id_municipio": 17, "nombre": "Tecuala"},
            {"id_municipio": 18, "nombre": "Tepic"},
            {"id_municipio": 19, "nombre": "Tuxpan"},
            {"id_municipio": 20, "nombre": "Xalisco"},
        ]
        for m in municipios:
            Municipio.objects.update_or_create(id_municipio=m["id_municipio"], defaults=m)
        self.stdout.write("  Municipios: OK (Nayarit)")

    def _seed_localidades(self):
        localidades = [
            # Acaponeta (id=1)
            {"id_localidad": 1, "nombre": "Acaponeta", "fk_municipio_id": 1},
            {"id_localidad": 2, "nombre": "Sayulilla", "fk_municipio_id": 1},
            {"id_localidad": 3, "nombre": "La Guásima", "fk_municipio_id": 1},
            {"id_localidad": 4, "nombre": "San José de Gracia", "fk_municipio_id": 1},
            {"id_localidad": 5, "nombre": "El Centenario", "fk_municipio_id": 1},
            # Ahuacatlán (id=2)
            {"id_localidad": 6, "nombre": "Ahuacatlán", "fk_municipio_id": 2},
            {"id_localidad": 7, "nombre": "Uzeta", "fk_municipio_id": 2},
            {"id_localidad": 8, "nombre": "El Rosario", "fk_municipio_id": 2},
            {"id_localidad": 9, "nombre": "Mecatán", "fk_municipio_id": 2},
            # Amatlán de Cañas (id=3)
            {"id_localidad": 10, "nombre": "Amatlán de Cañas", "fk_municipio_id": 3},
            {"id_localidad": 11, "nombre": "El Divisadero", "fk_municipio_id": 3},
            {"id_localidad": 12, "nombre": "Lagunillas", "fk_municipio_id": 3},
            {"id_localidad": 13, "nombre": "El Naranjo", "fk_municipio_id": 3},
            # Bahía de Banderas (id=4)
            {"id_localidad": 14, "nombre": "Valle de Banderas", "fk_municipio_id": 4},
            {"id_localidad": 15, "nombre": "San José del Valle", "fk_municipio_id": 4},
            {"id_localidad": 16, "nombre": "Bucerías", "fk_municipio_id": 4},
            {"id_localidad": 17, "nombre": "Mezcales", "fk_municipio_id": 4},
            {"id_localidad": 18, "nombre": "Jarretadera", "fk_municipio_id": 4},
            {"id_localidad": 19, "nombre": "Cruz de Huanacaxtle", "fk_municipio_id": 4},
            {"id_localidad": 20, "nombre": "Nuevo Nayarit", "fk_municipio_id": 4},
            {"id_localidad": 21, "nombre": "San Vicente", "fk_municipio_id": 4},
            # Compostela (id=5)
            {"id_localidad": 22, "nombre": "Compostela", "fk_municipio_id": 5},
            {"id_localidad": 23, "nombre": "Las Varas", "fk_municipio_id": 5},
            {"id_localidad": 24, "nombre": "La Peñita de Jaltemba", "fk_municipio_id": 5},
            {"id_localidad": 25, "nombre": "Zacualpan", "fk_municipio_id": 5},
            {"id_localidad": 26, "nombre": "Rincón de Guayabitos", "fk_municipio_id": 5},
            {"id_localidad": 27, "nombre": "Monteón", "fk_municipio_id": 5},
            {"id_localidad": 28, "nombre": "Ixtapa de la Concepción", "fk_municipio_id": 5},
            {"id_localidad": 29, "nombre": "Mazatán", "fk_municipio_id": 5},
            # Del Nayar (id=6)
            {"id_localidad": 30, "nombre": "Jesús María", "fk_municipio_id": 6},
            {"id_localidad": 31, "nombre": "Mesa del Nayar", "fk_municipio_id": 6},
            {"id_localidad": 32, "nombre": "Santa Teresa", "fk_municipio_id": 6},
            {"id_localidad": 33, "nombre": "Linda Vista", "fk_municipio_id": 6},
            {"id_localidad": 34, "nombre": "La Mesa", "fk_municipio_id": 6},
            # Huajicori (id=7)
            {"id_localidad": 35, "nombre": "Huajicori", "fk_municipio_id": 7},
            {"id_localidad": 36, "nombre": "Acatita", "fk_municipio_id": 7},
            {"id_localidad": 37, "nombre": "Mineral de Cucharas", "fk_municipio_id": 7},
            {"id_localidad": 38, "nombre": "El Arrayán", "fk_municipio_id": 7},
            {"id_localidad": 39, "nombre": "El Limón", "fk_municipio_id": 7},
            # Ixtlán del Río (id=8)
            {"id_localidad": 40, "nombre": "Ixtlán del Río", "fk_municipio_id": 8},
            {"id_localidad": 41, "nombre": "El Zoquite", "fk_municipio_id": 8},
            {"id_localidad": 42, "nombre": "La Cantera", "fk_municipio_id": 8},
            {"id_localidad": 43, "nombre": "San José de Gracia", "fk_municipio_id": 8},
            # Jala (id=9)
            {"id_localidad": 44, "nombre": "Jala", "fk_municipio_id": 9},
            {"id_localidad": 45, "nombre": "Atonalisco", "fk_municipio_id": 9},
            {"id_localidad": 46, "nombre": "Pochotitán", "fk_municipio_id": 9},
            {"id_localidad": 47, "nombre": "Los Pozos", "fk_municipio_id": 9},
            {"id_localidad": 48, "nombre": "El Águila", "fk_municipio_id": 9},
            # La Yesca (id=10)
            {"id_localidad": 49, "nombre": "La Yesca", "fk_municipio_id": 10},
            {"id_localidad": 50, "nombre": "Huayanmotita", "fk_municipio_id": 10},
            {"id_localidad": 51, "nombre": "Zoquipilla", "fk_municipio_id": 10},
            {"id_localidad": 52, "nombre": "Guayabitos", "fk_municipio_id": 10},
            # Rosamorada (id=11)
            {"id_localidad": 53, "nombre": "Rosamorada", "fk_municipio_id": 11},
            {"id_localidad": 54, "nombre": "San Vicente", "fk_municipio_id": 11},
            {"id_localidad": 55, "nombre": "Chacalilla", "fk_municipio_id": 11},
            {"id_localidad": 56, "nombre": "El Colorado", "fk_municipio_id": 11},
            {"id_localidad": 57, "nombre": "Callejones", "fk_municipio_id": 11},
            # Ruiz (id=12)
            {"id_localidad": 58, "nombre": "Ruiz", "fk_municipio_id": 12},
            {"id_localidad": 59, "nombre": "Paso Hondo", "fk_municipio_id": 12},
            {"id_localidad": 60, "nombre": "El Falcón", "fk_municipio_id": 12},
            {"id_localidad": 61, "nombre": "La Loma", "fk_municipio_id": 12},
            # San Blas (id=13)
            {"id_localidad": 62, "nombre": "San Blas", "fk_municipio_id": 13},
            {"id_localidad": 63, "nombre": "Matanchén", "fk_municipio_id": 13},
            {"id_localidad": 64, "nombre": "Aticama", "fk_municipio_id": 13},
            {"id_localidad": 65, "nombre": "El Llano", "fk_municipio_id": 13},
            {"id_localidad": 66, "nombre": "La Contaduría", "fk_municipio_id": 13},
            # San Pedro Lagunillas (id=14)
            {"id_localidad": 67, "nombre": "San Pedro Lagunillas", "fk_municipio_id": 14},
            {"id_localidad": 68, "nombre": "Estación de San Pedro", "fk_municipio_id": 14},
            {"id_localidad": 69, "nombre": "La Presa", "fk_municipio_id": 14},
            # Santa María del Oro (id=15)
            {"id_localidad": 70, "nombre": "Santa María del Oro", "fk_municipio_id": 15},
            {"id_localidad": 71, "nombre": "Venustiano Carranza", "fk_municipio_id": 15},
            {"id_localidad": 72, "nombre": "La Mojonera", "fk_municipio_id": 15},
            {"id_localidad": 73, "nombre": "Cerro Pelón", "fk_municipio_id": 15},
            {"id_localidad": 74, "nombre": "El Llano", "fk_municipio_id": 15},
            # Santiago Ixcuintla (id=16)
            {"id_localidad": 75, "nombre": "Santiago Ixcuintla", "fk_municipio_id": 16},
            {"id_localidad": 76, "nombre": "Mexcaltitán", "fk_municipio_id": 16},
            {"id_localidad": 77, "nombre": "Villa Juárez", "fk_municipio_id": 16},
            {"id_localidad": 78, "nombre": "Puerta de Palapares", "fk_municipio_id": 16},
            {"id_localidad": 79, "nombre": "Pozo de Ibarra", "fk_municipio_id": 16},
            # Tecuala (id=17)
            {"id_localidad": 80, "nombre": "Tecuala", "fk_municipio_id": 17},
            {"id_localidad": 81, "nombre": "Milpas Viejas", "fk_municipio_id": 17},
            {"id_localidad": 82, "nombre": "La Toje", "fk_municipio_id": 17},
            {"id_localidad": 83, "nombre": "Quimichis", "fk_municipio_id": 17},
            # Tepic (id=18)
            {"id_localidad": 84, "nombre": "Tepic", "fk_municipio_id": 18},
            {"id_localidad": 85, "nombre": "Francisco I. Madero", "fk_municipio_id": 18},
            {"id_localidad": 86, "nombre": "San Cayetano", "fk_municipio_id": 18},
            {"id_localidad": 87, "nombre": "Camichín de Jauja", "fk_municipio_id": 18},
            {"id_localidad": 88, "nombre": "Bellavista", "fk_municipio_id": 18},
            {"id_localidad": 89, "nombre": "Santiago de Pochotitán", "fk_municipio_id": 18},
            {"id_localidad": 90, "nombre": "Atonalisco", "fk_municipio_id": 18},
            {"id_localidad": 91, "nombre": "Lo de Lamedo", "fk_municipio_id": 18},
            # Tuxpan (id=19)
            {"id_localidad": 92, "nombre": "Tuxpan", "fk_municipio_id": 19},
            {"id_localidad": 93, "nombre": "Peñas", "fk_municipio_id": 19},
            {"id_localidad": 94, "nombre": "Palma Grande", "fk_municipio_id": 19},
            {"id_localidad": 95, "nombre": "El Tecomate", "fk_municipio_id": 19},
            # Xalisco (id=20)
            {"id_localidad": 96, "nombre": "Xalisco", "fk_municipio_id": 20},
            {"id_localidad": 97, "nombre": "El Rodeo", "fk_municipio_id": 20},
            {"id_localidad": 98, "nombre": "Colonia la Presa", "fk_municipio_id": 20},
            {"id_localidad": 99, "nombre": "Los Sauces", "fk_municipio_id": 20},
        ]
        for loc in localidades:
            Localidad.objects.update_or_create(id_localidad=loc["id_localidad"], defaults=loc)
        self.stdout.write("  Localidades: OK (Nayarit)")

    # ------------------------------------------------------------------
    # 3. PERSONAS Y USUARIOS
    # ------------------------------------------------------------------

    def _seed_personas(self):
        personas = [
            {
                "id_persona": 1,
                "nombre": "Juan",
                "apellido_paterno": "Pérez",
                "apellido_materno": "García",
                "fecha_nacimiento": "1985-03-15",
                "sexo": "M",
                "domicilio": "Av. Principal 123",
                "fk_localidad_id": 1,  # Acaponeta
            },
            {
                "id_persona": 2,
                "nombre": "María",
                "apellido_paterno": "López",
                "apellido_materno": "Hernández",
                "fecha_nacimiento": "1990-07-22",
                "sexo": "F",
                "domicilio": "Calle Hidalgo 45",
                "fk_localidad_id": 14,  # Valle de Banderas
            },
            {
                "id_persona": 3,
                "nombre": "Pedro",
                "apellido_paterno": "González",
                "apellido_materno": "Martínez",
                "fecha_nacimiento": "1978-11-08",
                "sexo": "M",
                "domicilio": "Benito Juárez 78",
                "fk_localidad_id": 30,  # Jesús María, Del Nayar
            },
            {
                "id_persona": 4,
                "nombre": "Ana",
                "apellido_paterno": "Ramírez",
                "apellido_materno": "Cruz",
                "fecha_nacimiento": "1995-02-14",
                "sexo": "F",
                "domicilio": "Zaragoza 12",
                "fk_localidad_id": 22,  # Compostela
            },
            {
                "id_persona": 5,
                "nombre": "José",
                "apellido_paterno": "Sánchez",
                "apellido_materno": "Flores",
                "fecha_nacimiento": "1982-09-30",
                "sexo": "M",
                "domicilio": "Allende 56",
                "fk_localidad_id": 40,  # Ixtlán del Río
            },
            {
                "id_persona": 6,
                "nombre": "Rosa",
                "apellido_paterno": "Martínez",
                "apellido_materno": "Gómez",
                "fecha_nacimiento": "1988-06-18",
                "sexo": "F",
                "domicilio": "Morelos 34",
                "fk_localidad_id": 2,  # Sayulilla, Acaponeta
            },
            {
                "id_persona": 7,
                "nombre": "Carlos",
                "apellido_paterno": "Hernández",
                "apellido_materno": "Luna",
                "fecha_nacimiento": "1992-12-25",
                "sexo": "M",
                "domicilio": "Insurgentes 90",
                "fk_localidad_id": 44,  # Jala
            },
            {
                "id_persona": 8,
                "nombre": "Sofía",
                "apellido_paterno": "Torres",
                "apellido_materno": "Vázquez",
                "fecha_nacimiento": "1997-04-03",
                "sexo": "F",
                "domicilio": "Reforma 67",
                "fk_localidad_id": 75,  # Santiago Ixcuintla
            },
            {
                "id_persona": 9,
                "nombre": "Luis",
                "apellido_paterno": "Flores",
                "apellido_materno": "Ramos",
                "fecha_nacimiento": "1975-10-20",
                "sexo": "M",
                "domicilio": "Independencia 23",
                "fk_localidad_id": 84,  # Tepic
            },
            {
                "id_persona": 10,
                "nombre": "Martha",
                "apellido_paterno": "Díaz",
                "apellido_materno": "Reyes",
                "fecha_nacimiento": "1993-08-12",
                "sexo": "F",
                "domicilio": "Hidalgo 89",
                "fk_localidad_id": 92,  # Tuxpan
            },
            {
                "id_persona": 11,
                "nombre": "Admin",
                "apellido_paterno": "Sistema",
                "apellido_materno": "RASSA",
                "fecha_nacimiento": "1990-01-01",
                "sexo": "M",
                "domicilio": "Universidad S/N",
                "fk_localidad_id": 84,  # Tepic
            },
            {
                "id_persona": 12,
                "nombre": "Vendedor",
                "apellido_paterno": "Universidad",
                "apellido_materno": "RASSA",
                "fecha_nacimiento": "1992-01-01",
                "sexo": "F",
                "domicilio": "Universidad S/N",
                "fk_localidad_id": 62,  # San Blas
            },
        ]
        for p in personas:
            Persona.objects.update_or_create(id_persona=p["id_persona"], defaults=p)
        self.stdout.write("  Personas: OK")

    def _seed_usuarios(self):
        user_model = get_user_model()

        # Credenciales para auth_user (Django auth)
        credenciales = {
            1: "juan123",
            2: "maria123",
            3: "pedro123",
            4: "ana123",
            5: "jose123",
            6: "rosa123",
            7: "carlos123",
            8: "sofia123",
            9: "luis123",
            10: "martha123",
            11: "admin123",
            12: "vendedor123",
        }

        usuarios = [
            {
                "id_usuario": 1,
                "fk_persona_id": 1,
                "telefono": "4611234567",
                "correo": "juan.perez@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 2,
                "fk_persona_id": 2,
                "telefono": "4612345678",
                "correo": "maria.lopez@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 3,
                "fk_persona_id": 3,
                "telefono": "4613456789",
                "correo": "pedro.gonzalez@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 4,
                "fk_persona_id": 4,
                "telefono": "4614567890",
                "correo": "ana.ramirez@email.com",
                "fk_rol_id": 4,
            },
            {
                "id_usuario": 5,
                "fk_persona_id": 5,
                "telefono": "4615678901",
                "correo": "jose.sanchez@email.com",
                "fk_rol_id": 4,
            },
            {
                "id_usuario": 6,
                "fk_persona_id": 6,
                "telefono": "4616789012",
                "correo": "rosa.martinez@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 7,
                "fk_persona_id": 7,
                "telefono": "4617890123",
                "correo": "carlos.hernandez@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 8,
                "fk_persona_id": 8,
                "telefono": "4618901234",
                "correo": "sofia.torres@email.com",
                "fk_rol_id": 4,
            },
            {
                "id_usuario": 9,
                "fk_persona_id": 9,
                "telefono": "4619012345",
                "correo": "luis.flores@email.com",
                "fk_rol_id": 3,
            },
            {
                "id_usuario": 10,
                "fk_persona_id": 10,
                "telefono": "4610123456",
                "correo": "martha.diaz@email.com",
                "fk_rol_id": 4,
            },
            {
                "id_usuario": 11,
                "fk_persona_id": 11,
                "telefono": "4610000001",
                "correo": "admin@rassa.com",
                "fk_rol_id": 1,
            },
            {
                "id_usuario": 12,
                "fk_persona_id": 12,
                "telefono": "4610000002",
                "correo": "vendedor@rassa.com",
                "fk_rol_id": 2,
            },
        ]
        for u in usuarios:
            Usuario.objects.update_or_create(id_usuario=u["id_usuario"], defaults=u)
            # Crear usuario de Django auth para login JWT
            auth_user, created = user_model.objects.get_or_create(
                email=u["correo"],
                defaults={
                    "username": u["correo"],
                    "is_active": True,
                },
            )
            if created:
                auth_user.set_password(credenciales[u["id_usuario"]])
                auth_user.save()
            # Vincular Usuario con auth.User via fk_user
            usuario = Usuario.objects.get(id_usuario=u["id_usuario"])
            if usuario.fk_user_id != auth_user.id:
                usuario.fk_user = auth_user
                usuario.save(update_fields=["fk_user"])
        self.stdout.write("  Usuarios: OK")

    # ------------------------------------------------------------------
    # 4. FAMILIAS
    # ------------------------------------------------------------------

    def _seed_familias(self):
        familias = [
            {
                "id_familia": 1,
                "fk_jefe_familia_id": 1,
                "nombre_familia": "Familia Pérez",
                "detalle_familia": "Familia dedicada al cultivo de verduras en Apaseo el Alto",
            },
            {
                "id_familia": 2,
                "fk_jefe_familia_id": 3,
                "nombre_familia": "Familia González",
                "detalle_familia": "Productores de frutas y legumbres en Celaya",
            },
            {
                "id_familia": 3,
                "fk_jefe_familia_id": 7,
                "nombre_familia": "Familia Hernández",
                "detalle_familia": "Cultivo de hortalizas en Apaseo el Grande",
            },
        ]
        for f in familias:
            Familia.objects.update_or_create(id_familia=f["id_familia"], defaults=f)
        self.stdout.write("  Familias: OK")

    def _seed_familia_usuarios(self):
        registros = [
            {"id_familia_usuario": 1, "fk_usuario_id": 1, "fk_familia_id": 1},
            {"id_familia_usuario": 2, "fk_usuario_id": 2, "fk_familia_id": 1},
            {"id_familia_usuario": 3, "fk_usuario_id": 3, "fk_familia_id": 2},
            {"id_familia_usuario": 4, "fk_usuario_id": 6, "fk_familia_id": 2},
            {"id_familia_usuario": 5, "fk_usuario_id": 7, "fk_familia_id": 3},
            {"id_familia_usuario": 6, "fk_usuario_id": 9, "fk_familia_id": 3},
        ]
        for r in registros:
            FamiliaUsuario.objects.update_or_create(id_familia_usuario=r["id_familia_usuario"], defaults=r)
        self.stdout.write("  Familia-Usuarios: OK")

    def _seed_limites_cliente(self):
        limites = [
            {"id_limite": 1, "fk_usuario_id": 4, "monto": Decimal("500.00")},
            {"id_limite": 2, "fk_usuario_id": 5, "monto": Decimal("300.00")},
            {"id_limite": 3, "fk_usuario_id": 8, "monto": Decimal("750.00")},
            {"id_limite": 4, "fk_usuario_id": 10, "monto": Decimal("400.00")},
        ]
        for lim in limites:
            LimiteCliente.objects.update_or_create(id_limite=lim["id_limite"], defaults=lim)
        self.stdout.write("  Límites de cliente: OK")

    # ------------------------------------------------------------------
    # 5. PRODUCTOS
    # ------------------------------------------------------------------

    def _seed_productos(self):
        productos = [
            {
                "id_producto": 1,
                "nombre_producto": "Tomate Saladet",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 2,
                "nombre_producto": "Cebolla Blanca",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 3,
                "nombre_producto": "Lechuga Romana",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 4,
                "nombre_producto": "Zanahoria",
                "fk_categoria_id": 6,
                "es_perecedero": True,
            },
            {
                "id_producto": 5,
                "nombre_producto": "Papa",
                "fk_categoria_id": 6,
                "es_perecedero": True,
            },
            {
                "id_producto": 6,
                "nombre_producto": "Chile Serrano",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 7,
                "nombre_producto": "Cilantro",
                "fk_categoria_id": 5,
                "es_perecedero": True,
            },
            {
                "id_producto": 8,
                "nombre_producto": "Aguacate",
                "fk_categoria_id": 2,
                "es_perecedero": True,
            },
            {
                "id_producto": 9,
                "nombre_producto": "Manzana",
                "fk_categoria_id": 2,
                "es_perecedero": True,
            },
            {
                "id_producto": 10,
                "nombre_producto": "Naranja",
                "fk_categoria_id": 2,
                "es_perecedero": True,
            },
            {
                "id_producto": 11,
                "nombre_producto": "Frijol Negro",
                "fk_categoria_id": 4,
                "es_perecedero": False,
            },
            {
                "id_producto": 12,
                "nombre_producto": "Lenteja",
                "fk_categoria_id": 4,
                "es_perecedero": False,
            },
            {
                "id_producto": 13,
                "nombre_producto": "Queso Fresco",
                "fk_categoria_id": 3,
                "es_perecedero": True,
            },
            {
                "id_producto": 14,
                "nombre_producto": "Crema",
                "fk_categoria_id": 3,
                "es_perecedero": True,
            },
            {
                "id_producto": 15,
                "nombre_producto": "Betabel",
                "fk_categoria_id": 6,
                "es_perecedero": True,
            },
            {
                "id_producto": 16,
                "nombre_producto": "Espinaca",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 17,
                "nombre_producto": "Calabacita",
                "fk_categoria_id": 1,
                "es_perecedero": True,
            },
            {
                "id_producto": 18,
                "nombre_producto": "Perejil",
                "fk_categoria_id": 5,
                "es_perecedero": True,
            },
            {
                "id_producto": 19,
                "nombre_producto": "Camote",
                "fk_categoria_id": 6,
                "es_perecedero": True,
            },
            {
                "id_producto": 20,
                "nombre_producto": "Leche Bronca",
                "fk_categoria_id": 3,
                "es_perecedero": True,
            },
        ]
        for p in productos:
            Producto.objects.update_or_create(id_producto=p["id_producto"], defaults=p)
        self.stdout.write("  Productos: OK")

    # ------------------------------------------------------------------
    # 6. PUBLICACIÓN SEMANAL
    # ------------------------------------------------------------------

    def _seed_publicaciones_semanales(self):
        publicaciones = [
            {
                "id_publicacion": 1,
                "fk_agricultor_id": 1,
                "fecha_publicacion": "2026-06-01",
                "semana": 23,
                "estado": "cerrado",
            },
            {
                "id_publicacion": 2,
                "fk_agricultor_id": 1,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
            {
                "id_publicacion": 3,
                "fk_agricultor_id": 2,
                "fecha_publicacion": "2026-06-01",
                "semana": 23,
                "estado": "cerrado",
            },
            {
                "id_publicacion": 4,
                "fk_agricultor_id": 2,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
            {
                "id_publicacion": 5,
                "fk_agricultor_id": 3,
                "fecha_publicacion": "2026-06-01",
                "semana": 23,
                "estado": "cerrado",
            },
            {
                "id_publicacion": 6,
                "fk_agricultor_id": 3,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
            {
                "id_publicacion": 7,
                "fk_agricultor_id": 6,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
            {
                "id_publicacion": 8,
                "fk_agricultor_id": 7,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
            {
                "id_publicacion": 9,
                "fk_agricultor_id": 9,
                "fecha_publicacion": "2026-06-08",
                "semana": 24,
                "estado": "publicado",
            },
        ]
        for p in publicaciones:
            PublicacionSemanal.objects.update_or_create(id_publicacion=p["id_publicacion"], defaults=p)
        self.stdout.write("  Publicaciones semanales: OK")

    def _seed_productos_semanales(self):
        productos = [
            # Juan Pérez - Semana 24
            {
                "id_producto_semanal": 1,
                "fk_publicacion_id": 2,
                "fk_producto_id": 1,
                "fk_unidad_id": 1,
                "stock": 50,
                "precio": Decimal("25.00"),
            },
            {
                "id_producto_semanal": 2,
                "fk_publicacion_id": 2,
                "fk_producto_id": 2,
                "fk_unidad_id": 1,
                "stock": 40,
                "precio": Decimal("18.00"),
            },
            {
                "id_producto_semanal": 3,
                "fk_publicacion_id": 2,
                "fk_producto_id": 4,
                "fk_unidad_id": 1,
                "stock": 30,
                "precio": Decimal("22.00"),
            },
            {
                "id_producto_semanal": 4,
                "fk_publicacion_id": 2,
                "fk_producto_id": 6,
                "fk_unidad_id": 1,
                "stock": 15,
                "precio": Decimal("35.00"),
            },
            {
                "id_producto_semanal": 5,
                "fk_publicacion_id": 2,
                "fk_producto_id": 7,
                "fk_unidad_id": 3,
                "stock": 25,
                "precio": Decimal("10.00"),
            },
            # María López - Semana 24
            {
                "id_producto_semanal": 6,
                "fk_publicacion_id": 4,
                "fk_producto_id": 3,
                "fk_unidad_id": 2,
                "stock": 30,
                "precio": Decimal("15.00"),
            },
            {
                "id_producto_semanal": 7,
                "fk_publicacion_id": 4,
                "fk_producto_id": 16,
                "fk_unidad_id": 3,
                "stock": 20,
                "precio": Decimal("12.00"),
            },
            {
                "id_producto_semanal": 8,
                "fk_publicacion_id": 4,
                "fk_producto_id": 17,
                "fk_unidad_id": 1,
                "stock": 25,
                "precio": Decimal("14.00"),
            },
            # Pedro González - Semana 24
            {
                "id_producto_semanal": 9,
                "fk_publicacion_id": 6,
                "fk_producto_id": 8,
                "fk_unidad_id": 2,
                "stock": 20,
                "precio": Decimal("35.00"),
            },
            {
                "id_producto_semanal": 10,
                "fk_publicacion_id": 6,
                "fk_producto_id": 9,
                "fk_unidad_id": 1,
                "stock": 30,
                "precio": Decimal("28.00"),
            },
            {
                "id_producto_semanal": 11,
                "fk_publicacion_id": 6,
                "fk_producto_id": 10,
                "fk_unidad_id": 5,
                "stock": 25,
                "precio": Decimal("22.00"),
            },
            {
                "id_producto_semanal": 12,
                "fk_publicacion_id": 6,
                "fk_producto_id": 11,
                "fk_unidad_id": 1,
                "stock": 15,
                "precio": Decimal("30.00"),
            },
            # Rosa Martínez - Semana 24
            {
                "id_producto_semanal": 13,
                "fk_publicacion_id": 7,
                "fk_producto_id": 5,
                "fk_unidad_id": 1,
                "stock": 35,
                "precio": Decimal("16.00"),
            },
            {
                "id_producto_semanal": 14,
                "fk_publicacion_id": 7,
                "fk_producto_id": 15,
                "fk_unidad_id": 1,
                "stock": 20,
                "precio": Decimal("20.00"),
            },
            {
                "id_producto_semanal": 15,
                "fk_publicacion_id": 7,
                "fk_producto_id": 18,
                "fk_unidad_id": 3,
                "stock": 15,
                "precio": Decimal("8.00"),
            },
            # Carlos Hernández - Semana 24
            {
                "id_producto_semanal": 16,
                "fk_publicacion_id": 8,
                "fk_producto_id": 12,
                "fk_unidad_id": 1,
                "stock": 20,
                "precio": Decimal("28.00"),
            },
            {
                "id_producto_semanal": 17,
                "fk_publicacion_id": 8,
                "fk_producto_id": 19,
                "fk_unidad_id": 1,
                "stock": 18,
                "precio": Decimal("18.00"),
            },
            # Luis Flores - Semana 24
            {
                "id_producto_semanal": 18,
                "fk_publicacion_id": 9,
                "fk_producto_id": 13,
                "fk_unidad_id": 1,
                "stock": 10,
                "precio": Decimal("60.00"),
            },
            {
                "id_producto_semanal": 19,
                "fk_publicacion_id": 9,
                "fk_producto_id": 14,
                "fk_unidad_id": 4,
                "stock": 8,
                "precio": Decimal("35.00"),
            },
            {
                "id_producto_semanal": 20,
                "fk_publicacion_id": 9,
                "fk_producto_id": 20,
                "fk_unidad_id": 4,
                "stock": 12,
                "precio": Decimal("18.00"),
            },
        ]
        for p in productos:
            ProductoSemanal.objects.update_or_create(id_producto_semanal=p["id_producto_semanal"], defaults=p)
        self.stdout.write("  Productos semanales: OK")

    # ------------------------------------------------------------------
    # 7. PEDIDOS
    # ------------------------------------------------------------------

    def _seed_pedidos(self):
        pedidos = [
            {
                "id_pedido": 1,
                "fk_cliente_id": 4,
                "fk_estado_id": 5,
                "subtotal": Decimal("103.00"),
                "iva": Decimal("16.48"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-05 18:00:00",
                "total": Decimal("119.48"),
            },
            {
                "id_pedido": 2,
                "fk_cliente_id": 5,
                "fk_estado_id": 4,
                "subtotal": Decimal("78.00"),
                "iva": Decimal("12.48"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-06 18:00:00",
                "total": Decimal("90.48"),
            },
            {
                "id_pedido": 3,
                "fk_cliente_id": 8,
                "fk_estado_id": 2,
                "subtotal": Decimal("155.00"),
                "iva": Decimal("24.80"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-06 18:00:00",
                "total": Decimal("179.80"),
            },
            {
                "id_pedido": 4,
                "fk_cliente_id": 10,
                "fk_estado_id": 1,
                "subtotal": Decimal("45.00"),
                "iva": Decimal("7.20"),
                "fk_vendedor_id": None,
                "fecha_expiracion": "2026-06-07 18:00:00",
                "total": Decimal("52.20"),
            },
            {
                "id_pedido": 5,
                "fk_cliente_id": 4,
                "fk_estado_id": 1,
                "subtotal": Decimal("120.00"),
                "iva": Decimal("19.20"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-08 18:00:00",
                "total": Decimal("139.20"),
            },
            {
                "id_pedido": 6,
                "fk_cliente_id": 5,
                "fk_estado_id": 3,
                "subtotal": Decimal("88.00"),
                "iva": Decimal("14.08"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-06 18:00:00",
                "total": Decimal("102.08"),
            },
            {
                "id_pedido": 7,
                "fk_cliente_id": 8,
                "fk_estado_id": 5,
                "subtotal": Decimal("210.00"),
                "iva": Decimal("33.60"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-04 18:00:00",
                "total": Decimal("243.60"),
            },
            {
                "id_pedido": 8,
                "fk_cliente_id": 10,
                "fk_estado_id": 6,
                "subtotal": Decimal("65.00"),
                "iva": Decimal("10.40"),
                "fk_vendedor_id": None,
                "fecha_expiracion": "2026-06-05 18:00:00",
                "total": Decimal("75.40"),
            },
            {
                "id_pedido": 9,
                "fk_cliente_id": 4,
                "fk_estado_id": 2,
                "subtotal": Decimal("95.00"),
                "iva": Decimal("15.20"),
                "fk_vendedor_id": 12,
                "fecha_expiracion": "2026-06-09 18:00:00",
                "total": Decimal("110.20"),
            },
            {
                "id_pedido": 10,
                "fk_cliente_id": 8,
                "fk_estado_id": 1,
                "subtotal": Decimal("180.00"),
                "iva": Decimal("28.80"),
                "fk_vendedor_id": None,
                "fecha_expiracion": "2026-06-10 18:00:00",
                "total": Decimal("208.80"),
            },
        ]
        for p in pedidos:
            if isinstance(p.get("fecha_expiracion"), str):
                p["fecha_expiracion"] = timezone.make_aware(dt.strptime(p["fecha_expiracion"], "%Y-%m-%d %H:%M:%S"))
            PedidoCabecera.objects.update_or_create(id_pedido=p["id_pedido"], defaults=p)
        self.stdout.write("  Pedidos cabecera: OK")

    def _seed_detalles_pedido(self):
        detalles = [
            # Pedido 1 - Ana (ENTREGADO)
            {
                "id_detalle": 1,
                "fk_pedido_id": 1,
                "fk_producto_semanal_id": 1,
                "nombre_producto": "Tomate Saladet",
                "precio_unitario": Decimal("25.00"),
                "cantidad": 2,
                "importe": Decimal("50.00"),
            },
            {
                "id_detalle": 2,
                "fk_pedido_id": 1,
                "fk_producto_semanal_id": 2,
                "nombre_producto": "Cebolla Blanca",
                "precio_unitario": Decimal("18.00"),
                "cantidad": 1,
                "importe": Decimal("18.00"),
            },
            {
                "id_detalle": 3,
                "fk_pedido_id": 1,
                "fk_producto_semanal_id": 5,
                "nombre_producto": "Cilantro",
                "precio_unitario": Decimal("10.00"),
                "cantidad": 3,
                "importe": Decimal("30.00"),
            },
            {
                "id_detalle": 4,
                "fk_pedido_id": 1,
                "fk_producto_semanal_id": 8,
                "nombre_producto": "Calabacita",
                "precio_unitario": Decimal("14.00"),
                "cantidad": 1,
                "importe": Decimal("14.00"),
            },
            # Pedido 2 - José (LISTO PARA RETIRAR)
            {
                "id_detalle": 5,
                "fk_pedido_id": 2,
                "fk_producto_semanal_id": 3,
                "nombre_producto": "Zanahoria",
                "precio_unitario": Decimal("22.00"),
                "cantidad": 2,
                "importe": Decimal("44.00"),
            },
            {
                "id_detalle": 6,
                "fk_pedido_id": 2,
                "fk_producto_semanal_id": 13,
                "nombre_producto": "Papa",
                "precio_unitario": Decimal("16.00"),
                "cantidad": 2,
                "importe": Decimal("32.00"),
            },
            {
                "id_detalle": 7,
                "fk_pedido_id": 2,
                "fk_producto_semanal_id": 5,
                "nombre_producto": "Cilantro",
                "precio_unitario": Decimal("10.00"),
                "cantidad": 1,
                "importe": Decimal("10.00"),
            },
            # Pedido 3 - Sofía (CONFIRMADO)
            {
                "id_detalle": 8,
                "fk_pedido_id": 3,
                "fk_producto_semanal_id": 6,
                "nombre_producto": "Lechuga Romana",
                "precio_unitario": Decimal("15.00"),
                "cantidad": 3,
                "importe": Decimal("45.00"),
            },
            {
                "id_detalle": 9,
                "fk_pedido_id": 3,
                "fk_producto_semanal_id": 9,
                "nombre_producto": "Aguacate",
                "precio_unitario": Decimal("35.00"),
                "cantidad": 2,
                "importe": Decimal("70.00"),
            },
            {
                "id_detalle": 10,
                "fk_pedido_id": 3,
                "fk_producto_semanal_id": 10,
                "nombre_producto": "Manzana",
                "precio_unitario": Decimal("28.00"),
                "cantidad": 1,
                "importe": Decimal("28.00"),
            },
            {
                "id_detalle": 11,
                "fk_pedido_id": 3,
                "fk_producto_semanal_id": 7,
                "nombre_producto": "Espinaca",
                "precio_unitario": Decimal("12.00"),
                "cantidad": 2,
                "importe": Decimal("24.00"),
            },
            # Pedido 4 - Martha (PENDIENTE)
            {
                "id_detalle": 12,
                "fk_pedido_id": 4,
                "fk_producto_semanal_id": 12,
                "nombre_producto": "Frijol Negro",
                "precio_unitario": Decimal("30.00"),
                "cantidad": 1,
                "importe": Decimal("30.00"),
            },
            {
                "id_detalle": 13,
                "fk_pedido_id": 4,
                "fk_producto_semanal_id": 11,
                "nombre_producto": "Naranja",
                "precio_unitario": Decimal("22.00"),
                "cantidad": 1,
                "importe": Decimal("22.00"),
            },
            # Pedido 5 - Ana (PENDIENTE)
            {
                "id_detalle": 14,
                "fk_pedido_id": 5,
                "fk_producto_semanal_id": 18,
                "nombre_producto": "Queso Fresco",
                "precio_unitario": Decimal("60.00"),
                "cantidad": 1,
                "importe": Decimal("60.00"),
            },
            {
                "id_detalle": 15,
                "fk_pedido_id": 5,
                "fk_producto_semanal_id": 19,
                "nombre_producto": "Crema",
                "precio_unitario": Decimal("35.00"),
                "cantidad": 2,
                "importe": Decimal("70.00"),
            },
            # Pedido 6 - José (EN PREPARACIÓN)
            {
                "id_detalle": 16,
                "fk_pedido_id": 6,
                "fk_producto_semanal_id": 14,
                "nombre_producto": "Betabel",
                "precio_unitario": Decimal("20.00"),
                "cantidad": 2,
                "importe": Decimal("40.00"),
            },
            {
                "id_detalle": 17,
                "fk_pedido_id": 6,
                "fk_producto_semanal_id": 17,
                "nombre_producto": "Camote",
                "precio_unitario": Decimal("18.00"),
                "cantidad": 2,
                "importe": Decimal("36.00"),
            },
            {
                "id_detalle": 18,
                "fk_pedido_id": 6,
                "fk_producto_semanal_id": 4,
                "nombre_producto": "Chile Serrano",
                "precio_unitario": Decimal("35.00"),
                "cantidad": 1,
                "importe": Decimal("35.00"),
            },
            # Pedido 7 - Sofía (ENTREGADO)
            {
                "id_detalle": 19,
                "fk_pedido_id": 7,
                "fk_producto_semanal_id": 1,
                "nombre_producto": "Tomate Saladet",
                "precio_unitario": Decimal("25.00"),
                "cantidad": 3,
                "importe": Decimal("75.00"),
            },
            {
                "id_detalle": 20,
                "fk_pedido_id": 7,
                "fk_producto_semanal_id": 9,
                "nombre_producto": "Aguacate",
                "precio_unitario": Decimal("35.00"),
                "cantidad": 3,
                "importe": Decimal("105.00"),
            },
            {
                "id_detalle": 21,
                "fk_pedido_id": 7,
                "fk_producto_semanal_id": 10,
                "nombre_producto": "Manzana",
                "precio_unitario": Decimal("28.00"),
                "cantidad": 2,
                "importe": Decimal("56.00"),
            },
            # Pedido 8 - Martha (CANCELADO)
            {
                "id_detalle": 22,
                "fk_pedido_id": 8,
                "fk_producto_semanal_id": 13,
                "nombre_producto": "Papa",
                "precio_unitario": Decimal("16.00"),
                "cantidad": 3,
                "importe": Decimal("48.00"),
            },
            {
                "id_detalle": 23,
                "fk_pedido_id": 8,
                "fk_producto_semanal_id": 15,
                "nombre_producto": "Perejil",
                "precio_unitario": Decimal("8.00"),
                "cantidad": 2,
                "importe": Decimal("16.00"),
            },
            # Pedido 9 - Ana (CONFIRMADO)
            {
                "id_detalle": 24,
                "fk_pedido_id": 9,
                "fk_producto_semanal_id": 2,
                "nombre_producto": "Cebolla Blanca",
                "precio_unitario": Decimal("18.00"),
                "cantidad": 2,
                "importe": Decimal("36.00"),
            },
            {
                "id_detalle": 25,
                "fk_pedido_id": 9,
                "fk_producto_semanal_id": 6,
                "nombre_producto": "Lechuga Romana",
                "precio_unitario": Decimal("15.00"),
                "cantidad": 3,
                "importe": Decimal("45.00"),
            },
            {
                "id_detalle": 26,
                "fk_pedido_id": 9,
                "fk_producto_semanal_id": 8,
                "nombre_producto": "Calabacita",
                "precio_unitario": Decimal("14.00"),
                "cantidad": 1,
                "importe": Decimal("14.00"),
            },
            # Pedido 10 - Sofía (PENDIENTE)
            {
                "id_detalle": 27,
                "fk_pedido_id": 10,
                "fk_producto_semanal_id": 3,
                "nombre_producto": "Zanahoria",
                "precio_unitario": Decimal("22.00"),
                "cantidad": 3,
                "importe": Decimal("66.00"),
            },
            {
                "id_detalle": 28,
                "fk_pedido_id": 10,
                "fk_producto_semanal_id": 12,
                "nombre_producto": "Frijol Negro",
                "precio_unitario": Decimal("30.00"),
                "cantidad": 3,
                "importe": Decimal("90.00"),
            },
            {
                "id_detalle": 29,
                "fk_pedido_id": 10,
                "fk_producto_semanal_id": 7,
                "nombre_producto": "Espinaca",
                "precio_unitario": Decimal("12.00"),
                "cantidad": 2,
                "importe": Decimal("24.00"),
            },
        ]
        for d in detalles:
            DetallePedido.objects.update_or_create(id_detalle=d["id_detalle"], defaults=d)
        self.stdout.write("  Detalles de pedido: OK")

    # ------------------------------------------------------------------
    # 8. PAGOS Y CORTES
    # ------------------------------------------------------------------

    def _seed_pagos(self):
        pagos = [
            {
                "id_pago": 1,
                "fk_pedido_id": 1,
                "fk_tipo_id": 1,
                "monto": Decimal("120.00"),
                "referencia": None,
            },
            {
                "id_pago": 2,
                "fk_pedido_id": 2,
                "fk_tipo_id": 2,
                "monto": Decimal("90.00"),
                "referencia": "TRF-20260601-001",
            },
            {
                "id_pago": 3,
                "fk_pedido_id": 7,
                "fk_tipo_id": 1,
                "monto": Decimal("244.00"),
                "referencia": None,
            },
            {
                "id_pago": 4,
                "fk_pedido_id": 3,
                "fk_tipo_id": 1,
                "monto": Decimal("180.00"),
                "referencia": None,
            },
        ]
        for p in pagos:
            Pago.objects.update_or_create(id_pago=p["id_pago"], defaults=p)
        self.stdout.write("  Pagos: OK")

    def _seed_cortes(self):
        cortes = [
            {
                "id_corte": 1,
                "monto_real": Decimal("3560.00"),
                "monto_teorico": Decimal("3520.00"),
                "diferencia": Decimal("40.00"),
                "estado": "cuadrado",
                "creado_en": "2026-06-01 18:00:00",
            },
            {
                "id_corte": 2,
                "monto_real": Decimal("2840.00"),
                "monto_teorico": Decimal("2890.00"),
                "diferencia": Decimal("-50.00"),
                "estado": "cerrado",
                "creado_en": "2026-06-02 18:00:00",
            },
            {
                "id_corte": 3,
                "monto_real": Decimal("4120.00"),
                "monto_teorico": Decimal("4120.00"),
                "diferencia": Decimal("0.00"),
                "estado": "cuadrado",
                "creado_en": "2026-06-08 18:00:00",
            },
        ]
        for c in cortes:
            if isinstance(c.get("creado_en"), str):
                c["creado_en"] = timezone.make_aware(dt.strptime(c["creado_en"], "%Y-%m-%d %H:%M:%S"))
            Corte.objects.update_or_create(id_corte=c["id_corte"], defaults=c)
        self.stdout.write("  Cortes de caja: OK")

    # ------------------------------------------------------------------
    # 9. HISTORIAL DE ESTADO DE PEDIDO
    # ------------------------------------------------------------------

    def _seed_historial_estado_pedido(self):
        historial = [
            {
                "id_historial": 1,
                "fk_pedido_id": 1,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 4,
                "creado_en": "2026-06-01 09:30:00",
            },
            {
                "id_historial": 2,
                "fk_pedido_id": 1,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 10:00:00",
            },
            {
                "id_historial": 3,
                "fk_pedido_id": 1,
                "fk_estado_anterior_id": 2,
                "fk_estado_nuevo_id": 3,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 11:00:00",
            },
            {
                "id_historial": 4,
                "fk_pedido_id": 1,
                "fk_estado_anterior_id": 3,
                "fk_estado_nuevo_id": 4,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 16:00:00",
            },
            {
                "id_historial": 5,
                "fk_pedido_id": 1,
                "fk_estado_anterior_id": 4,
                "fk_estado_nuevo_id": 5,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-02 10:00:00",
            },
            {
                "id_historial": 6,
                "fk_pedido_id": 2,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 5,
                "creado_en": "2026-06-01 10:30:00",
            },
            {
                "id_historial": 7,
                "fk_pedido_id": 2,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 11:00:00",
            },
            {
                "id_historial": 8,
                "fk_pedido_id": 2,
                "fk_estado_anterior_id": 2,
                "fk_estado_nuevo_id": 3,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 14:00:00",
            },
            {
                "id_historial": 9,
                "fk_pedido_id": 2,
                "fk_estado_anterior_id": 3,
                "fk_estado_nuevo_id": 4,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-03 12:00:00",
            },
            {
                "id_historial": 10,
                "fk_pedido_id": 3,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 8,
                "creado_en": "2026-06-02 11:30:00",
            },
            {
                "id_historial": 11,
                "fk_pedido_id": 3,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-02 14:00:00",
            },
            {
                "id_historial": 12,
                "fk_pedido_id": 6,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 5,
                "creado_en": "2026-06-02 12:00:00",
            },
            {
                "id_historial": 13,
                "fk_pedido_id": 6,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-02 13:00:00",
            },
            {
                "id_historial": 14,
                "fk_pedido_id": 6,
                "fk_estado_anterior_id": 2,
                "fk_estado_nuevo_id": 3,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-03 09:00:00",
            },
            {
                "id_historial": 15,
                "fk_pedido_id": 7,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 8,
                "creado_en": "2026-06-01 15:00:00",
            },
            {
                "id_historial": 16,
                "fk_pedido_id": 7,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-01 16:00:00",
            },
            {
                "id_historial": 17,
                "fk_pedido_id": 7,
                "fk_estado_anterior_id": 2,
                "fk_estado_nuevo_id": 3,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-02 09:00:00",
            },
            {
                "id_historial": 18,
                "fk_pedido_id": 7,
                "fk_estado_anterior_id": 3,
                "fk_estado_nuevo_id": 4,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-02 14:00:00",
            },
            {
                "id_historial": 19,
                "fk_pedido_id": 7,
                "fk_estado_anterior_id": 4,
                "fk_estado_nuevo_id": 5,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-03 11:00:00",
            },
            {
                "id_historial": 20,
                "fk_pedido_id": 8,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 10,
                "creado_en": "2026-06-02 10:00:00",
            },
            {
                "id_historial": 21,
                "fk_pedido_id": 8,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 6,
                "fk_cambiado_por_id": 10,
                "creado_en": "2026-06-02 16:00:00",
            },
            {
                "id_historial": 22,
                "fk_pedido_id": 9,
                "fk_estado_anterior_id": None,
                "fk_estado_nuevo_id": 1,
                "fk_cambiado_por_id": 4,
                "creado_en": "2026-06-03 09:00:00",
            },
            {
                "id_historial": 23,
                "fk_pedido_id": 9,
                "fk_estado_anterior_id": 1,
                "fk_estado_nuevo_id": 2,
                "fk_cambiado_por_id": 12,
                "creado_en": "2026-06-03 11:00:00",
            },
        ]
        for h in historial:
            if isinstance(h.get("creado_en"), str):
                h["creado_en"] = timezone.make_aware(dt.strptime(h["creado_en"], "%Y-%m-%d %H:%M:%S"))
            HistorialEstadoPedido.objects.update_or_create(id_historial=h["id_historial"], defaults=h)
        self.stdout.write("  Historial de estados: OK")

    # ------------------------------------------------------------------
    # 10. MERMAS
    # ------------------------------------------------------------------

    def _seed_mermas(self):
        mermas = [
            {
                "id_merma": 1,
                "fk_producto_semanal_id": 16,
                "cantidad": 2,
                "motivo": "Se magullaron durante el transporte",
                "comentarios": "Las papas llegaron golpeadas",
                "fk_decision_id": 2,
            },
            {
                "id_merma": 2,
                "fk_producto_semanal_id": 6,
                "cantidad": 3,
                "motivo": "Se marchitaron",
                "comentarios": "Las lechugas no se vendieron en 3 días",
                "fk_decision_id": 1,
            },
            {
                "id_merma": 3,
                "fk_producto_semanal_id": 1,
                "cantidad": 5,
                "motivo": "Se echaron a perder",
                "comentarios": "Los tomates maduraron muy rápido",
                "fk_decision_id": 2,
            },
            {
                "id_merma": 4,
                "fk_producto_semanal_id": 5,
                "cantidad": 4,
                "motivo": "No se vendieron",
                "comentarios": "Sobraron manojos del fin de semana",
                "fk_decision_id": 3,
            },
        ]
        for m in mermas:
            Merma.objects.update_or_create(id_merma=m["id_merma"], defaults=m)
        self.stdout.write("  Mermas: OK")

    # ------------------------------------------------------------------
    # 11. LOGS
    # ------------------------------------------------------------------

    def _seed_logs(self):
        logs = [
            {
                "id_log": 1,
                "fk_usuario_id": 11,
                "descripcion": "Inició sesión",
                "ip": "192.168.1.100",
                "dispositivo": "Chrome 120 / Windows 10",
            },
            {
                "id_log": 2,
                "fk_usuario_id": 1,
                "descripcion": "Creó publicación semanal #2",
                "ip": "192.168.1.101",
                "dispositivo": "Chrome 120 / Android 14",
            },
            {
                "id_log": 3,
                "fk_usuario_id": 4,
                "descripcion": "Hizo pedido #1",
                "ip": "192.168.1.102",
                "dispositivo": "Safari 17 / iOS 18",
            },
            {
                "id_log": 4,
                "fk_usuario_id": 2,
                "descripcion": "Publicó productos (semana 24)",
                "ip": "192.168.1.103",
                "dispositivo": "Firefox 125 / Windows 11",
            },
            {
                "id_log": 5,
                "fk_usuario_id": 12,
                "descripcion": "Cambió estado pedido #2 a listo",
                "ip": "192.168.1.100",
                "dispositivo": "Chrome 120 / Windows 10",
            },
            {
                "id_log": 6,
                "fk_usuario_id": 3,
                "descripcion": "Inició sesión",
                "ip": "192.168.1.104",
                "dispositivo": "Chrome 120 / Android 13",
            },
            {
                "id_log": 7,
                "fk_usuario_id": 8,
                "descripcion": "Hizo pedido #3",
                "ip": "192.168.1.105",
                "dispositivo": "Safari 17 / iOS 18",
            },
            {
                "id_log": 8,
                "fk_usuario_id": 11,
                "descripcion": "Creó usuario #12 (vendedor)",
                "ip": "192.168.1.100",
                "dispositivo": "Chrome 120 / Windows 10",
            },
            {
                "id_log": 9,
                "fk_usuario_id": 5,
                "descripcion": "Hizo pedido #6",
                "ip": "192.168.1.106",
                "dispositivo": "Edge 125 / Windows 11",
            },
            {
                "id_log": 10,
                "fk_usuario_id": 12,
                "descripcion": "Registró merma #1",
                "ip": "192.168.1.100",
                "dispositivo": "Chrome 120 / Windows 10",
            },
            {
                "id_log": 11,
                "fk_usuario_id": 11,
                "descripcion": "Cerró corte de caja #1",
                "ip": "192.168.1.100",
                "dispositivo": "Chrome 120 / Windows 10",
            },
            {
                "id_log": 12,
                "fk_usuario_id": 4,
                "descripcion": "Hizo pedido #5",
                "ip": "192.168.1.102",
                "dispositivo": "Safari 17 / iOS 18",
            },
        ]
        for log_entry in logs:
            Log.objects.update_or_create(id_log=log_entry["id_log"], defaults=log_entry)
        self.stdout.write("  Logs: OK")

    # ------------------------------------------------------------------
    # 12. CHAT
    # ------------------------------------------------------------------

    def _seed_conversaciones(self):
        convs = [
            {"id_conversacion": 1, "nombre": None, "tipo": False},
            {"id_conversacion": 2, "nombre": None, "tipo": False},
            {"id_conversacion": 3, "nombre": None, "tipo": False},
            {"id_conversacion": 4, "nombre": None, "tipo": False},
            {"id_conversacion": 5, "nombre": None, "tipo": False},
            {"id_conversacion": 6, "nombre": None, "tipo": False},
            {"id_conversacion": 7, "nombre": "Familia Pérez", "tipo": True},
            {"id_conversacion": 8, "nombre": "Familia González", "tipo": True},
            {"id_conversacion": 9, "nombre": "Familia Hernández", "tipo": True},
        ]
        for c in convs:
            Conversacion.objects.update_or_create(id_conversacion=c["id_conversacion"], defaults=c)
        self.stdout.write("  Conversaciones: OK")

    def _seed_integrantes(self):
        integrantes = [
            {"id_miembro": 1, "fk_usuario_id": 4, "fk_conversacion_id": 1},
            {"id_miembro": 2, "fk_usuario_id": 1, "fk_conversacion_id": 1},
            {"id_miembro": 3, "fk_usuario_id": 5, "fk_conversacion_id": 2},
            {"id_miembro": 4, "fk_usuario_id": 2, "fk_conversacion_id": 2},
            {"id_miembro": 5, "fk_usuario_id": 8, "fk_conversacion_id": 3},
            {"id_miembro": 6, "fk_usuario_id": 3, "fk_conversacion_id": 3},
            {"id_miembro": 7, "fk_usuario_id": 10, "fk_conversacion_id": 4},
            {"id_miembro": 8, "fk_usuario_id": 6, "fk_conversacion_id": 4},
            {"id_miembro": 9, "fk_usuario_id": 4, "fk_conversacion_id": 5},
            {"id_miembro": 10, "fk_usuario_id": 7, "fk_conversacion_id": 5},
            {"id_miembro": 11, "fk_usuario_id": 11, "fk_conversacion_id": 6},
            {"id_miembro": 12, "fk_usuario_id": 1, "fk_conversacion_id": 6},
            {"id_miembro": 13, "fk_usuario_id": 1, "fk_conversacion_id": 7},
            {"id_miembro": 14, "fk_usuario_id": 2, "fk_conversacion_id": 7},
            {"id_miembro": 15, "fk_usuario_id": 3, "fk_conversacion_id": 8},
            {"id_miembro": 16, "fk_usuario_id": 6, "fk_conversacion_id": 8},
            {"id_miembro": 17, "fk_usuario_id": 7, "fk_conversacion_id": 9},
            {"id_miembro": 18, "fk_usuario_id": 9, "fk_conversacion_id": 9},
        ]
        for i in integrantes:
            Integrante.objects.update_or_create(id_miembro=i["id_miembro"], defaults=i)
        self.stdout.write("  Integrantes: OK")

        # Sincronizar conversaciones familiares: enlazar por nombre las convs
        # 7/8/9 ya creadas sin fk_familia, luego ensure_family_chat reconcilia
        # integrantes/roles. ponytail: se hace aquí (tras crear convs+integrantes)
        # en vez de tras _seed_familias porque las convs aún no existían allí.
        from rassa.blueprints.chat.services import chat_sync

        for f in Familia.objects.all():
            Conversacion.objects.filter(nombre=f.nombre_familia, fk_familia__isnull=True, tipo=True).update(
                fk_familia=f
            )
        for f in Familia.objects.all():
            chat_sync.ensure_family_chat(f.id_familia)
        self.stdout.write("  Conversaciones familiares sincronizadas: OK")

    def _seed_mensajes(self):
        mensajes = [
            {
                "id_mensaje": 1,
                "fk_emisor_id": 4,
                "fk_conversacion_id": 1,
                "contenido": "Buenos días, ¿todavía tiene tomate?",
                "leido": True,
                "creado_en": "2026-06-01 09:00:00",
            },
            {
                "id_mensaje": 2,
                "fk_emisor_id": 1,
                "fk_conversacion_id": 1,
                "contenido": "Sí, tengo 50kg disponibles",
                "leido": True,
                "creado_en": "2026-06-01 09:15:00",
            },
            {
                "id_mensaje": 3,
                "fk_emisor_id": 4,
                "fk_conversacion_id": 1,
                "contenido": "Perfecto, voy a pedir 2kg",
                "leido": True,
                "creado_en": "2026-06-01 09:20:00",
            },
            {
                "id_mensaje": 4,
                "fk_emisor_id": 1,
                "fk_conversacion_id": 1,
                "contenido": "Claro, cuando guste",
                "leido": False,
                "creado_en": "2026-06-01 09:25:00",
            },
            {
                "id_mensaje": 5,
                "fk_emisor_id": 5,
                "fk_conversacion_id": 2,
                "contenido": "¿Las espinacas son orgánicas?",
                "leido": True,
                "creado_en": "2026-06-02 10:00:00",
            },
            {
                "id_mensaje": 6,
                "fk_emisor_id": 2,
                "fk_conversacion_id": 2,
                "contenido": "Sí, todo es orgánico, sin químicos",
                "leido": True,
                "creado_en": "2026-06-02 10:30:00",
            },
            {
                "id_mensaje": 7,
                "fk_emisor_id": 5,
                "fk_conversacion_id": 2,
                "contenido": "Perfecto, gracias",
                "leido": False,
                "creado_en": "2026-06-02 10:35:00",
            },
            {
                "id_mensaje": 8,
                "fk_emisor_id": 8,
                "fk_conversacion_id": 3,
                "contenido": "¿Los aguacates ya están suaves?",
                "leido": True,
                "creado_en": "2026-06-03 11:00:00",
            },
            {
                "id_mensaje": 9,
                "fk_emisor_id": 3,
                "fk_conversacion_id": 3,
                "contenido": "Acabo de cortarlos, están en el punto",
                "leido": True,
                "creado_en": "2026-06-03 11:10:00",
            },
            {
                "id_mensaje": 10,
                "fk_emisor_id": 8,
                "fk_conversacion_id": 3,
                "contenido": "Perfecto, pido 3",
                "leido": False,
                "creado_en": "2026-06-03 11:15:00",
            },
            {
                "id_mensaje": 11,
                "fk_emisor_id": 1,
                "fk_conversacion_id": 7,
                "contenido": "Compas, mañana llevo el tomate y la cebolla",
                "leido": True,
                "creado_en": "2026-06-07 18:00:00",
            },
            {
                "id_mensaje": 12,
                "fk_emisor_id": 2,
                "fk_conversacion_id": 7,
                "contenido": "Yo llevo la lechuga y espinaca",
                "leido": True,
                "creado_en": "2026-06-07 18:05:00",
            },
            {
                "id_mensaje": 13,
                "fk_emisor_id": 1,
                "fk_conversacion_id": 7,
                "contenido": "Súper, nos vemos en la uni a las 7am",
                "leido": False,
                "creado_en": "2026-06-07 18:10:00",
            },
            {
                "id_mensaje": 14,
                "fk_emisor_id": 11,
                "fk_conversacion_id": 6,
                "contenido": "Don Juan, mañana paso por sus productos a las 8am",
                "leido": True,
                "creado_en": "2026-06-07 16:00:00",
            },
            {
                "id_mensaje": 15,
                "fk_emisor_id": 1,
                "fk_conversacion_id": 6,
                "contenido": "Está bien, lo espero",
                "leido": True,
                "creado_en": "2026-06-07 16:30:00",
            },
        ]
        for m in mensajes:
            if isinstance(m.get("creado_en"), str):
                m["creado_en"] = timezone.make_aware(dt.strptime(m["creado_en"], "%Y-%m-%d %H:%M:%S"))
            Mensaje.objects.update_or_create(id_mensaje=m["id_mensaje"], defaults=m)
        self._reset_pk_sequence(Mensaje)
        self.stdout.write("  Mensajes: OK")

    def _seed_documentos(self):
        documentos = [
            {
                "id_documento": 1,
                "fk_usuario_id": 1,
                "nombre_documento": "tomate_disponible.png",
                "url_documento": "documentos/tomate_disponible.png",
                "tipo_documento": "imagen",
            },
            {
                "id_documento": 2,
                "fk_usuario_id": 2,
                "nombre_documento": "espinaca_organica.png",
                "url_documento": "documentos/espinaca_organica.png",
                "tipo_documento": "imagen",
            },
            {
                "id_documento": 3,
                "fk_usuario_id": 11,
                "nombre_documento": "nota_recoleccion.wav",
                "url_documento": "documentos/nota_recoleccion.wav",
                "tipo_documento": "audio",
            },
        ]
        for d in documentos:
            Documento.objects.update_or_create(id_documento=d["id_documento"], defaults=d)
        self._write_demo_media()
        self.stdout.write("  Documentos: OK")

    def _write_demo_media(self):
        docs_dir = Path(settings.MEDIA_ROOT) / "documentos"
        docs_dir.mkdir(parents=True, exist_ok=True)
        _write_tone_wav(docs_dir / "nota_recoleccion.wav")
        _write_solid_png(docs_dir / "tomate_disponible.png", (200, 60, 50))
        _write_solid_png(docs_dir / "espinaca_organica.png", (46, 139, 87))

    def _seed_mensajes_documentos(self):
        registros = [
            {"id_mensaje_documento": 1, "fk_mensaje_id": 2, "fk_documento_id": 1},
            {"id_mensaje_documento": 2, "fk_mensaje_id": 6, "fk_documento_id": 2},
            {"id_mensaje_documento": 3, "fk_mensaje_id": 14, "fk_documento_id": 3},
        ]
        for r in registros:
            MensajeDocumento.objects.update_or_create(id_mensaje_documento=r["id_mensaje_documento"], defaults=r)
        self.stdout.write("  Mensajes-Documentos: OK")

    # ------------------------------------------------------------------
    # 13. IMÁGENES DE PRODUCTO
    # ------------------------------------------------------------------

    def _seed_producto_imagenes(self):
        imagenes = [
            {
                "id_imagen": 1,
                "fk_producto_id": 1,
                "url": "https://storage.rassa.com/productos/tomate_01.jpg",
                "es_principal": True,
            },
            {
                "id_imagen": 2,
                "fk_producto_id": 1,
                "url": "https://storage.rassa.com/productos/tomate_02.jpg",
                "es_principal": False,
            },
            {
                "id_imagen": 3,
                "fk_producto_id": 8,
                "url": "https://storage.rassa.com/productos/aguacate_01.jpg",
                "es_principal": True,
            },
            {
                "id_imagen": 4,
                "fk_producto_id": 13,
                "url": "https://storage.rassa.com/productos/queso_01.jpg",
                "es_principal": True,
            },
        ]
        for i in imagenes:
            ProductoImagen.objects.update_or_create(id_imagen=i["id_imagen"], defaults=i)
        self.stdout.write("  Imágenes de producto: OK")

    # ------------------------------------------------------------------
    # 14. RECOLECCIÓN
    # ------------------------------------------------------------------

    def _seed_recoleccion(self):
        recolecciones = [
            {
                "id_recoleccion": 1,
                "fk_agricultor_id": 1,
                "fecha_recoleccion": "2026-06-07",
                "hora_inicio": "07:00",
                "hora_fin": "09:00",
                "estado": "recolectado",
                "comentarios": "Tomate, cebolla, zanahoria listos",
            },
            {
                "id_recoleccion": 2,
                "fk_agricultor_id": 1,
                "fecha_recoleccion": "2026-06-14",
                "hora_inicio": "07:00",
                "hora_fin": None,
                "estado": "pendiente",
                "comentarios": "Programada para la próxima semana",
            },
            {
                "id_recoleccion": 3,
                "fk_agricultor_id": 3,
                "fecha_recoleccion": "2026-06-07",
                "hora_inicio": "08:00",
                "hora_fin": "10:30",
                "estado": "recolectado",
                "comentarios": "Aguacate, manzana y naranja",
            },
            {
                "id_recoleccion": 4,
                "fk_agricultor_id": 7,
                "fecha_recoleccion": "2026-06-07",
                "hora_inicio": "09:00",
                "hora_fin": "10:00",
                "estado": "recolectado",
                "comentarios": "Lenteja y camote",
            },
            {
                "id_recoleccion": 5,
                "fk_agricultor_id": 9,
                "fecha_recoleccion": "2026-06-07",
                "hora_inicio": "10:30",
                "hora_fin": "11:30",
                "estado": "recolectado",
                "comentarios": "Queso, crema y leche",
            },
            {
                "id_recoleccion": 6,
                "fk_agricultor_id": 2,
                "fecha_recoleccion": "2026-06-14",
                "hora_inicio": "07:30",
                "hora_fin": None,
                "estado": "pendiente",
                "comentarios": "Pendiente de recolectar",
            },
        ]
        for r in recolecciones:
            Recoleccion.objects.update_or_create(id_recoleccion=r["id_recoleccion"], defaults=r)
        self.stdout.write("  Recolecciones: OK")

    # ------------------------------------------------------------------
    # 15. RECIBOS
    # ------------------------------------------------------------------

    def _seed_recibos(self):
        recibos = [
            {
                "id_recibo": 1,
                "fk_pago_id": 1,
                "fk_pedido_id": 1,
                "folio": "REC-20260601-001",
                "monto": Decimal("120.00"),
                "creado_en": "2026-06-01 12:00:00",
            },
            {
                "id_recibo": 2,
                "fk_pago_id": 2,
                "fk_pedido_id": 2,
                "folio": "REC-20260601-002",
                "monto": Decimal("90.00"),
                "creado_en": "2026-06-01 15:00:00",
            },
            {
                "id_recibo": 3,
                "fk_pago_id": 3,
                "fk_pedido_id": 7,
                "folio": "REC-20260603-001",
                "monto": Decimal("244.00"),
                "creado_en": "2026-06-03 14:00:00",
            },
            {
                "id_recibo": 4,
                "fk_pago_id": 4,
                "fk_pedido_id": 3,
                "folio": "REC-20260602-001",
                "monto": Decimal("180.00"),
                "creado_en": "2026-06-02 16:00:00",
            },
        ]
        for r in recibos:
            if isinstance(r.get("creado_en"), str):
                r["creado_en"] = timezone.make_aware(dt.strptime(r["creado_en"], "%Y-%m-%d %H:%M:%S"))
            Recibo.objects.update_or_create(id_recibo=r["id_recibo"], defaults=r)
        self.stdout.write("  Recibos: OK")

    # ------------------------------------------------------------------
    # 16. LIQUIDACIONES
    # ------------------------------------------------------------------

    def _seed_liquidaciones(self):
        liquidaciones = [
            {
                "id_liquidacion": 1,
                "fk_agricultor_id": 1,
                "periodo_inicio": "2026-06-01",
                "periodo_fin": "2026-06-07",
                "monto_ventas": Decimal("1250.00"),
                "comision": Decimal("125.00"),
                "monto_liquidar": Decimal("1125.00"),
                "fk_pago_liquidacion_id": 1,
                "estado": "pagada",
            },
            {
                "id_liquidacion": 2,
                "fk_agricultor_id": 3,
                "periodo_inicio": "2026-06-01",
                "periodo_fin": "2026-06-07",
                "monto_ventas": Decimal("980.00"),
                "comision": Decimal("98.00"),
                "monto_liquidar": Decimal("882.00"),
                "fk_pago_liquidacion_id": None,
                "estado": "pendiente",
            },
            {
                "id_liquidacion": 3,
                "fk_agricultor_id": 6,
                "periodo_inicio": "2026-06-01",
                "periodo_fin": "2026-06-07",
                "monto_ventas": Decimal("540.00"),
                "comision": Decimal("54.00"),
                "monto_liquidar": Decimal("486.00"),
                "fk_pago_liquidacion_id": None,
                "estado": "pendiente",
            },
            {
                "id_liquidacion": 4,
                "fk_agricultor_id": 7,
                "periodo_inicio": "2026-06-01",
                "periodo_fin": "2026-06-07",
                "monto_ventas": Decimal("420.00"),
                "comision": Decimal("42.00"),
                "monto_liquidar": Decimal("378.00"),
                "fk_pago_liquidacion_id": None,
                "estado": "pendiente",
            },
            {
                "id_liquidacion": 5,
                "fk_agricultor_id": 9,
                "periodo_inicio": "2026-06-01",
                "periodo_fin": "2026-06-07",
                "monto_ventas": Decimal("680.00"),
                "comision": Decimal("68.00"),
                "monto_liquidar": Decimal("612.00"),
                "fk_pago_liquidacion_id": 1,
                "estado": "pagada",
            },
        ]
        for liq in liquidaciones:
            Liquidacion.objects.update_or_create(id_liquidacion=liq["id_liquidacion"], defaults=liq)
        self.stdout.write("  Liquidaciones: OK")
