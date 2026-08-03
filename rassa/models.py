"""Django models para Rassa — mapeo de las 32 tablas de rassa_jala.sql.

Cada modelo respeta los nombres de columna originales (snake_case español)
para mantener compatibilidad con el esquema SQL existente y las consultas.

Política de on_delete:
- CASCADE: relación padre-hijo directa (ej: DetallePedido→Pedido). Si se
  elimina el padre, el hijo no tiene sentido existir.
- SET_NULL: preservar traza de auditoría o historial. Si se elimina el
  padre, el hijo queda huérfano pero conserva el registro (fk nullable).
- PROTECT: catálogos compartidos que no deben eliminarse si tienen
  registros dependientes (ej: TipoPago, EstadoPedido, Rol).
"""

from django.db import connection, models
from django.utils import timezone

from rassa.blueprints.liquidaciones.constants import ESTADOS_ACTIVOS

# ============================================================
# 1. TABLAS BASE (sin dependencias)
# ============================================================


class Rol(models.Model):
    """Define los roles del sistema (Admin, Vendedor, Agricultor, Cliente)."""

    id_rol = models.AutoField(primary_key=True)
    nombre_rol = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=300)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "roles"
        ordering = ["id_rol"]

    def __str__(self):
        return str(self.nombre_rol)


class CategoriaProducto(models.Model):
    """Categorías de productos (Verduras, Frutas, Lácteos, etc.)."""

    id_categoria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=300)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "categoria_producto"
        ordering = ["id_categoria"]

    def __str__(self):
        return str(self.nombre)


class Unidad(models.Model):
    """Unidades de medida para productos (Kilogramo, Pieza, Manojo, etc.)."""

    id_unidad = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=50, blank=True, null=True)
    nombre = models.CharField(max_length=100, blank=True, null=True)
    abreviatura = models.CharField(max_length=20, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "unidad"
        ordering = ["id_unidad"]

    def __str__(self):
        return str(self.nombre or self.tipo or self.abreviatura or self.id_unidad)


class EstadoPedido(models.Model):
    """Estados posibles de un pedido (pendiente, confirmado, entregado, etc.)."""

    id_estado = models.AutoField(primary_key=True)
    tipo_estado = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=300)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "estado_pedido"
        ordering = ["id_estado"]

    def __str__(self):
        return str(self.tipo_estado)


class DecisionMerma(models.Model):
    """Decisiones para mermas (Donar, Desechar, Vender más barato, Compostar)."""

    id_decision = models.AutoField(primary_key=True)
    decision = models.CharField(max_length=50)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "decision_merma"
        ordering = ["id_decision"]

    def __str__(self):
        return str(self.decision)


# ============================================================
# 2. MUNICIPIO Y LOCALIDAD
# ============================================================


class Municipio(models.Model):
    """Municipios del estado de Nayarit."""

    id_municipio = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "municipio"
        ordering = ["id_municipio"]

    def __str__(self):
        return str(self.nombre)


class Localidad(models.Model):
    """Localidades dentro de un municipio."""

    id_localidad = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=150)
    fk_municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE, db_column="fk_municipio")
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "localidad"
        ordering = ["id_localidad"]

    def __str__(self):
        return f"{str(self.nombre)} ({str(self.fk_municipio)})"


# ============================================================
# 3. PERSONA Y USUARIO
# ============================================================


class Persona(models.Model):
    """Datos personales de un individuo (nombre, fecha de nacimiento, domicilio)."""

    SEXO_CHOICES = [
        ("M", "Masculino"),
        ("F", "Femenino"),
        ("O", "Otro"),
    ]

    id_persona = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100, blank=True, null=True)
    fecha_nacimiento = models.DateField()
    sexo = models.CharField(max_length=1, choices=SEXO_CHOICES)
    domicilio = models.CharField(max_length=300)
    fk_localidad = models.ForeignKey(
        Localidad,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="fk_localidad",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "persona"
        ordering = ["id_persona"]

    def __str__(self):
        return f"{str(self.nombre)} {str(self.apellido_paterno)}"


class Usuario(models.Model):
    """Usuario del sistema con credenciales y rol asignado.

    La autenticación se realiza mediante django.contrib.auth.models.User
    (tabla auth_user). Este modelo almacena datos de negocio adicionales.
    """

    id_usuario = models.AutoField(primary_key=True)
    fk_user = models.OneToOneField(
        "auth.User",
        on_delete=models.SET_NULL,
        db_column="fk_user",
        related_name="usuario",
        null=True,
        blank=True,
    )
    fk_persona = models.OneToOneField(Persona, on_delete=models.CASCADE, db_column="fk_persona")
    telefono = models.CharField(max_length=15)
    correo = models.CharField(max_length=150, unique=True)
    fk_rol = models.ForeignKey(Rol, on_delete=models.PROTECT, db_column="fk_rol")
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "usuario"
        ordering = ["id_usuario"]

    def __str__(self):
        return f"{str(self.correo)} ({str(self.fk_rol)})"

    def tiene_rol(self, nombre_rol: str) -> bool:
        """Verifica si el usuario tiene el rol indicado."""
        return self.fk_rol.nombre_rol == nombre_rol


# ============================================================
# 4. FAMILIAS
# ============================================================


class Familia(models.Model):
    """Grupo familiar de agricultores."""

    id_familia = models.AutoField(primary_key=True)
    fk_jefe_familia = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_jefe_familia"
    )
    nombre_familia = models.CharField(max_length=100)
    detalle_familia = models.CharField(max_length=300, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "familia"
        ordering = ["id_familia"]

    def __str__(self):
        return str(self.nombre_familia)


class FamiliaUsuario(models.Model):
    """Relación entre un usuario y su familia."""

    id_familia_usuario = models.AutoField(primary_key=True)
    fk_usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, db_column="fk_usuario")
    fk_familia = models.ForeignKey(Familia, on_delete=models.CASCADE, db_column="fk_familia")
    estado = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "familia_usuario"
        ordering = ["id_familia_usuario"]

    def __str__(self):
        return f"{str(self.fk_usuario)} → {str(self.fk_familia)}"


# ============================================================
# 5. LÍMITE DE CRÉDITO POR CLIENTE
# ============================================================


class LimiteCliente(models.Model):
    """Límite de crédito asignado a un cliente."""

    id_limite = models.AutoField(primary_key=True)
    fk_usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, db_column="fk_usuario")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "limite_cliente"
        ordering = ["id_limite"]

    def __str__(self):
        return f"{str(self.fk_usuario)} — ${self.monto}"


# ============================================================
# 6. CATÁLOGO DE PRODUCTOS
# ============================================================


class Producto(models.Model):
    """Catálogo de productos disponibles para venta."""

    id_producto = models.AutoField(primary_key=True)
    nombre_producto = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, default="")
    fk_categoria = models.ForeignKey(CategoriaProducto, on_delete=models.PROTECT, db_column="fk_categoria")
    fk_unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, db_column="fk_unidad", null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock = models.PositiveIntegerField(default=0)
    es_perecedero = models.BooleanField(default=False)
    imagen = models.TextField(blank=True, null=True)
    estado = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "producto"
        ordering = ["id_producto"]

    def __str__(self):
        return str(self.nombre_producto)


# ============================================================
# 7. PUBLICACIÓN SEMANAL
# ============================================================


class PublicacionSemanal(models.Model):
    """Publicación semanal de productos de un agricultor."""

    ESTADO_BORRADOR = "borrador"
    ESTADO_PUBLICADO = "publicado"
    ESTADO_CERRADO = "cerrado"
    ESTADO_CANCELADO = "cancelado"

    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_PUBLICADO, "Publicado"),
        (ESTADO_CERRADO, "Cerrado"),
        (ESTADO_CANCELADO, "Cancelado"),
    ]

    id_publicacion = models.AutoField(primary_key=True)
    fk_agricultor = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_agricultor"
    )
    fecha_publicacion = models.DateField()
    semana = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "publicacion_semanal"
        ordering = ["id_publicacion"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(semana__gte=1, semana__lte=52),
                name="check_semana_range",
            ),
            models.UniqueConstraint(
                fields=["fk_agricultor", "semana"],
                name="unique_agricultor_semana",
            ),
        ]

    def __str__(self):
        return f"Pub #{self.id_publicacion} — Sem {self.semana} ({str(self.estado)})"


class ProductoSemanal(models.Model):
    """Producto publicado en una publicación semanal con precio y stock."""

    ESTADO_ACTIVO = "activo"
    ESTADO_INACTIVO = "inactivo"

    ESTADO_CHOICES = [
        (ESTADO_ACTIVO, "Activo"),
        (ESTADO_INACTIVO, "Inactivo"),
    ]

    id_producto_semanal = models.AutoField(primary_key=True)
    fk_publicacion = models.ForeignKey(PublicacionSemanal, on_delete=models.CASCADE, db_column="fk_publicacion")
    fk_producto = models.ForeignKey(Producto, on_delete=models.PROTECT, db_column="fk_producto")
    fk_unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, db_column="fk_unidad")
    stock = models.PositiveIntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    foto = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activo")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "producto_semanal"
        ordering = ["id_producto_semanal"]

    def __str__(self):
        return f"{str(self.fk_producto)} — {self.stock} {str(self.fk_unidad)} @ ${self.precio}"


# ============================================================
# 8. PEDIDOS (cabecera-detalle)
# ============================================================


class PedidoCabecera(models.Model):
    """Cabecera de un pedido con totales y estado."""

    id_pedido = models.AutoField(primary_key=True)
    fk_cliente = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="fk_cliente",
        related_name="pedidos_como_cliente",
    )
    fk_estado = models.ForeignKey(
        EstadoPedido,
        on_delete=models.PROTECT,
        db_column="fk_estado",
        default=1,
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    iva = models.DecimalField(max_digits=10, decimal_places=2)
    fk_vendedor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="fk_vendedor",
        related_name="pedidos_como_vendedor",
    )
    fecha_expiracion = models.DateTimeField(blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pedido_cabecera"
        ordering = ["id_pedido"]

    def __str__(self):
        return f"Pedido #{self.id_pedido} — {str(self.fk_cliente)}"

    def save(self, *args, **kwargs):
        self.total = self.subtotal + self.iva
        super().save(*args, **kwargs)


class DetallePedido(models.Model):
    """Detalle de un pedido (línea de producto con cantidad e importe)."""

    id_detalle = models.AutoField(primary_key=True)
    fk_pedido = models.ForeignKey(PedidoCabecera, on_delete=models.CASCADE, db_column="fk_pedido")
    fk_producto_semanal = models.ForeignKey(ProductoSemanal, on_delete=models.CASCADE, db_column="fk_producto_semanal")
    nombre_producto = models.CharField(max_length=150)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad = models.PositiveIntegerField()
    importe = models.DecimalField(max_digits=10, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "detalle_pedido"
        ordering = ["id_detalle"]

    def __str__(self):
        return f"{str(self.nombre_producto)} x{self.cantidad}"

    def save(self, *args, **kwargs):
        if self.importe is None:
            self.importe = self.precio_unitario * self.cantidad
        super().save(*args, **kwargs)


# ============================================================
# 9. PAGOS
# ============================================================


class TipoPago(models.Model):
    """Tipos de pago (Efectivo, Transferencia, Depósito)."""

    id_tipo_pago = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=30, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tipo_pago"
        ordering = ["id_tipo_pago"]

    def __str__(self):
        return str(self.nombre)


class Pago(models.Model):
    """Pago registrado para un pedido."""

    id_pago = models.AutoField(primary_key=True)
    fk_pedido = models.ForeignKey(
        PedidoCabecera, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_pedido"
    )
    fk_tipo = models.ForeignKey(TipoPago, on_delete=models.PROTECT, db_column="fk_tipo")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    referencia = models.CharField(max_length=100, blank=True, null=True)
    folio = models.CharField(max_length=50, unique=True, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pago"
        ordering = ["id_pago"]
        constraints = [
            models.UniqueConstraint(fields=["fk_pedido"], name="unique_pago_per_pedido", nulls_distinct=True),
        ]

    def __str__(self):
        return f"Pago #{self.id_pago} — ${self.monto}"

    def save(self, *args, **kwargs):
        if not self.folio:
            today_str = timezone.localdate().strftime("%Y%m%d")
            lock_id = int(today_str)
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
            prefix = f"REC-{today_str}-"
            last = Pago.objects.filter(folio__startswith=prefix).order_by("id_pago").last()
            try:
                last_num = int(last.folio.rsplit("-", 1)[-1]) if last else 0
            except (ValueError, IndexError):
                last_num = 0
            next_num = last_num + 1
            self.folio = f"{prefix}{next_num:03d}"
        super().save(*args, **kwargs)


# ============================================================
# 10. MERMA
# ============================================================


class Merma(models.Model):
    """Registro de merma (pérdida) de productos."""

    id_merma = models.AutoField(primary_key=True)
    fk_producto_semanal = models.ForeignKey(
        ProductoSemanal, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_producto_semanal"
    )
    cantidad = models.PositiveIntegerField()
    motivo = models.CharField(max_length=300)
    comentarios = models.TextField(blank=True, null=True)
    fk_decision = models.ForeignKey(DecisionMerma, on_delete=models.PROTECT, db_column="fk_decision")
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "merma"
        ordering = ["id_merma"]

    def __str__(self):
        return f"Merma #{self.id_merma} — {str(self.motivo)}"


# ============================================================
# 11. CORTE (arqueo de caja)
# ============================================================


class Corte(models.Model):
    """Arqueo de caja con monto real vs teórico."""

    ESTADO_CHOICES = [
        ("abierto", "Abierto"),
        ("cerrado", "Cerrado"),
        ("cuadrado", "Cuadrado"),
    ]

    id_corte = models.AutoField(primary_key=True)
    monto_real = models.DecimalField(max_digits=10, decimal_places=2)
    monto_teorico = models.DecimalField(max_digits=10, decimal_places=2)
    diferencia = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="abierto")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "corte"
        ordering = ["id_corte"]

    def __str__(self):
        return f"Corte #{self.id_corte} — {str(self.estado)}"

    def save(self, *args, **kwargs):
        if self.diferencia is None:
            self.diferencia = self.monto_real - self.monto_teorico
        super().save(*args, **kwargs)


# ============================================================
# 12. LOGS (auditoría)
# ============================================================


class Log(models.Model):
    """Registro de auditoría de acciones en el sistema."""

    id_log = models.AutoField(primary_key=True)
    fk_usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, db_column="fk_usuario")
    descripcion = models.TextField()
    ip = models.GenericIPAddressField()
    dispositivo = models.CharField(max_length=200)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "logs"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Log #{self.id_log} — {str(self.fk_usuario)}"


# ============================================================
# 13. CHAT
# ============================================================


class Conversacion(models.Model):
    """Conversación privada o grupal entre usuarios."""

    id_conversacion = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100, blank=True, null=True)
    tipo = models.BooleanField(default=False)  # FALSE = privada, TRUE = grupal
    fk_familia = models.ForeignKey(Familia, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_familia")
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "conversacion"
        ordering = ["id_conversacion"]

    def __str__(self):
        tipo_str = "Grupal" if self.tipo else "Privada"
        return f"Conversación #{self.id_conversacion} ({tipo_str})"


class Integrante(models.Model):
    """Miembro participante en una conversación."""

    id_miembro = models.AutoField(primary_key=True)
    fk_usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, db_column="fk_usuario")
    fk_conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, db_column="fk_conversacion")
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "integrantes"
        ordering = ["id_miembro"]
        constraints = [
            models.UniqueConstraint(
                fields=["fk_usuario", "fk_conversacion"],
                name="unique_integrante_usuario_conversacion",
            ),
        ]

    def __str__(self):
        return f"{str(self.fk_usuario)} en Conv #{self.fk_conversacion_id}"


class Mensaje(models.Model):
    """Mensaje enviado dentro de una conversación."""

    id_mensaje = models.AutoField(primary_key=True)
    fk_emisor = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_emisor")
    fk_conversacion = models.ForeignKey(Conversacion, on_delete=models.CASCADE, db_column="fk_conversacion")
    contenido = models.TextField(blank=True, null=True)
    leido = models.BooleanField(default=False)
    editado = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "mensaje"
        ordering = ["id_mensaje"]

    def __str__(self):
        return f"Mensaje #{self.id_mensaje} de {str(self.fk_emisor)}"


class Documento(models.Model):
    """Documento multimedia compartido en chat (imagen, audio, video)."""

    TIPO_CHOICES = [
        ("imagen", "Imagen"),
        ("audio", "Audio"),
        ("video", "Video"),
    ]

    id_documento = models.AutoField(primary_key=True)
    fk_usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_usuario")
    nombre_documento = models.CharField(max_length=100)
    url_documento = models.TextField()
    tipo_documento = models.CharField(max_length=50, choices=TIPO_CHOICES)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "documento"
        ordering = ["id_documento"]

    def __str__(self):
        return str(self.nombre_documento)


class MensajeDocumento(models.Model):
    """Relación entre un mensaje y un documento adjunto."""

    id_mensaje_documento = models.AutoField(primary_key=True)
    fk_mensaje = models.ForeignKey(Mensaje, on_delete=models.CASCADE, db_column="fk_mensaje")
    fk_documento = models.ForeignKey(Documento, on_delete=models.CASCADE, db_column="fk_documento")
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        db_table = "mensajes_documentos"
        ordering = ["id_mensaje_documento"]
        constraints = [
            models.UniqueConstraint(
                fields=["fk_mensaje", "fk_documento"],
                name="unique_mensaje_documento",
            ),
        ]

    def __str__(self):
        return f"Msg #{self.fk_mensaje_id} ↔ Doc #{self.fk_documento_id}"


# ============================================================
# 14. TABLAS v2.1
# ============================================================


class ProductoImagen(models.Model):
    """Imagen de un producto del catálogo."""

    id_imagen = models.AutoField(primary_key=True)
    fk_producto = models.ForeignKey(Producto, on_delete=models.CASCADE, db_column="fk_producto")
    url = models.URLField(max_length=500)
    drive_file_id = models.CharField(max_length=255, blank=True, null=True)
    es_principal = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True)
    # When True, the Drive file failed to delete and needs retry cleanup.
    eliminar_pendiente = models.BooleanField(default=False)

    class Meta:
        db_table = "producto_imagen"
        ordering = ["orden", "id_imagen"]
        constraints = [
            models.UniqueConstraint(
                fields=["fk_producto"],
                condition=models.Q(es_principal=True),
                name="unique_es_principal_per_producto",
            ),
        ]

    def __str__(self):
        return f"Imagen #{self.id_imagen} — {str(self.fk_producto)}"


class Recoleccion(models.Model):
    """Programación de recolección de productos de un agricultor."""

    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("en_ruta", "En Ruta"),
        ("recolectado", "Recolectado"),
        ("cancelado", "Cancelado"),
    ]

    id_recoleccion = models.AutoField(primary_key=True)
    fk_agricultor = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_agricultor"
    )
    fecha_recoleccion = models.DateField()
    hora_inicio = models.TimeField(blank=True, null=True)
    hora_fin = models.TimeField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")
    comentarios = models.TextField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recoleccion"
        ordering = ["id_recoleccion"]

    def __str__(self):
        return f"Recolección #{self.id_recoleccion} — {self.fecha_recoleccion}"


class HistorialEstadoPedido(models.Model):
    """Historial de cambios de estado de un pedido."""

    id_historial = models.AutoField(primary_key=True)
    fk_pedido = models.ForeignKey(
        PedidoCabecera, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_pedido"
    )
    fk_estado_anterior = models.ForeignKey(
        EstadoPedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="fk_estado_anterior",
        related_name="historial_anterior",
    )
    fk_estado_nuevo = models.ForeignKey(
        EstadoPedido,
        on_delete=models.PROTECT,
        db_column="fk_estado_nuevo",
        related_name="historial_nuevo",
    )
    fk_cambiado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_cambiado_por"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "historial_estado_pedido"
        ordering = ["id_historial"]

    def __str__(self):
        return f"Historial #{self.id_historial} — Pedido #{self.fk_pedido_id}"


class Recibo(models.Model):
    """Recibo emitido por un pago recibido."""

    id_recibo = models.AutoField(primary_key=True)
    fk_pago = models.ForeignKey(Pago, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_pago")
    fk_pedido = models.ForeignKey(
        PedidoCabecera, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_pedido"
    )
    folio = models.CharField(max_length=50, unique=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "recibo"
        ordering = ["id_recibo"]

    def __str__(self):
        return f"Recibo {str(self.folio)} — ${self.monto}"


class Liquidacion(models.Model):
    """Liquidación de ventas de un agricultor en un periodo."""

    ESTADO_CHOICES = [
        ("pendiente", "Pendiente"),
        ("pagada", "Pagada"),
        ("parcial", "Parcial"),
    ]

    id_liquidacion = models.AutoField(primary_key=True)
    fk_agricultor = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, db_column="fk_agricultor"
    )
    periodo_inicio = models.DateField()
    periodo_fin = models.DateField()
    monto_ventas = models.DecimalField(max_digits=10, decimal_places=2)
    comision = models.DecimalField(max_digits=10, decimal_places=2)
    monto_liquidar = models.DecimalField(max_digits=10, decimal_places=2)
    fk_pago_liquidacion = models.ForeignKey(
        Pago,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="fk_pago_liquidacion",
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="pendiente")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "liquidacion"
        ordering = ["id_liquidacion"]
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(estado__in=ESTADOS_ACTIVOS),
                fields=["fk_agricultor", "periodo_inicio", "periodo_fin"],
                name="unique_liquidacion_agricultor_periodo_activo",
            ),
        ]

    def __str__(self):
        return f"Liquidación #{self.id_liquidacion} — {str(self.fk_agricultor)}"


class LiquidacionVenta(models.Model):
    """Snapshot de los pedidos que aportaron al cálculo de una liquidación.

    Permite que el detalle de la liquidación (ventas incluidas) sea estable
    frente a cambios futuros en el estado de los pedidos: aunque un pedido
    deje de estar `entregado` después de liquidarse, sigue contando para
    la liquidación original. Cierra el riesgo de "doble pago" si se
    re-calcula un periodo con ventas distintas en el snapshot.
    """

    id_liquidacion_venta = models.AutoField(primary_key=True)
    fk_liquidacion = models.ForeignKey(
        Liquidacion,
        on_delete=models.CASCADE,
        db_column="fk_liquidacion",
        related_name="ventas",
    )
    fk_pedido = models.ForeignKey(
        "PedidoCabecera",
        on_delete=models.PROTECT,
        db_column="fk_pedido",
        related_name="liquidaciones",
    )
    monto_aportado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total del pedido al momento de la liquidación (snapshot).",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "liquidacion_venta"
        ordering = ["id_liquidacion_venta"]
        constraints = [
            models.UniqueConstraint(
                fields=["fk_liquidacion", "fk_pedido"],
                name="unique_liquidacion_venta_pedido",
            ),
        ]

    def __str__(self):
        return f"LV #{self.id_liquidacion_venta} — liq={self.fk_liquidacion_id} pedido={self.fk_pedido_id}"
