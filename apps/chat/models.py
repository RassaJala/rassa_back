from django.db import models


class Conversacion(models.Model):
    id_conversacion = models.AutoField(primary_key=True, db_column='id_conversacion')
    nombre = models.CharField(max_length=100, null=True, blank=True)
    tipo = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'conversacion'


class Mensaje(models.Model):
    id_mensaje = models.AutoField(primary_key=True, db_column='id_mensaje')
    fk_emisor = models.IntegerField(db_column='fk_emisor')
    fk_conversacion = models.IntegerField(db_column='fk_conversacion')
    contenido = models.TextField(db_column='contenido')
    leido = models.BooleanField(default=False, db_column='leido')
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'mensaje'


class Documento(models.Model):
    id_documento = models.AutoField(primary_key=True, db_column='id_documento')
    fk_usuario = models.IntegerField(db_column='fk_usuario')
    nombre_documento = models.CharField(max_length=100, db_column='nombre_documento')
    url_documento = models.TextField(db_column='url_documento')
    tipo_documento = models.CharField(max_length=50, db_column='tipo_documento')
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'documento'


class MensajesDocumentos(models.Model):
    id_mensaje_documento = models.AutoField(primary_key=True, db_column='id_mensaje_documento')
    fk_mensaje = models.IntegerField(db_column='fk_mensaje')
    fk_documento = models.IntegerField(db_column='fk_documento')
    creado_en = models.DateTimeField(auto_now_add=True, db_column='creado_en')
    estado = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'mensajes_documentos'
