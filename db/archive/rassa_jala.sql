-- ============================================================
-- RASSA - JALA v3.1
-- Migración unificada: Esquema + Seeders (datos de prueba)
-- PostgreSQL
--
-- Este archivo combina:
--   1) Esquema (base.sql) con la tabla producto restaurando
--      la columna "estado" + el modelo de chat actualizado
--      (conversacion / integrantes / documento / mensajes_documentos)
--   2) Seeders actualizados para el nuevo modelo de chat
--
-- Uso:
--   psql -U <usuario> -d <basededatos> -f rassa_jala_v3_full.sql
-- ============================================================

BEGIN;

-- ============================================================
-- ESQUEMA LÓGICO BD RASSA - JALA v3.0 DEFINITIVA
-- PostgreSQL
--
-- FUSIÓN: v2.0 (original) + v2.1 (tablas financieras/recolección)
-- + correcciones para cubrir las 50 consultas del profesor
--
-- TABLAS: 32 en total
-- ============================================================

-- ============================================================
-- 1. TABLAS BASE (sin dependencias)
-- ============================================================

CREATE TABLE roles (
    id_rol       SERIAL       PRIMARY KEY,
    nombre_rol   VARCHAR(50)  NOT NULL UNIQUE,
    descripcion  VARCHAR(300) NOT NULL,
    creado_en    TIMESTAMP    NOT NULL DEFAULT NOW(),
    estado       BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE categoria_producto (
    id_categoria  SERIAL       PRIMARY KEY,
    nombre        VARCHAR(50)  NOT NULL,
    descripcion   VARCHAR(300) NOT NULL,
    creado_en     TIMESTAMP    NOT NULL DEFAULT NOW(),
    estado        BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE unidad (
    id_unidad  SERIAL      PRIMARY KEY,
    tipo       VARCHAR(50) NOT NULL,
    creado_en  TIMESTAMP   NOT NULL DEFAULT NOW(),
    estado     BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE estado_pedido (
    id_estado    SERIAL       PRIMARY KEY,
    tipo_estado  VARCHAR(50)  NOT NULL UNIQUE,
    -- VALORES: pendiente, confirmado, en_preparacion,
    --          listo_para_retirar, entregado, cancelado, activo
    descripcion  VARCHAR(300) NOT NULL,
    creado_en    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE decision_merma (
    id_decision  SERIAL       PRIMARY KEY,
    decision     VARCHAR(50)  NOT NULL,
    -- VALORES: donar, desechar, vender_barato, compostar
    creado_en    TIMESTAMP    NOT NULL DEFAULT NOW(),
    estado       BOOLEAN      NOT NULL DEFAULT TRUE
);


-- ============================================================
-- 2. MUNICIPIO Y LOCALIDAD
-- Origen: v2.0 original + consulta #2
-- ============================================================

CREATE TABLE municipio (
    id_municipio  SERIAL       PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL
);

CREATE TABLE localidad (
    id_localidad  SERIAL       PRIMARY KEY,
    nombre        VARCHAR(150) NOT NULL,
    fk_municipio  INT          NOT NULL,

    CONSTRAINT fk_localidad_municipio FOREIGN KEY (fk_municipio)
        REFERENCES municipio (id_municipio)
);


-- ============================================================
-- 3. PERSONA Y USUARIO
-- v2.0 original + fk_localidad
-- ============================================================

CREATE TABLE persona (
    id_persona        SERIAL        PRIMARY KEY,
    nombre            VARCHAR(100)  NOT NULL,
    apellido_paterno  VARCHAR(100)  NOT NULL,
    apellido_materno  VARCHAR(100),
    fecha_nacimiento  DATE          NOT NULL,
    sexo              CHAR(1)       NOT NULL CHECK(sexo IN ('M', 'F', 'O')),
    domicilio         VARCHAR(300)  NOT NULL,
    fk_localidad      INT,          -- Ubicación del agricultor para recolección
    creado_en         TIMESTAMP     NOT NULL DEFAULT NOW(),
    estado            BOOLEAN       NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_persona_localidad FOREIGN KEY (fk_localidad)
        REFERENCES localidad (id_localidad)
);

CREATE TABLE usuario (
    id_usuario   SERIAL        PRIMARY KEY,
    fk_persona   INT           NOT NULL UNIQUE,
    telefono     VARCHAR(15)   NOT NULL,
    contrasenia  VARCHAR(255)  NOT NULL,
    correo       VARCHAR(150)  NOT NULL UNIQUE,
    fk_rol       INT           NOT NULL,
    creado_en    TIMESTAMP     NOT NULL DEFAULT NOW(),
    estado       BOOLEAN       NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_usuario_persona FOREIGN KEY (fk_persona)
        REFERENCES persona (id_persona),
    CONSTRAINT fk_usuario_rol FOREIGN KEY (fk_rol)
        REFERENCES roles (id_rol)
);


-- ============================================================
-- 4. FAMILIAS
-- ============================================================

CREATE TABLE familia (
    id_familia       SERIAL        PRIMARY KEY,
    fk_jefe_familia  INT           NOT NULL,
    nombre_familia   VARCHAR(100)  NOT NULL,
    detalle_familia  VARCHAR(300),
    creado_en        TIMESTAMP     NOT NULL DEFAULT NOW(),
    estado           BOOLEAN       NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_familia_jefe FOREIGN KEY (fk_jefe_familia)
        REFERENCES usuario (id_usuario)
);

CREATE TABLE familia_usuario (
    id_familia_usuario  SERIAL   PRIMARY KEY,
    fk_usuario          INT      NOT NULL UNIQUE,
    fk_familia          INT      NOT NULL,
    estado              BOOLEAN  NOT NULL DEFAULT TRUE,
    creado_en           TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_familia_usuario_usuario FOREIGN KEY (fk_usuario)
        REFERENCES usuario (id_usuario),
    CONSTRAINT fk_familia_usuario_familia FOREIGN KEY (fk_familia)
        REFERENCES familia (id_familia)
);


-- ============================================================
-- 5. LÍMITE DE CRÉDITO POR CLIENTE
-- ============================================================

CREATE TABLE limite_cliente (
    id_limite  SERIAL         PRIMARY KEY,
    fk_usuario INT            NOT NULL UNIQUE,
    monto      NUMERIC(10,2)  NOT NULL CHECK(monto >= 0),
    creado_en  TIMESTAMP      NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_limite_usuario FOREIGN KEY (fk_usuario)
        REFERENCES usuario (id_usuario)
);


-- ============================================================
-- 6. CATÁLOGO DE PRODUCTOS
-- v2.1 + es_perecedero (consulta #8)
-- ============================================================

CREATE TABLE producto (
    id_producto     SERIAL        PRIMARY KEY,
    nombre_producto VARCHAR(150)  NOT NULL,
    fk_categoria    INT           NOT NULL,
    es_perecedero   BOOLEAN       DEFAULT FALSE,  -- Consulta #8
    estado          BOOLEAN       NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMP     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_producto_categoria FOREIGN KEY (fk_categoria)
        REFERENCES categoria_producto (id_categoria)
);


-- ============================================================
-- 7. PUBLICACIÓN SEMANAL
-- ============================================================

CREATE TABLE publicacion_semanal (
    id_publicacion    SERIAL        PRIMARY KEY,
    fk_agricultor     INT           NOT NULL,
    fecha_publicacion DATE          NOT NULL,
    semana            INTEGER       NOT NULL CHECK(semana BETWEEN 1 AND 52),
    estado            VARCHAR(20)   NOT NULL DEFAULT 'borrador'
        CHECK(estado IN ('borrador', 'publicado', 'cerrado')),
    creado_en         TIMESTAMP     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_publicacion_agricultor FOREIGN KEY (fk_agricultor)
        REFERENCES usuario (id_usuario)
);

CREATE TABLE producto_semanal (
    id_producto_semanal  SERIAL          PRIMARY KEY,
    fk_publicacion       INT             NOT NULL,
    fk_producto          INT             NOT NULL,
    fk_unidad            INT             NOT NULL,
    stock                INTEGER         NOT NULL CHECK(stock >= 0),
    precio               NUMERIC(10,2)   NOT NULL CHECK(precio > 0),
    foto                 TEXT,
    estado               VARCHAR(20)     DEFAULT 'activo',
    creado_en            TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_prodsem_publicacion FOREIGN KEY (fk_publicacion)
        REFERENCES publicacion_semanal (id_publicacion),
    CONSTRAINT fk_prodsem_producto FOREIGN KEY (fk_producto)
        REFERENCES producto (id_producto),
    CONSTRAINT fk_prodsem_unidad FOREIGN KEY (fk_unidad)
        REFERENCES unidad (id_unidad)
);


-- ============================================================
-- 8. PEDIDOS (cabecera-detalle)
-- v2.1 + fk_vendedor (consulta #28) + fecha_expiracion (consulta #25)
-- ============================================================

CREATE TABLE pedido_cabecera (
    id_pedido        SERIAL          PRIMARY KEY,
    fk_cliente       INT             NOT NULL,
    fk_estado        INT             NOT NULL DEFAULT 1,
    subtotal         NUMERIC(10,2)   NOT NULL,
    iva              NUMERIC(10,2)   NOT NULL,
    fk_vendedor      INT,                        -- Consulta #28
    fecha_expiracion TIMESTAMP,                  -- Consulta #25
    total            NUMERIC(10,2)   GENERATED ALWAYS AS (subtotal + iva) STORED,
    creado_en        TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_pedido_cliente FOREIGN KEY (fk_cliente)
        REFERENCES usuario (id_usuario),
    CONSTRAINT fk_pedido_estado FOREIGN KEY (fk_estado)
        REFERENCES estado_pedido (id_estado),
    CONSTRAINT fk_pedido_vendedor FOREIGN KEY (fk_vendedor)
        REFERENCES usuario (id_usuario)
);

CREATE TABLE detalle_pedido (
    id_detalle           SERIAL          PRIMARY KEY,
    fk_pedido            INT             NOT NULL,
    fk_producto_semanal  INT             NOT NULL,
    nombre_producto      VARCHAR(150)    NOT NULL,
    precio_unitario      NUMERIC(10,2)   NOT NULL,
    cantidad             INTEGER         NOT NULL CHECK(cantidad > 0),
    importe              NUMERIC(10,2)   GENERATED ALWAYS AS (precio_unitario * cantidad) STORED,
    creado_en            TIMESTAMP       NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_detalle_pedido FOREIGN KEY (fk_pedido)
        REFERENCES pedido_cabecera (id_pedido),
    CONSTRAINT fk_detalle_prodsem FOREIGN KEY (fk_producto_semanal)
        REFERENCES producto_semanal (id_producto_semanal)
);


-- ============================================================
-- 9. PAGOS
-- ============================================================

CREATE TABLE tipo_pago (
    id_tipo_pago  SERIAL       PRIMARY KEY,
    nombre        VARCHAR(30)  NOT NULL UNIQUE,
    -- VALORES: efectivo, transferencia, deposito
    creado_en     TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE pago (
    id_pago      SERIAL         PRIMARY KEY,
    fk_pedido    INT            NOT NULL,
    fk_tipo      INT            NOT NULL,
    monto        NUMERIC(10,2)  NOT NULL CHECK(monto > 0),
    referencia   VARCHAR(100),
    creado_en    TIMESTAMP      NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_pago_pedido FOREIGN KEY (fk_pedido)
        REFERENCES pedido_cabecera (id_pedido),
    CONSTRAINT fk_pago_tipo FOREIGN KEY (fk_tipo)
        REFERENCES tipo_pago (id_tipo_pago)
);


-- ============================================================
-- 10. MERMA
-- ============================================================

CREATE TABLE merma (
    id_merma             SERIAL        PRIMARY KEY,
    fk_producto_semanal  INT           NOT NULL,
    cantidad             INTEGER       NOT NULL CHECK(cantidad > 0),
    motivo               VARCHAR(300)  NOT NULL,
    comentarios          TEXT,
    fk_decision          INT           NOT NULL,
    creado_en            TIMESTAMP     NOT NULL DEFAULT NOW(),
    estado               BOOLEAN       NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_merma_prodsem FOREIGN KEY (fk_producto_semanal)
        REFERENCES producto_semanal (id_producto_semanal),
    CONSTRAINT fk_merma_decision FOREIGN KEY (fk_decision)
        REFERENCES decision_merma (id_decision)
);


-- ============================================================
-- 11. CORTE (arqueo de caja)
-- ============================================================

CREATE TABLE corte (
    id_corte       SERIAL         PRIMARY KEY,
    monto_real     NUMERIC(10,2)  NOT NULL,
    monto_teorico  NUMERIC(10,2)  NOT NULL,
    diferencia     NUMERIC(10,2)  GENERATED ALWAYS AS (monto_real - monto_teorico) STORED,
    estado         VARCHAR(20)    NOT NULL DEFAULT 'abierto'
        CHECK(estado IN ('abierto', 'cerrado', 'cuadrado')),
    creado_en      TIMESTAMP      NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 12. LOGS (auditoría)
-- ============================================================

CREATE TABLE logs (
    id_log       SERIAL        PRIMARY KEY,
    fk_usuario   INT           NOT NULL,
    descripcion  TEXT          NOT NULL,
    ip           INET          NOT NULL,
    dispositivo  VARCHAR(200)  NOT NULL,
    creado_en    TIMESTAMP     NOT NULL DEFAULT NOW(),
    estado       BOOLEAN       NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_log_usuario FOREIGN KEY (fk_usuario)
        REFERENCES usuario (id_usuario)
);


-- ============================================================
-- 13. CHAT
-- Origen: v2.0 original
-- ============================================================


CREATE TABLE conversacion (
    id_conversacion  SERIAL   PRIMARY KEY,
    nombre           VARCHAR(100) ,
    tipo boolean NOT NULL DEFAULT FALSE, -- FALSE = privada, TRUE = grupal
    creado_en        TIMESTAMP DEFAULT NOW(),
    estado boolean NOT NULL DEFAULT TRUE
);


CREATE TABLE integrantes (
    id_miembro  SERIAL    PRIMARY KEY,
    fk_usuario  INT       NOT NULL,
    fk_conversacion INT NOT NULL,
    creado_en   TIMESTAMP DEFAULT NOW(),
    estado boolean NOT NULL DEFAULT TRUE,
    constraint fk_integrante_conversacion FOREIGN KEY (fk_conversacion)
        REFERENCES conversacion (id_conversacion),
    CONSTRAINT fk_grupo_miembro_usuario FOREIGN KEY (fk_usuario)
        REFERENCES usuario (id_usuario),
    UNIQUE ( fk_usuario, fk_conversacion)
);

CREATE TABLE mensaje (
    id_mensaje      SERIAL       PRIMARY KEY,
    fk_emisor       INT          NOT NULL,
    fk_conversacion INT NOT NULL,
    contenido       TEXT         ,
    leido           BOOLEAN      DEFAULT FALSE,
    creado_en       TIMESTAMP    DEFAULT NOW(),
    estado boolean NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_msg_emisor FOREIGN KEY (fk_emisor)
        REFERENCES usuario (id_usuario),
    CONSTRAINT fk_msg_conversacion FOREIGN KEY (fk_conversacion)
        REFERENCES conversacion (id_conversacion)
);
create table documento (
    id_documento SERIAL PRIMARY KEY,
    fk_usuario INT NOT NULL,
    nombre_documento VARCHAR(100) NOT NULL,
    url_documento TEXT NOT NULL,
    tipo_documento VARCHAR(50) NOT NULL,
    check(tipo_documento IN ('imagen','audio','video')),
    creado_en TIMESTAMP DEFAULT NOW(),
    estado boolean NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_documento_usuario FOREIGN KEY (fk_usuario)
        REFERENCES usuario (id_usuario)
);
create table mensajes_documentos(
    id_mensaje_documento SERIAL PRIMARY KEY,
    fk_mensaje INT NOT NULL,
    fk_documento INT NOT NULL,
    creado_en TIMESTAMP DEFAULT NOW(),
    estado boolean NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_msg_doc_mensaje FOREIGN KEY (fk_mensaje)
        REFERENCES mensaje (id_mensaje),
    CONSTRAINT fk_msg_doc_documento FOREIGN KEY (fk_documento)
        REFERENCES documento (id_documento),
        unique(fk_mensaje, fk_documento)
);

-- ============================================================
-- 14. NUEVAS TABLAS v2.1
-- Origen: schema actualizado (financieras + logística)
-- ============================================================

-- 14a. IMÁGENES DE PRODUCTO — Consultas #9, #10
CREATE TABLE producto_imagen (
    id_imagen      SERIAL       PRIMARY KEY,
    fk_producto    INT          NOT NULL,
    url            TEXT         NOT NULL,
    es_principal   BOOLEAN      DEFAULT FALSE,
    creado_en      TIMESTAMP    DEFAULT NOW(),

    CONSTRAINT fk_img_producto FOREIGN KEY (fk_producto)
        REFERENCES producto (id_producto)
);

-- 14b. RECOLECCIÓN — Consultas #31, #33
CREATE TABLE recoleccion (
    id_recoleccion    SERIAL        PRIMARY KEY,
    fk_agricultor     INT           NOT NULL,
    fecha_recoleccion DATE          NOT NULL,
    hora_inicio       TIME,
    hora_fin          TIME,
    estado            VARCHAR(20)   DEFAULT 'pendiente'
        CHECK(estado IN ('pendiente', 'en_ruta', 'recolectado', 'cancelado')),
    comentarios       TEXT,
    creado_en         TIMESTAMP     DEFAULT NOW(),

    CONSTRAINT fk_recol_agricultor FOREIGN KEY (fk_agricultor)
        REFERENCES usuario (id_usuario)
);

-- 14c. HISTORIAL DE ESTADO DE PEDIDO — Consultas #34, #35
CREATE TABLE historial_estado_pedido (
    id_historial       SERIAL     PRIMARY KEY,
    fk_pedido          INT        NOT NULL,
    fk_estado_anterior INT,
    fk_estado_nuevo    INT        NOT NULL,
    fk_cambiado_por    INT        NOT NULL,
    creado_en          TIMESTAMP  DEFAULT NOW(),

    CONSTRAINT fk_hist_pedido FOREIGN KEY (fk_pedido)
        REFERENCES pedido_cabecera (id_pedido),
    CONSTRAINT fk_hist_est_ant FOREIGN KEY (fk_estado_anterior)
        REFERENCES estado_pedido (id_estado),
    CONSTRAINT fk_hist_est_nue FOREIGN KEY (fk_estado_nuevo)
        REFERENCES estado_pedido (id_estado),
    CONSTRAINT fk_hist_usuario FOREIGN KEY (fk_cambiado_por)
        REFERENCES usuario (id_usuario)
);

-- 14d. RECIBO — Consultas #38, #39, #40
CREATE TABLE recibo (
    id_recibo    SERIAL         PRIMARY KEY,
    fk_pago      INT            NOT NULL,
    fk_pedido    INT            NOT NULL,
    folio        VARCHAR(50)    NOT NULL UNIQUE,
    monto        NUMERIC(10,2)  NOT NULL,
    creado_en    TIMESTAMP      DEFAULT NOW(),

    CONSTRAINT fk_recibo_pago   FOREIGN KEY (fk_pago)
        REFERENCES pago (id_pago),
    CONSTRAINT fk_recibo_pedido FOREIGN KEY (fk_pedido)
        REFERENCES pedido_cabecera (id_pedido)
);

-- 14e. LIQUIDACIÓN — Consultas #41, #42, #43, #44, #45
CREATE TABLE liquidacion (
    id_liquidacion      SERIAL         PRIMARY KEY,
    fk_agricultor       INT            NOT NULL,
    periodo_inicio      DATE           NOT NULL,
    periodo_fin         DATE           NOT NULL,
    monto_ventas        NUMERIC(10,2)  NOT NULL,
    comision            NUMERIC(10,2)  NOT NULL,
    monto_liquidar      NUMERIC(10,2)  GENERATED ALWAYS AS (monto_ventas - comision) STORED,
    fk_pago_liquidacion INT,
    estado              VARCHAR(20)    DEFAULT 'pendiente'
        CHECK(estado IN ('pendiente', 'pagada', 'parcial')),
    creado_en           TIMESTAMP      DEFAULT NOW(),

    CONSTRAINT fk_liq_agricultor FOREIGN KEY (fk_agricultor)
        REFERENCES usuario (id_usuario),
    CONSTRAINT fk_liq_pago FOREIGN KEY (fk_pago_liquidacion)
        REFERENCES pago (id_pago)
);


-- ============================================================
-- 15. ÍNDICES
-- ============================================================

-- Búsqueda por correo (login)
CREATE INDEX idx_usuario_correo ON usuario (correo);

-- Productos por categoría
CREATE INDEX idx_producto_categoria ON producto (fk_categoria);

-- Publicaciones por agricultor y semana
CREATE INDEX idx_publicacion_agricultor_semana
    ON publicacion_semanal (fk_agricultor, semana);

-- Productos semanales por publicación
CREATE INDEX idx_prodsem_publicacion ON producto_semanal (fk_publicacion);

-- Pedidos por cliente
CREATE INDEX idx_pedido_cliente ON pedido_cabecera (fk_cliente);

-- Pedidos por estado
CREATE INDEX idx_pedido_estado ON pedido_cabecera (fk_estado);

-- Pedidos por vendedor (consulta #28)
CREATE INDEX idx_pedido_vendedor ON pedido_cabecera (fk_vendedor);

-- Detalles por pedido
CREATE INDEX idx_detalle_pedido ON detalle_pedido (fk_pedido);

-- Logs por usuario
CREATE INDEX idx_log_usuario ON logs (fk_usuario);

-- Logs por fecha
CREATE INDEX idx_log_creado ON logs (creado_en);

-- Localidades por municipio (consulta #2)
CREATE INDEX idx_localidad_municipio ON localidad (fk_municipio);

-- ============================================================
-- ÍNDICES DEL CHAT
-- ============================================================

-- Conversaciones
CREATE INDEX idx_conversacion_estado
    ON conversacion (estado);

CREATE INDEX idx_conversacion_tipo
    ON conversacion (tipo);

-- Integrantes
CREATE INDEX idx_integrantes_usuario
    ON integrantes (fk_usuario);

CREATE INDEX idx_integrantes_conversacion
    ON integrantes (fk_conversacion);

-- Mensajes
CREATE INDEX idx_mensaje_conversacion
    ON mensaje (fk_conversacion);

CREATE INDEX idx_mensaje_emisor
    ON mensaje (fk_emisor);

-- Muy útil para obtener los mensajes ordenados por fecha
CREATE INDEX idx_mensaje_conversacion_fecha
    ON mensaje (fk_conversacion, creado_en DESC);

-- Mensajes no leídos por conversación
CREATE INDEX idx_mensaje_no_leidos
    ON mensaje (fk_conversacion, leido)
    WHERE leido = FALSE;

-- Documentos
CREATE INDEX idx_documento_usuario
    ON documento (fk_usuario);

-- Relación mensaje-documento
CREATE INDEX idx_msg_doc_mensaje
    ON mensajes_documentos (fk_mensaje);

CREATE INDEX idx_msg_doc_documento
    ON mensajes_documentos (fk_documento);

-- Imágenes por producto (#9)
CREATE INDEX idx_producto_imagen ON producto_imagen (fk_producto);

-- Recolecciones por agricultor (#31)
CREATE INDEX idx_recoleccion_agricultor ON recoleccion (fk_agricultor);

-- Historial por pedido (#34)
CREATE INDEX idx_historial_pedido ON historial_estado_pedido (fk_pedido);

-- Recibos por pago (#38)
CREATE INDEX idx_recibo_pago ON recibo (fk_pago);

-- Liquidaciones por agricultor (#41)
CREATE INDEX idx_liquidacion_agricultor ON liquidacion (fk_agricultor);


-- ============================================================
-- 16. FUNCIÓN AUXILIAR
-- ============================================================

CREATE OR REPLACE FUNCTION usuario_tiene_rol(
    p_id_usuario INT,
    p_nombre_rol VARCHAR
) RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1
        FROM usuario u
        JOIN roles r ON u.fk_rol = r.id_rol
        WHERE u.id_usuario = p_id_usuario
          AND r.nombre_rol  = p_nombre_rol
    );
$$ LANGUAGE sql STABLE;

-- ============================================================
-- ============================================================
--  SEEDERS — DATOS DE PRUEBA
-- ============================================================
-- ============================================================

-- ============================================================
-- DATOS DE PRUEBA — RASSA JALA v3.0 DEFINITIVA
-- Seeders para todas las 31 tablas del sistema
-- PostgreSQL
--
-- Orden de inserción (respetando FK):
--  1. roles, categoria_producto, unidad, estado_pedido, decision_merma, tipo_pago
--  2. municipio, localidad
--  3. persona, usuario
--  4. familia, familia_usuario, limite_cliente
--  5. producto
--  6. publicacion_semanal, producto_semanal
--  7. pedido_cabecera, detalle_pedido
--  8. pago, corte
--  9. historial_estado_pedido
-- 10. merma
-- 11. logs
-- 12. conversacion, integrantes, mensaje, documento, mensajes_documentos
-- 13. producto_imagen
-- 14. recoleccion
-- 15. recibo
-- 16. liquidacion
-- ============================================================


-- ============================================================
-- 1. TABLAS BASE
-- ============================================================

INSERT INTO roles (nombre_rol, descripcion) VALUES
    ('Admin',      'Administrador del sistema. Acceso total a todas las funciones.'),
    ('Vendedor',   'Personal de la universidad. Gestiona pedidos, pagos, mermas y recolección.'),
    ('Agricultor', 'Productor del campo. Publica sus productos los lunes y coordina la recolección.'),
    ('Cliente',    'Comprador. Ve productos, compra y chatea con agricultores.');

INSERT INTO categoria_producto (nombre, descripcion) VALUES
    ('Verduras',            'Verduras frescas del campo'),
    ('Frutas',              'Frutas de temporada'),
    ('Lácteos',             'Quesos, crema, leche y derivados'),
    ('Legumbres',           'Frijol, lenteja, garbanzo y similares'),
    ('Hierbas y Especias',  'Cilantro, perejil, hierbabuena, etc.'),
    ('Tubérculos',          'Papa, camote, zanahoria, betabel');

INSERT INTO unidad (tipo) VALUES
    ('Kilogramo'),
    ('Pieza'),
    ('Manojo'),
    ('Litro'),
    ('Docena');

INSERT INTO estado_pedido (tipo_estado, descripcion) VALUES
    ('pendiente',        'El cliente realizó el pedido, esperando confirmación'),
    ('confirmado',       'El vendedor confirmó el pedido'),
    ('en_preparacion',   'El vendedor está preparando los productos'),
    ('listo_para_retirar', 'El pedido está listo, el cliente puede pasar por él'),
    ('entregado',        'El cliente recogió el pedido'),
    ('cancelado',        'El pedido fue cancelado'),
    ('activo',           'El apartado/pedido está activo en el sistema');

INSERT INTO decision_merma (decision) VALUES
    ('Donar'),
    ('Desechar'),
    ('Vender más barato'),
    ('Compostar');

INSERT INTO tipo_pago (nombre) VALUES
    ('Efectivo'),
    ('Transferencia'),
    ('Depósito');


-- ============================================================
-- 2. MUNICIPIO Y LOCALIDAD
-- ============================================================

INSERT INTO municipio (nombre) VALUES
    ('Apaseo el Alto'),
    ('Apaseo el Grande'),
    ('Celaya'),
    ('Salvatierra'),
    ('Cortazar'),
    ('Tarimoro');

INSERT INTO localidad (nombre, fk_municipio) VALUES
    ('Centro',            1),
    ('San Bartolo',       1),
    ('La Joya',           1),
    ('Centro',            2),
    ('Ixtla',             2),
    ('San Juan',          2),
    ('Centro',            3),
    ('San Miguel',        3),
    ('Rincón de Tamayo',  3),
    ('Centro',            4),
    ('San Isidro',        4),
    ('La Estancia',       4),
    ('Centro',            5),
    ('Cañada de Caracheo',5),
    ('Centro',            6),
    ('San José de Horta', 6);


-- ============================================================
-- 3. PERSONAS Y USUARIOS
-- ============================================================

INSERT INTO persona (nombre, apellido_paterno, apellido_materno, fecha_nacimiento, sexo, domicilio, fk_localidad) VALUES
    ('Juan',     'Pérez',     'García',   '1985-03-15', 'M', 'Av. Principal 123',    1),
    ('María',    'López',     'Hernández','1990-07-22', 'F', 'Calle Hidalgo 45',      4),
    ('Pedro',    'González',  'Martínez', '1978-11-08', 'M', 'Benito Juárez 78',      7),
    ('Ana',      'Ramírez',   'Cruz',     '1995-02-14', 'F', 'Zaragoza 12',           10),
    ('José',     'Sánchez',   'Flores',   '1982-09-30', 'M', 'Allende 56',            13),
    ('Rosa',     'Martínez',  'Gómez',    '1988-06-18', 'F', 'Morelos 34',            2),
    ('Carlos',   'Hernández', 'Luna',     '1992-12-25', 'M', 'Insurgentes 90',        5),
    ('Sofía',    'Torres',    'Vázquez',  '1997-04-03', 'F', 'Reforma 67',            8),
    ('Luis',     'Flores',    'Ramos',    '1975-10-20', 'M', 'Independencia 23',      11),
    ('Martha',   'Díaz',      'Reyes',    '1993-08-12', 'F', 'Hidalgo 89',            14),
    ('Admin',    'Sistema',   'RASSA',    '1990-01-01', 'M', 'Universidad S/N',       7),
    ('Vendedor', 'Universidad','RASSA',    '1992-01-01', 'F', 'Universidad S/N',       7);

-- NOTA PARA EL EQUIPO: las contraseñas se guardan EN TEXTO PLANO
-- (sin hash) únicamente para este entorno de pruebas/desarrollo,
-- para que cualquiera pueda iniciar sesión sin necesidad de conocer
-- el hash. La contraseña de cada usuario es la misma cadena que
-- aparece en la columna "contrasenia" (se repite en el comentario
-- solo por claridad). NO usar este patrón en producción: ahí sí
-- debe ir hasheada (bcrypt/argon2, etc.).
INSERT INTO usuario (fk_persona, telefono, contrasenia, correo, fk_rol) VALUES
    (1,  '4611234567', 'juan123',     'juan.perez@email.com',      3),   -- Agricultor      | password: juan123
    (2,  '4612345678', 'maria123',    'maria.lopez@email.com',     3),   -- Agricultor      | password: maria123
    (3,  '4613456789', 'pedro123',    'pedro.gonzalez@email.com',  3),   -- Agricultor      | password: pedro123
    (4,  '4614567890', 'ana123',      'ana.ramirez@email.com',     4),   -- Cliente         | password: ana123
    (5,  '4615678901', 'jose123',     'jose.sanchez@email.com',    4),   -- Cliente         | password: jose123
    (6,  '4616789012', 'rosa123',     'rosa.martinez@email.com',   3),   -- Agricultor      | password: rosa123
    (7,  '4617890123', 'carlos123',   'carlos.hernandez@email.com',3),   -- Agricultor      | password: carlos123
    (8,  '4618901234', 'sofia123',    'sofia.torres@email.com',    4),   -- Cliente         | password: sofia123
    (9,  '4619012345', 'luis123',     'luis.flores@email.com',     3),   -- Agricultor      | password: luis123
    (10, '4610123456', 'martha123',   'martha.diaz@email.com',     4),   -- Cliente         | password: martha123
    (11, '4610000001', 'admin123',    'admin@rassa.com',           1),   -- Admin           | password: admin123
    (12, '4610000002', 'vendedor123', 'vendedor@rassa.com',        2);   -- Vendedor        | password: vendedor123


-- ============================================================
-- 4. FAMILIAS
-- ============================================================

INSERT INTO familia (fk_jefe_familia, nombre_familia, detalle_familia) VALUES
    (1, 'Familia Pérez',     'Familia dedicada al cultivo de verduras en Apaseo el Alto'),
    (3, 'Familia González',  'Productores de frutas y legumbres en Celaya'),
    (7, 'Familia Hernández', 'Cultivo de hortalizas en Apaseo el Grande');

INSERT INTO familia_usuario (fk_usuario, fk_familia) VALUES
    (1, 1),   -- Juan Pérez → Familia Pérez (jefe)
    (2, 1),   -- María López → Familia Pérez (miembro)
    (3, 2),   -- Pedro González → Familia González (jefe)
    (6, 2),   -- Rosa Martínez → Familia González (miembro)
    (7, 3),   -- Carlos Hernández → Familia Hernández (jefe)
    (9, 3);   -- Luis Flores → Familia Hernández (miembro)

INSERT INTO limite_cliente (fk_usuario, monto) VALUES
    (4,  500.00),   -- Ana Ramírez:  límite $500
    (5,  300.00),   -- José Sánchez:  límite $300
    (8,  750.00),   -- Sofía Torres:  límite $750
    (10, 400.00);   -- Martha Díaz:   límite $400


-- ============================================================
-- 5. PRODUCTOS (con es_perecedero para consulta #8)
-- ============================================================

INSERT INTO producto (nombre_producto, fk_categoria, es_perecedero) VALUES
    ('Tomate Saladet',  1, TRUE),    -- Verduras - perecedero
    ('Cebolla Blanca',  1, TRUE),    -- Verduras - perecedero
    ('Lechuga Romana',  1, TRUE),    -- Verduras - perecedero
    ('Zanahoria',       6, TRUE),    -- Tubérculos - perecedero
    ('Papa',            6, TRUE),    -- Tubérculos - perecedero
    ('Chile Serrano',   1, TRUE),    -- Verduras - perecedero
    ('Cilantro',        5, TRUE),    -- Hierbas - perecedero
    ('Aguacate',        2, TRUE),    -- Frutas - perecedero
    ('Manzana',         2, TRUE),    -- Frutas - perecedero
    ('Naranja',         2, TRUE),    -- Frutas - perecedero
    ('Frijol Negro',    4, FALSE),   -- Legumbres - NO perecedero
    ('Lenteja',         4, FALSE),   -- Legumbres - NO perecedero
    ('Queso Fresco',    3, TRUE),    -- Lácteos - perecedero
    ('Crema',           3, TRUE),    -- Lácteos - perecedero
    ('Betabel',         6, TRUE),    -- Tubérculos - perecedero
    ('Espinaca',        1, TRUE),    -- Verduras - perecedero
    ('Calabacita',      1, TRUE),    -- Verduras - perecedero
    ('Perejil',         5, TRUE),    -- Hierbas - perecedero
    ('Camote',          6, TRUE),    -- Tubérculos - perecedero
    ('Leche Bronca',    3, TRUE);    -- Lácteos - perecedero


-- ============================================================
-- 6. PUBLICACIÓN SEMANAL
-- ============================================================

INSERT INTO publicacion_semanal (fk_agricultor, fecha_publicacion, semana, estado) VALUES
    (1, '2026-06-01', 23, 'cerrado'),     -- Juan Pérez, semana 23
    (1, '2026-06-08', 24, 'publicado'),   -- Juan Pérez, semana 24
    (2, '2026-06-01', 23, 'cerrado'),     -- María López, semana 23
    (2, '2026-06-08', 24, 'publicado'),   -- María López, semana 24
    (3, '2026-06-01', 23, 'cerrado'),     -- Pedro González, semana 23
    (3, '2026-06-08', 24, 'publicado'),   -- Pedro González, semana 24
    (6, '2026-06-08', 24, 'publicado'),   -- Rosa Martínez, semana 24
    (7, '2026-06-08', 24, 'publicado'),   -- Carlos Hernández, semana 24
    (9, '2026-06-08', 24, 'publicado');   -- Luis Flores, semana 24

INSERT INTO producto_semanal (fk_publicacion, fk_producto, fk_unidad, stock, precio, foto) VALUES
    -- Juan Pérez - Semana 24
    (2,  1,  1, 50, 25.00, NULL),   -- Tomate      - kg        - $25
    (2,  2,  1, 40, 18.00, NULL),   -- Cebolla     - kg        - $18
    (2,  4,  1, 30, 22.00, NULL),   -- Zanahoria   - kg        - $22
    (2,  6,  1, 15, 35.00, NULL),   -- Chile       - kg        - $35
    (2,  7,  3, 25, 10.00, NULL),   -- Cilantro    - manojo    - $10
    -- María López - Semana 24
    (4,  3,  2, 30, 15.00, NULL),   -- Lechuga     - pieza     - $15
    (4,  16, 3, 20, 12.00, NULL),   -- Espinaca    - manojo    - $12
    (4,  17, 1, 25, 14.00, NULL),   -- Calabacita  - kg        - $14
    -- Pedro González - Semana 24
    (6,  8,  2, 20, 35.00, NULL),   -- Aguacate    - pieza     - $35
    (6,  9,  1, 30, 28.00, NULL),   -- Manzana     - kg        - $28
    (6,  10, 5, 25, 22.00, NULL),   -- Naranja     - docena    - $22
    (6,  11, 1, 15, 30.00, NULL),   -- Frijol      - kg        - $30
    -- Rosa Martínez - Semana 24
    (7,  5,  1, 35, 16.00, NULL),   -- Papa        - kg        - $16
    (7,  15, 1, 20, 20.00, NULL),   -- Betabel     - kg        - $20
    (7,  18, 3, 15, 8.00, NULL),    -- Perejil     - manojo    - $8
    -- Carlos Hernández - Semana 24
    (8,  12, 1, 20, 28.00, NULL),   -- Lenteja     - kg        - $28
    (8,  19, 1, 18, 18.00, NULL),   -- Camote      - kg        - $18
    -- Luis Flores - Semana 24
    (9,  13, 1, 10, 60.00, NULL),   -- Queso       - kg        - $60
    (9,  14, 4,  8, 35.00, NULL),   -- Crema       - litro     - $35
    (9,  20, 4, 12, 18.00, NULL);   -- Leche       - litro     - $18


-- ============================================================
-- 7. PEDIDOS (con fk_vendedor y fecha_expiracion)
-- ============================================================

INSERT INTO pedido_cabecera (fk_cliente, fk_estado, subtotal, iva, fk_vendedor, fecha_expiracion) VALUES
    (4,  5, 103.00, 16.48, 12, '2026-06-05 18:00:00'),   -- Ana       - ENTREGADO
    (5,  4, 78.00,  12.48, 12, '2026-06-06 18:00:00'),   -- José      - LISTO PARA RETIRAR
    (8,  2, 155.00, 24.80, 12, '2026-06-06 18:00:00'),   -- Sofía     - CONFIRMADO
    (10, 1, 45.00,  7.20,  NULL, '2026-06-07 18:00:00'), -- Martha    - PENDIENTE (sin vendedor asignado)
    (4,  1, 120.00, 19.20, 12, '2026-06-08 18:00:00'),   -- Ana       - PENDIENTE
    (5,  3, 88.00,  14.08, 12, '2026-06-06 18:00:00'),   -- José      - EN PREPARACIÓN
    (8,  5, 210.00, 33.60, 12, '2026-06-04 18:00:00'),   -- Sofía     - ENTREGADO
    (10, 6, 65.00,  10.40, NULL, '2026-06-05 18:00:00'), -- Martha    - CANCELADO
    (4,  2, 95.00,  15.20, 12, '2026-06-09 18:00:00'),   -- Ana       - CONFIRMADO
    (8,  1, 180.00, 28.80, NULL, '2026-06-10 18:00:00'); -- Sofía     - PENDIENTE (sin vendedor asignado)

INSERT INTO detalle_pedido (fk_pedido, fk_producto_semanal, nombre_producto, precio_unitario, cantidad) VALUES
    -- Pedido 1 - Ana (ENTREGADO)
    (1,  1,  'Tomate Saladet',   25.00, 2),   -- 2kg tomate     = $50
    (1,  2,  'Cebolla Blanca',   18.00, 1),   -- 1kg cebolla    = $18
    (1,  5,  'Cilantro',         10.00, 3),   -- 3 manojos      = $30
    (1,  8,  'Calabacita',       14.00, 1),   -- 1kg calabacita = $14
    -- Pedido 2 - José (LISTO PARA RETIRAR)
    (2,  3,  'Zanahoria',        22.00, 2),   -- 2kg zanahoria  = $44
    (2,  16, 'Papa',             16.00, 2),   -- 2kg papa       = $32
    (2,  5,  'Cilantro',         10.00, 1),   -- 1 manojo       = $10
    -- Pedido 3 - Sofía (CONFIRMADO)
    (3,  6,  'Lechuga Romana',   15.00, 3),   -- 3 piezas       = $45
    (3,  9,  'Aguacate',         35.00, 2),   -- 2 piezas       = $70
    (3,  10, 'Manzana',          28.00, 1),   -- 1kg            = $28
    (3,  7,  'Espinaca',         12.00, 2),   -- 2 manojos      = $24
    -- Pedido 4 - Martha (PENDIENTE)
    (4,  12, 'Frijol Negro',     30.00, 1),   -- 1kg            = $30
    (4,  11, 'Naranja',          22.00, 1),   -- 1 docena       = $22
    -- Pedido 5 - Ana (PENDIENTE)
    (5,  13, 'Queso Fresco',     60.00, 1),   -- 1kg            = $60
    (5,  14, 'Crema',            35.00, 2),   -- 2 litros       = $70
    -- Pedido 6 - José (EN PREPARACIÓN)
    (6,  15, 'Betabel',          20.00, 2),   -- 2kg            = $40
    (6,  17, 'Camote',           18.00, 2),   -- 2kg            = $36
    (6,  4,  'Chile Serrano',    35.00, 1),   -- 1kg            = $35
    -- Pedido 7 - Sofía (ENTREGADO)
    (7,  1,  'Tomate Saladet',   25.00, 3),   -- 3kg            = $75
    (7,  9,  'Aguacate',         35.00, 3),   -- 3 piezas       = $105
    (7,  10, 'Manzana',          28.00, 2),   -- 2kg            = $56
    -- Pedido 8 - Martha (CANCELADO)
    (8,  16, 'Papa',             16.00, 3),   -- 3kg            = $48
    (8,  18, 'Perejil',          8.00,  2),   -- 2 manojos      = $16
    -- Pedido 9 - Ana (CONFIRMADO)
    (9,  2,  'Cebolla Blanca',   18.00, 2),   -- 2kg            = $36
    (9,  6,  'Lechuga Romana',   15.00, 3),   -- 3 piezas       = $45
    (9,  8,  'Calabacita',       14.00, 1),   -- 1kg            = $14
    -- Pedido 10 - Sofía (PENDIENTE)
    (10, 3,  'Zanahoria',        22.00, 3),   -- 3kg            = $66
    (10, 12, 'Frijol Negro',     30.00, 3),   -- 3kg            = $90
    (10, 7,  'Espinaca',         12.00, 2);   -- 2 manojos      = $24


-- ============================================================
-- 8. PAGOS Y CORTES
-- ============================================================

INSERT INTO pago (fk_pedido, fk_tipo, monto, referencia) VALUES
    (1, 1, 120.00, NULL),               -- Pedido 1: Efectivo
    (2, 2, 90.00,  'TRF-20260601-001'), -- Pedido 2: Transferencia
    (7, 1, 244.00, NULL),               -- Pedido 7: Efectivo
    (3, 1, 180.00, NULL);               -- Pedido 3: Efectivo (parcial)

INSERT INTO corte (monto_real, monto_teorico, estado, creado_en) VALUES
    (3560.00, 3520.00, 'cuadrado', '2026-06-01 18:00:00'),
    (2840.00, 2890.00, 'cerrado',  '2026-06-02 18:00:00'),
    (4120.00, 4120.00, 'cuadrado', '2026-06-08 18:00:00');


-- ============================================================
-- 9. HISTORIAL DE ESTADO DE PEDIDO (Consulta #34, #35)
-- ============================================================

INSERT INTO historial_estado_pedido (fk_pedido, fk_estado_anterior, fk_estado_nuevo, fk_cambiado_por, creado_en) VALUES
    -- Pedido 1: pendiente → confirmado → en_preparacion → listo → entregado
    (1, NULL, 1, 4,  '2026-06-01 09:30:00'),  -- Cliente crea
    (1, 1,    2, 12, '2026-06-01 10:00:00'),  -- Vendedor confirma
    (1, 2,    3, 12, '2026-06-01 11:00:00'),  -- Vendedor prepara
    (1, 3,    4, 12, '2026-06-01 16:00:00'),  -- Vendedor listo
    (1, 4,    5, 12, '2026-06-02 10:00:00'),  -- Vendedor entrega
    -- Pedido 2: pendiente → confirmado → en_preparacion → listo
    (2, NULL, 1, 5,  '2026-06-01 10:30:00'),
    (2, 1,    2, 12, '2026-06-01 11:00:00'),
    (2, 2,    3, 12, '2026-06-01 14:00:00'),
    (2, 3,    4, 12, '2026-06-03 12:00:00'),
    -- Pedido 3: pendiente → confirmado
    (3, NULL, 1, 8,  '2026-06-02 11:30:00'),
    (3, 1,    2, 12, '2026-06-02 14:00:00'),
    -- Pedido 6: pendiente → confirmado → en_preparacion
    (6, NULL, 1, 5,  '2026-06-02 12:00:00'),
    (6, 1,    2, 12, '2026-06-02 13:00:00'),
    (6, 2,    3, 12, '2026-06-03 09:00:00'),
    -- Pedido 7: pendiente → confirmado → en_preparacion → listo → entregado
    (7, NULL, 1, 8,  '2026-06-01 15:00:00'),
    (7, 1,    2, 12, '2026-06-01 16:00:00'),
    (7, 2,    3, 12, '2026-06-02 09:00:00'),
    (7, 3,    4, 12, '2026-06-02 14:00:00'),
    (7, 4,    5, 12, '2026-06-03 11:00:00'),
    -- Pedido 8: pendiente → cancelado
    (8, NULL, 1, 10, '2026-06-02 10:00:00'),
    (8, 1,    6, 10, '2026-06-02 16:00:00'),
    -- Pedido 9: pendiente → confirmado
    (9, NULL, 1, 4,  '2026-06-03 09:00:00'),
    (9, 1,    2, 12, '2026-06-03 11:00:00');


-- ============================================================
-- 10. MERMAS
-- ============================================================

INSERT INTO merma (fk_producto_semanal, cantidad, motivo, comentarios, fk_decision) VALUES
    (16, 2, 'Se magullaron durante el transporte', 'Las papas llegaron golpeadas',           2),  -- Desechar
    (6,  3, 'Se marchitaron',                      'Las lechugas no se vendieron en 3 días', 1),  -- Donar
    (1,  5, 'Se echaron a perder',                 'Los tomates maduraron muy rápido',       2),  -- Desechar
    (5,  4, 'No se vendieron',                     'Sobraron manojos del fin de semana',     3);  -- Vender más barato


-- ============================================================
-- 11. LOGS
-- ============================================================

INSERT INTO logs (fk_usuario, descripcion, ip, dispositivo) VALUES
    (11, 'Inició sesión',                          '192.168.1.100', 'Chrome 120 / Windows 10'),
    (1,  'Creó publicación semanal #2',            '192.168.1.101', 'Chrome 120 / Android 14'),
    (4,  'Hizo pedido #1',                         '192.168.1.102', 'Safari 17 / iOS 18'),
    (2,  'Publicó productos (semana 24)',          '192.168.1.103', 'Firefox 125 / Windows 11'),
    (12, 'Cambió estado pedido #2 a listo',        '192.168.1.100', 'Chrome 120 / Windows 10'),
    (3,  'Inició sesión',                          '192.168.1.104', 'Chrome 120 / Android 13'),
    (8,  'Hizo pedido #3',                         '192.168.1.105', 'Safari 17 / iOS 18'),
    (11, 'Creó usuario #12 (vendedor)',            '192.168.1.100', 'Chrome 120 / Windows 10'),
    (5,  'Hizo pedido #6',                         '192.168.1.106', 'Edge 125 / Windows 11'),
    (12, 'Registró merma #1',                      '192.168.1.100', 'Chrome 120 / Windows 10'),
    (11, 'Cerró corte de caja #1',                 '192.168.1.100', 'Chrome 120 / Windows 10'),
    (4,  'Hizo pedido #5',                         '192.168.1.102', 'Safari 17 / iOS 18');


-- ============================================================
-- 12. CHAT: CONVERSACIONES, INTEGRANTES, MENSAJES Y DOCUMENTOS
-- Modelo actualizado: conversacion (privada/grupal) + integrantes
-- ============================================================

-- Conversaciones 1-6: privadas (tipo = FALSE)
-- Conversaciones 7-9: grupales (tipo = TRUE), equivalentes a los
-- antiguos "grupo" por familia
INSERT INTO conversacion (nombre, tipo) VALUES
    (NULL,               FALSE),  -- 1: Ana Ramírez ↔ Juan Pérez
    (NULL,               FALSE),  -- 2: José Sánchez ↔ María López
    (NULL,               FALSE),  -- 3: Sofía Torres ↔ Pedro González
    (NULL,               FALSE),  -- 4: Martha Díaz ↔ Rosa Martínez
    (NULL,               FALSE),  -- 5: Ana Ramírez ↔ Carlos Hernández
    (NULL,               FALSE),  -- 6: Admin ↔ Juan Pérez
    ('Familia Pérez',    TRUE),   -- 7: Grupo familiar (Juan, María)
    ('Familia González', TRUE),   -- 8: Grupo familiar (Pedro, Rosa)
    ('Familia Hernández',TRUE);   -- 9: Grupo familiar (Carlos, Luis)

INSERT INTO integrantes (fk_usuario, fk_conversacion) VALUES
    (4,  1), (1, 1),   -- Ana ↔ Juan
    (5,  2), (2, 2),   -- José ↔ María
    (8,  3), (3, 3),   -- Sofía ↔ Pedro
    (10, 4), (6, 4),   -- Martha ↔ Rosa
    (4,  5), (7, 5),   -- Ana ↔ Carlos
    (11, 6), (1, 6),   -- Admin ↔ Juan
    (1,  7), (2, 7),   -- Familia Pérez: Juan, María
    (3,  8), (6, 8),   -- Familia González: Pedro, Rosa
    (7,  9), (9, 9);   -- Familia Hernández: Carlos, Luis

INSERT INTO mensaje (fk_emisor, fk_conversacion, contenido, leido, creado_en) VALUES
    -- Conversación 1: Ana ↔ Juan
    (4, 1, 'Buenos días, ¿todavía tiene tomate?', TRUE,  '2026-06-01 09:00:00'),
    (1, 1, 'Sí, tengo 50kg disponibles',           TRUE,  '2026-06-01 09:15:00'),
    (4, 1, 'Perfecto, voy a pedir 2kg',            TRUE,  '2026-06-01 09:20:00'),
    (1, 1, 'Claro, cuando guste',                  FALSE, '2026-06-01 09:25:00'),
    -- Conversación 2: José ↔ María
    (5, 2, '¿Las espinacas son orgánicas?',        TRUE,  '2026-06-02 10:00:00'),
    (2, 2, 'Sí, todo es orgánico, sin químicos',   TRUE,  '2026-06-02 10:30:00'),
    (5, 2, 'Perfecto, gracias',                     FALSE, '2026-06-02 10:35:00'),
    -- Conversación 3: Sofía ↔ Pedro
    (8, 3, '¿Los aguacates ya están suaves?',      TRUE,  '2026-06-03 11:00:00'),
    (3, 3, 'Acabo de cortarlos, están en el punto', TRUE,  '2026-06-03 11:10:00'),
    (8, 3, 'Perfecto, pido 3',                      FALSE, '2026-06-03 11:15:00'),
    -- Conversación 7: Grupo Familia Pérez
    (1, 7, 'Compas, mañana llevo el tomate y la cebolla', TRUE,  '2026-06-07 18:00:00'),
    (2, 7, 'Yo llevo la lechuga y espinaca',             TRUE,  '2026-06-07 18:05:00'),
    (1, 7, 'Súper, nos vemos en la uni a las 7am',      FALSE, '2026-06-07 18:10:00'),
    -- Conversación 6: Admin ↔ Juan Pérez
    (11, 6, 'Don Juan, mañana paso por sus productos a las 8am', TRUE,  '2026-06-07 16:00:00'),
    (1,  6, 'Está bien, lo espero',                             TRUE,  '2026-06-07 16:30:00');

-- Documentos (imágenes/audio/video) compartidos en el chat
INSERT INTO documento (fk_usuario, nombre_documento, url_documento, tipo_documento) VALUES
    (1, 'tomate_disponible.jpg',   'https://storage.rassa.com/chat/tomate_disponible.jpg',   'imagen'),
    (2, 'espinaca_organica.jpg',   'https://storage.rassa.com/chat/espinaca_organica.jpg',   'imagen'),
    (11,'nota_recoleccion.mp3',    'https://storage.rassa.com/chat/nota_recoleccion.mp3',    'audio');

-- Relación mensaje ↔ documento adjunto
INSERT INTO mensajes_documentos (fk_mensaje, fk_documento) VALUES
    (2, 1),   -- "Sí, tengo 50kg disponibles" + foto del tomate
    (6, 2),   -- "Sí, todo es orgánico..." + foto de la espinaca
    (14,3);   -- "Don Juan, mañana paso..." + nota de audio


-- ============================================================
-- 13. IMÁGENES DE PRODUCTO (Consultas #9, #10)
-- ============================================================

INSERT INTO producto_imagen (fk_producto, url, es_principal) VALUES
    (1,  'https://storage.rassa.com/productos/tomate_01.jpg', TRUE),
    (1,  'https://storage.rassa.com/productos/tomate_02.jpg', FALSE),
    (8,  'https://storage.rassa.com/productos/aguacate_01.jpg', TRUE),
    (13, 'https://storage.rassa.com/productos/queso_01.jpg', TRUE);


-- ============================================================
-- 14. RECOLECCIÓN (Consultas #31, #33)
-- ============================================================

INSERT INTO recoleccion (fk_agricultor, fecha_recoleccion, hora_inicio, hora_fin, estado, comentarios) VALUES
    (1, '2026-06-07', '07:00', '09:00', 'recolectado', 'Tomate, cebolla, zanahoria listos'),
    (1, '2026-06-14', '07:00', NULL,     'pendiente',  'Programada para la próxima semana'),
    (3, '2026-06-07', '08:00', '10:30', 'recolectado', 'Aguacate, manzana y naranja'),
    (7, '2026-06-07', '09:00', '10:00', 'recolectado', 'Lenteja y camote'),
    (9, '2026-06-07', '10:30', '11:30', 'recolectado', 'Queso, crema y leche'),
    (2, '2026-06-14', '07:30', NULL,     'pendiente',  'Pendiente de recolectar');


-- ============================================================
-- 15. RECIBOS (Consultas #38, #39, #40)
-- ============================================================

INSERT INTO recibo (fk_pago, fk_pedido, folio, monto, creado_en) VALUES
    (1, 1, 'REC-20260601-001', 120.00, '2026-06-01 12:00:00'),
    (2, 2, 'REC-20260601-002', 90.00,  '2026-06-01 15:00:00'),
    (3, 7, 'REC-20260603-001', 244.00, '2026-06-03 14:00:00'),
    (4, 3, 'REC-20260602-001', 180.00, '2026-06-02 16:00:00');


-- ============================================================
-- 16. LIQUIDACIONES (Consultas #41, #42, #43, #44, #45)
-- ============================================================

INSERT INTO liquidacion (fk_agricultor, periodo_inicio, periodo_fin, monto_ventas, comision, fk_pago_liquidacion, estado) VALUES
    (1, '2026-06-01', '2026-06-07', 1250.00, 125.00, 1, 'pagada'),
    (3, '2026-06-01', '2026-06-07', 980.00,  98.00,  NULL, 'pendiente'),
    (6, '2026-06-01', '2026-06-07', 540.00,  54.00,  NULL, 'pendiente'),
    (7, '2026-06-01', '2026-06-07', 420.00,  42.00,  NULL, 'pendiente'),
    (9, '2026-06-01', '2026-06-07', 680.00,  68.00,  1, 'pagada');

COMMIT;
