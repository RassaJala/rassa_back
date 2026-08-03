"""Constantes de mensajes y estados del módulo de Recolecciones.

Centraliza el contrato de errores en español del módulo: antes los mensajes
estaban repartidos entre serializers.py (MSG_AGRICULTOR_*) y views.py
(MSG_FK_AGRICULTOR_ENTERO_INVALIDO y strings hardcodeados). Una sola fuente de
verdad; serializers.py y views.py importan de aquí (nadie importa constants,
así que no hay ciclos de imports).
"""

from rassa.models import Recoleccion

# Misma derivación que views.ESTADOS_VALIDOS pero acá: evita que el mensaje de
# error del ChoiceField dependa de views (import circular con serializers).
ESTADOS_VALIDOS_STR = ", ".join(c[0] for c in Recoleccion.ESTADO_CHOICES)

MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO = "El agricultor especificado no existe o está inactivo."
MSG_AGRICULTOR_SIN_ROL = "El agricultor especificado no tiene rol Agricultor."
MSG_AGRICULTOR_DUPLICADO = "El agricultor ya tiene una recolección programada para esta fecha."
MSG_FK_AGRICULTOR_ENTERO_INVALIDO = "El campo 'fk_agricultor' debe ser un número entero válido."
MSG_ESTADO_VIA_ENDPOINT = "Use /estado/ o /cancelar/ para cambiar el estado."
MSG_AGRICULTOR_SOLO_PROPIAS = "Un agricultor solo puede consultar sus propias recolecciones."
