"""Módulo de autenticación para Rassa JALA.

Endpoints de autenticación que consumen los clientes (frontend React Native).
Diseñado para ser compatible con el AuthContext.tsx del frontend.

Endpoints:
    - POST /api/auth/login-api/  → Login con email/contraseña
    - POST /api/auth/register/   → Registro de nuevo usuario
    - GET  /api/auth/me/         → Datos del usuario autenticado

Referencia:
    Documento Técnico v3, Fase 13.4 - Módulo M3 (Usuarios y Roles).
"""
