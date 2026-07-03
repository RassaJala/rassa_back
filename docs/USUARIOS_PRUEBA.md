# RASSA JALA - Usuarios de Prueba

**Documento de referencia para desarrollo y testing**

_Versión: 1.0_
_Fecha: 02/07/26_

---

## 1. Credenciales de Login

### Login API

| Campo        | Valor                       |
| ------------ | --------------------------- |
| Endpoint     | `POST /api/auth/login-api/` |
| Content-Type | `application/json`          |

**Request Body:**

```json
{
  "email": "admin@rassa.com",
  "password": "admin123"
}
```

**Response Body:**

```json
{
  "success": true,
  "message": "Login exitoso",
  "remember": false,
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": 11,
    "email": "admin@rassa.com",
    "phone_number": "4610000001",
    "role": "Administrador",
    "first_name": "Admin",
    "last_name": "Sistema"
  }
}
```

---

## 2. Usuarios por Rol

### 2.1 Administrador (1 usuario)

| #   | Nombre              | Email             | Teléfono   | Contraseña | Rol           |
| --- | ------------------- | ----------------- | ---------- | ---------- | ------------- |
| 11  | Admin Sistema RASSA | `admin@rassa.com` | 4610000001 | `admin123` | Administrador |

**Permisos:** Acceso total a todas las funciones del sistema.

---

### 2.2 Vendedor (1 usuario)

| #   | Nombre                     | Email                | Teléfono   | Contraseña    | Rol      |
| --- | -------------------------- | -------------------- | ---------- | ------------- | -------- |
| 12  | Vendedor Universidad RASSA | `vendedor@rassa.com` | 4610000002 | `vendedor123` | Vendedor |

**Permisos:** Gestiona pedidos, pagos, mermas y recolección.

---

### 2.3 Agricultores (6 usuarios)

| #   | Nombre                  | Email                        | Teléfono   | Contraseña  | Rol        | Localidad                    |
| --- | ----------------------- | ---------------------------- | ---------- | ----------- | ---------- | ---------------------------- |
| 1   | Juan Pérez García       | `juan.perez@email.com`       | 4611234567 | `juan123`   | Agricultor | Apaseo el Alto - Centro      |
| 2   | María López Hernández   | `maria.lopez@email.com`      | 4612345678 | `maria123`  | Agricultor | Apaseo el Grande - Centro    |
| 3   | Pedro González Martínez | `pedro.gonzalez@email.com`   | 4613456789 | `pedro123`  | Agricultor | Celaya - Centro              |
| 6   | Rosa Martínez Gómez     | `rosa.martinez@email.com`    | 4616789012 | `rosa123`   | Agricultor | Apaseo el Alto - San Bartolo |
| 7   | Carlos Hernández Luna   | `carlos.hernandez@email.com` | 4617890123 | `carlos123` | Agricultor | Apaseo el Grande - Ixtla     |
| 9   | Luis Flores Ramos       | `luis.flores@email.com`      | 4619012345 | `luis123`   | Agricultor | Salvatierra - San Isidro     |

**Permisos:** Publicar productos los lunes, coordinar recolección, chatear con clientes.

**Familias:**

| Familia           | Jefe de Familia  | Miembros                      |
| ----------------- | ---------------- | ----------------------------- |
| Familia Pérez     | Juan Pérez       | Juan Pérez, María López       |
| Familia González  | Pedro González   | Pedro González, Rosa Martínez |
| Familia Hernández | Carlos Hernández | Carlos Hernández, Luis Flores |

---

### 2.4 Clientes (4 usuarios)

| #   | Nombre               | Email                    | Teléfono   | Contraseña  | Rol     | Localidad                     | Límite Crédito |
| --- | -------------------- | ------------------------ | ---------- | ----------- | ------- | ----------------------------- | -------------- |
| 4   | Ana Ramírez Cruz     | `ana.ramirez@email.com`  | 4614567890 | `ana123`    | Cliente | Salvatierra - Centro          | $500.00        |
| 5   | José Sánchez Flores  | `jose.sanchez@email.com` | 4615678901 | `jose123`   | Cliente | Cortazar - Centro             | $300.00        |
| 8   | Sofía Torres Vázquez | `sofia.torres@email.com` | 4618901234 | `sofia123`  | Cliente | Celaya - San Miguel           | $750.00        |
| 10  | Martha Díaz Reyes    | `martha.diaz@email.com`  | 4610123456 | `martha123` | Cliente | Cortazar - Cañada de Caracheo | $400.00        |

**Permisos:** Ver catálogo, realizar pedidos, chatear con agricultores.

---

## 3. Datos de Personas

| #   | Nombre   | Ap. Paterno | Ap. Materno | Fecha Nac. | Sexo | Domicilio         | Localidad                     |
| --- | -------- | ----------- | ----------- | ---------- | ---- | ----------------- | ----------------------------- |
| 1   | Juan     | Pérez       | García      | 1985-03-15 | M    | Av. Principal 123 | Apaseo el Alto - Centro       |
| 2   | María    | López       | Hernández   | 1990-07-22 | F    | Calle Hidalgo 45  | Apaseo el Grande - Centro     |
| 3   | Pedro    | González    | Martínez    | 1978-11-08 | M    | Benito Juárez 78  | Celaya - Centro               |
| 4   | Ana      | Ramírez     | Cruz        | 1995-02-14 | F    | Zaragoza 12       | Salvatierra - Centro          |
| 5   | José     | Sánchez     | Flores      | 1982-09-30 | M    | Allende 56        | Cortazar - Centro             |
| 6   | Rosa     | Martínez    | Gómez       | 1988-06-18 | F    | Morelos 34        | Apaseo el Alto - San Bartolo  |
| 7   | Carlos   | Hernández   | Luna        | 1992-12-25 | M    | Insurgentes 90    | Apaseo el Grande - Ixtla      |
| 8   | Sofía    | Torres      | Vázquez     | 1997-04-03 | F    | Reforma 67        | Celaya - San Miguel           |
| 9   | Luis     | Flores      | Ramos       | 1975-10-20 | M    | Independencia 23  | Salvatierra - San Isidro      |
| 10  | Martha   | Díaz        | Reyes       | 1993-08-12 | F    | Hidalgo 89        | Cortazar - Cañada de Caracheo |
| 11  | Admin    | Sistema     | RASSA       | 1990-01-01 | M    | Universidad S/N   | Celaya - Centro               |
| 12  | Vendedor | Universidad | RASSA       | 1992-01-01 | F    | Universidad S/N   | Celaya - Centro               |

---

## 4. Datos de Ubicación

### 4.1 Municipios

| ID  | Nombre           |
| --- | ---------------- |
| 1   | Apaseo el Alto   |
| 2   | Apaseo el Grande |
| 3   | Celaya           |
| 4   | Salvatierra      |
| 5   | Cortazar         |
| 6   | Tarimoro         |

### 4.2 Localidades

| ID  | Nombre             | Municipio        |
| --- | ------------------ | ---------------- |
| 1   | Centro             | Apaseo el Alto   |
| 2   | San Bartolo        | Apaseo el Alto   |
| 3   | La Joya            | Apaseo el Alto   |
| 4   | Centro             | Apaseo el Grande |
| 5   | Ixtla              | Apaseo el Grande |
| 6   | San Juan           | Apaseo el Grande |
| 7   | Centro             | Celaya           |
| 8   | San Miguel         | Celaya           |
| 9   | Rincón de Tamayo   | Celaya           |
| 10  | Centro             | Salvatierra      |
| 11  | San Isidro         | Salvatierra      |
| 12  | La Estancia        | Salvatierra      |
| 13  | Centro             | Cortazar         |
| 14  | Cañada de Caracheo | Cortazar         |
| 15  | Centro             | Tarimoro         |
| 16  | San José de Horta  | Tarimoro         |

---

## 5. Catálogo de Productos

### 5.1 Categorías

| ID  | Nombre             | Descripción                           |
| --- | ------------------ | ------------------------------------- |
| 1   | Verduras           | Verduras frescas del campo            |
| 2   | Frutas             | Frutas de temporada                   |
| 3   | Lácteos            | Quesos, crema, leche y derivados      |
| 4   | Legumbres          | Frijol, lenteja, garbanzo y similares |
| 5   | Hierbas y Especias | Cilantro, perejil, hierbabuena, etc.  |
| 6   | Tubérculos         | Papa, camote, zanahoria, betabel      |

### 5.2 Unidades

| ID  | Tipo      |
| --- | --------- |
| 1   | Kilogramo |
| 2   | Pieza     |
| 3   | Manojo    |
| 4   | Litro     |
| 5   | Docena    |

### 5.3 Productos

| ID  | Nombre         | Categoría          | Perecedero |
| --- | -------------- | ------------------ | ---------- |
| 1   | Tomate Saladet | Verduras           | Sí         |
| 2   | Cebolla Blanca | Verduras           | Sí         |
| 3   | Lechuga Romana | Verduras           | Sí         |
| 4   | Zanahoria      | Tubérculos         | Sí         |
| 5   | Papa           | Tubérculos         | Sí         |
| 6   | Chile Serrano  | Verduras           | Sí         |
| 7   | Cilantro       | Hierbas y Especias | Sí         |
| 8   | Aguacate       | Frutas             | Sí         |
| 9   | Manzana        | Frutas             | Sí         |
| 10  | Naranja        | Frutas             | Sí         |
| 11  | Frijol Negro   | Legumbres          | No         |
| 12  | Lenteja        | Legumbres          | No         |
| 13  | Queso Fresco   | Lácteos            | Sí         |
| 14  | Crema          | Lácteos            | Sí         |
| 15  | Betabel        | Tubérculos         | Sí         |
| 16  | Espinaca       | Verduras           | Sí         |
| 17  | Calabacita     | Verduras           | Sí         |
| 18  | Perejil        | Hierbas y Especias | Sí         |
| 19  | Camote         | Tubérculos         | Sí         |
| 20  | Leche Bronca   | Lácteos            | Sí         |

---

## 6. Productos Semanales (Semana 24)

| ID  | Producto       | Agricultor       | Unidad    | Stock | Precio |
| --- | -------------- | ---------------- | --------- | ----- | ------ |
| 1   | Tomate Saladet | Juan Pérez       | Kilogramo | 50    | $25.00 |
| 2   | Cebolla Blanca | Juan Pérez       | Kilogramo | 40    | $18.00 |
| 3   | Zanahoria      | Juan Pérez       | Kilogramo | 30    | $22.00 |
| 4   | Chile Serrano  | Juan Pérez       | Kilogramo | 15    | $35.00 |
| 5   | Cilantro       | Juan Pérez       | Manojo    | 25    | $10.00 |
| 6   | Lechuga Romana | María López      | Pieza     | 30    | $15.00 |
| 7   | Espinaca       | María López      | Manojo    | 20    | $12.00 |
| 8   | Calabacita     | María López      | Kilogramo | 25    | $14.00 |
| 9   | Aguacate       | Pedro González   | Pieza     | 20    | $35.00 |
| 10  | Manzana        | Pedro González   | Kilogramo | 30    | $28.00 |
| 11  | Naranja        | Pedro González   | Docena    | 25    | $22.00 |
| 12  | Frijol Negro   | Pedro González   | Kilogramo | 15    | $30.00 |
| 13  | Papa           | Rosa Martínez    | Kilogramo | 35    | $16.00 |
| 14  | Betabel        | Rosa Martínez    | Kilogramo | 20    | $20.00 |
| 15  | Perejil        | Rosa Martínez    | Manojo    | 15    | $8.00  |
| 16  | Lenteja        | Carlos Hernández | Kilogramo | 20    | $28.00 |
| 17  | Camote         | Carlos Hernández | Kilogramo | 18    | $18.00 |
| 18  | Queso Fresco   | Luis Flores      | Kilogramo | 10    | $60.00 |
| 19  | Crema          | Luis Flores      | Litro     | 8     | $35.00 |
| 20  | Leche Bronca   | Luis Flores      | Litro     | 12    | $18.00 |

---

## 7. Estados de Pedido

| ID  | Estado             | Descripción                                          |
| --- | ------------------ | ---------------------------------------------------- |
| 1   | pendiente          | El cliente realizó el pedido, esperando confirmación |
| 2   | confirmado         | El vendedor confirmó el pedido                       |
| 3   | en_preparacion     | El vendedor está preparando los productos            |
| 4   | listo_para_retirar | El pedido está listo, el cliente puede pasar por él  |
| 5   | entregado          | El cliente recogió el pedido                         |
| 6   | cancelado          | El pedido fue cancelado                              |
| 7   | activo             | El apartado/pedido está activo en el sistema         |

---

## 8. Tipos de Pago

| ID  | Nombre        |
| --- | ------------- |
| 1   | Efectivo      |
| 2   | Transferencia |
| 3   | Depósito      |

---

## 9. Decisiones de Merma

| ID  | Decisión          |
| --- | ----------------- |
| 1   | Donar             |
| 2   | Desechar          |
| 3   | Vender más barato |
| 4   | Compostar         |

---

## 10. Resumen de Datos

| Tabla               | Registros |
| ------------------- | --------- |
| Roles               | 4         |
| Categorías          | 6         |
| Unidades            | 5         |
| Estados Pedido      | 7         |
| Decisiones Merma    | 4         |
| Tipos Pago          | 3         |
| Municipios          | 6         |
| Localidades         | 16        |
| Personas            | 12        |
| Usuarios            | 12        |
| Familias            | 3         |
| Familia-Usuarios    | 6         |
| Límites Cliente     | 4         |
| Productos           | 20        |
| Publicaciones       | 9         |
| Productos Semanales | 20        |
| Pedidos             | 10        |
| Detalles Pedido     | 29        |
| Pagos               | 4         |
| Cortes              | 3         |
| Historial Estado    | 10        |
| Mermas              | 5         |
| Logs                | 15        |
| Conversaciones      | 5         |
| Integrantes         | 12        |
| Mensajes            | 15        |
| Documentos          | 5         |
| Mensajes-Documentos | 4         |
| Imágenes            | 10        |
| Recolecciones       | 3         |
| Recibos             | 3         |
| Liquidaciones       | 2         |
| **Total**           | **~250**  |

---

**Documento generado para desarrollo y testing de RASSA JALA.**
