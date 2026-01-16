-- Script para criar o banco de dados de licitações
-- Execute este script no PostgreSQL antes de rodar a aplicação

-- Criar banco de dados
CREATE DATABASE licitacoes_db;

-- Conectar ao banco
\c licitacoes_db;

-- Criar tabela de licitações
CREATE TABLE IF NOT EXISTS licitacoes (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(100) NOT NULL,
    titulo VARCHAR(500) NOT NULL,
    orgao VARCHAR(300),
    portal VARCHAR(100) NOT NULL,
    modalidade VARCHAR(100),
    data_publicacao TIMESTAMP,
    data_abertura TIMESTAMP,
    valor_estimado DECIMAL(15, 2),
    status VARCHAR(50),
    descricao TEXT,
    link_edital VARCHAR(500),
    palavra_chave VARCHAR(200),
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_licitacao UNIQUE (numero, portal)
);

-- Criar índices para melhor performance
CREATE INDEX idx_portal ON licitacoes(portal);
CREATE INDEX idx_status ON licitacoes(status);
CREATE INDEX idx_data_publicacao ON licitacoes(data_publicacao);
CREATE INDEX idx_palavra_chave ON licitacoes(palavra_chave);
CREATE INDEX idx_titulo ON licitacoes USING gin(to_tsvector('portuguese', titulo));
CREATE INDEX idx_descricao ON licitacoes USING gin(to_tsvector('portuguese', descricao));

-- Criar tabela de histórico de varreduras
CREATE TABLE IF NOT EXISTS historico_varreduras (
    id SERIAL PRIMARY KEY,
    portal VARCHAR(100) NOT NULL,
    data_varredura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_encontrado INTEGER,
    palavra_chave VARCHAR(200),
    sucesso BOOLEAN DEFAULT TRUE,
    mensagem_erro TEXT
);

-- Criar tabela de configurações
CREATE TABLE IF NOT EXISTS configuracoes (
    id SERIAL PRIMARY KEY,
    chave VARCHAR(100) UNIQUE NOT NULL,
    valor TEXT,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir configurações padrão
INSERT INTO configuracoes (chave, valor) VALUES 
    ('ultima_varredura', CURRENT_TIMESTAMP::TEXT),
    ('total_portais', '18')
ON CONFLICT (chave) DO NOTHING;

-- Comentários nas tabelas
COMMENT ON TABLE licitacoes IS 'Tabela principal com dados das licitações coletadas';
COMMENT ON TABLE historico_varreduras IS 'Registro de todas as varreduras realizadas';
COMMENT ON TABLE configuracoes IS 'Configurações gerais do sistema';

-- ================================
-- Novas tabelas: itens, contratos, fornecedores
-- ================================

-- Itens de Licitação
CREATE TABLE IF NOT EXISTS itens_licitacao (
    id SERIAL PRIMARY KEY,
    id_licitacao VARCHAR(100) NOT NULL,
    numero_item VARCHAR(50),
    descricao TEXT,
    unidade VARCHAR(100),
    quantidade DECIMAL(18,4),
    valor_unitario DECIMAL(15,2),
    valor_total DECIMAL(15,2),
    data_publicacao TIMESTAMP,
    portal VARCHAR(100) DEFAULT 'Comprasnet',
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_item_por_licitacao UNIQUE (id_licitacao, numero_item, portal)
);
CREATE INDEX IF NOT EXISTS idx_itens_licitacao_id ON itens_licitacao(id_licitacao);
CREATE INDEX IF NOT EXISTS idx_itens_licitacao_data ON itens_licitacao(data_publicacao);

-- Contratos
CREATE TABLE IF NOT EXISTS contratos (
    id SERIAL PRIMARY KEY,
    id_licitacao VARCHAR(100),
    numero_contrato VARCHAR(100) NOT NULL,
    orgao VARCHAR(300),
    cnpj VARCHAR(20),
    fornecedor VARCHAR(300),
    objeto TEXT,
    valor_inicial DECIMAL(15,2),
    valor_final DECIMAL(15,2),
    data_assinatura TIMESTAMP,
    vigencia_inicio TIMESTAMP,
    vigencia_fim TIMESTAMP,
    portal VARCHAR(100) DEFAULT 'Comprasnet',
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_contrato UNIQUE (numero_contrato, portal)
);
CREATE INDEX IF NOT EXISTS idx_contratos_id_licitacao ON contratos(id_licitacao);
CREATE INDEX IF NOT EXISTS idx_contratos_cnpj ON contratos(cnpj);

-- Fornecedores
CREATE TABLE IF NOT EXISTS fornecedores (
    id SERIAL PRIMARY KEY,
    cnpj VARCHAR(20) UNIQUE NOT NULL,
    razao_social VARCHAR(300),
    tipo VARCHAR(100),
    porte VARCHAR(100),
    uf VARCHAR(2),
    municipio VARCHAR(200),
    atualizado_em TIMESTAMP,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documentos (editais/anexos)
CREATE TABLE IF NOT EXISTS documentos (
    id SERIAL PRIMARY KEY,
    portal VARCHAR(100) NOT NULL,                 -- Ex: 'PNCP 14133'
    numero_controle VARCHAR(100),                 -- PNCP: numeroControlePNCP (quando disponível)
    id_compra VARCHAR(100),                       -- PNCP: idCompra (quando disponível)
    ano_compra INTEGER,                           -- PNCP: anoCompraPncp
    sequencial_compra INTEGER,                    -- PNCP: sequencialCompraPncp
    tipo_documento VARCHAR(200),                  -- Ex: 'INSTRUMENTO_CONVOCATORIO', 'ANEXO', etc.
    nome_arquivo VARCHAR(500),
    url TEXT,                                     -- URL pública de download (quando houver)
    caminho_local TEXT,                           -- Caminho salvo em disco (quando baixado)
    tamanho_bytes BIGINT,
    sha256 VARCHAR(64),
    data_publicacao TIMESTAMP,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_documento_url UNIQUE (url)
);
CREATE INDEX IF NOT EXISTS idx_documentos_portal ON documentos(portal);
CREATE INDEX IF NOT EXISTS idx_documentos_numero ON documentos(numero_controle);
