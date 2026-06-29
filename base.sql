-- ============================================================
-- ESQUEMA LÓGICO BD RASSA - JALA v3.0 DEFINITIVA
-- PostgreSQL
--
-- FUSIÓN: v2.0 (original) + v2.1 (tablas financieras/recolección)
-- + correcciones para cubrir las 50 consultas del profesor
--
-- TABLAS: 31 en total
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
