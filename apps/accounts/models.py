from django.db import models


class Persona(models.Model):
    id_persona = models.AutoField(primary_key=True, db_column='id_persona')
    nombre = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100, null=True, blank=True)
    fecha_nacimiento = models.DateField()
    sexo = models.CharField(max_length=1)
    domicilio = models.CharField(max_length=300)
    fk_localidad = models.IntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'persona'

    def __str__(self):
        return f"{self.nombre} {self.apellido_paterno}"


class User(models.Model):
    id_usuario = models.AutoField(primary_key=True, db_column='id_usuario')
    fk_persona = models.IntegerField(unique=True)
    telefono = models.CharField(max_length=15)
    contrasenia = models.CharField(max_length=255)
    correo = models.EmailField(max_length=150, unique=True)
    fk_rol = models.IntegerField()
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    USERNAME_FIELD = 'correo'
    REQUIRED_FIELDS = []

    class Meta:
        managed = False
        db_table = 'usuario'
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def __str__(self):
        return self.correo

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.estado

    @property
    def is_anonymous(self):
        return False

    def get_username(self):
        return self.correo

    def persona_data(self):
        try:
            return Persona.objects.get(id_persona=self.fk_persona)
        except Persona.DoesNotExist:
            return None

    def role_name(self):
        try:
            return Role.objects.get(id_rol=self.fk_rol).nombre_rol
        except Role.DoesNotExist:
            return "buyer"


class Role(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre_rol = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=300)
    creado_en = models.DateTimeField(auto_now_add=True)
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'roles'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.nombre_rol
