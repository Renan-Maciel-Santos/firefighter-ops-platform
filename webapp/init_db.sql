-- Executar conectado ao banco 11gb como superusuário

CREATE SCHEMA IF NOT EXISTS app;

CREATE TYPE app.perfil_enum AS ENUM ('comando', 'administrativo', 'operacional');

CREATE TABLE IF NOT EXISTS app.usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    matricula   VARCHAR(20)  NOT NULL UNIQUE,
    senha_hash  VARCHAR(255) NOT NULL,
    perfil      app.perfil_enum NOT NULL,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE
);

-- Usuário inicial: matrícula=000001, perfil 'comando' (acesso total).
-- ATENÇÃO: o hash abaixo é de uma senha fraca conhecida, usada só para o primeiro
-- acesso. TROQUE A SENHA logo após criar o usuário — enquanto ela valer, qualquer
-- pessoa com acesso a este arquivo entra como comando.
-- Para gerar outro hash:
--   python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('SUA_SENHA'))"
INSERT INTO app.usuarios (nome, matricula, senha_hash, perfil)
VALUES (
    'Administrador',
    '000001',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'comando'
)
ON CONFLICT (matricula) DO NOTHING;
