"""Módulo de permisos basados en roles (RBAC).

Implementa el control de acceso basado en roles definido en el documento
técnico de RASSA JALA (Sección 7.2 y 9.1).

Roles del sistema:
    - Administrador: Acceso completo a todos los módulos.
    - Agricultor: Publicación de productos, seguimiento de stock, mermas.
    - Vendedor: Gestión de pedidos, entregas, cobros.
    - Cliente: Catálogo semanal y seguimiento de pedidos propios.

Referencia:
    Documento Técnico v3, Fase 9.1 - Estrategia RBAC Implementada.
"""
