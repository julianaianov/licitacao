import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

class DatabaseManager:
    def __init__(self):
        """Inicializa a conexão com o banco PostgreSQL local"""
        self.connection_params = {
            'dbname': 'licitacoes_db',
            'user': 'postgres',
            'password': 'postgres',
            'host': 'localhost',
            'port': '5432'
        }
        self._create_connection()
    
    def _create_connection(self):
        """Cria conexão com o banco de dados"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            self.conn.autocommit = True
        except psycopg2.OperationalError as e:
            print(f"⚠️ Erro ao conectar ao banco de dados: {e}")
            print("Certifique-se de que o PostgreSQL está rodando e execute o script SQL de criação.")
            self.conn = None
    
    def insert_licitacao(self, licitacao: Dict):
        """Insere uma nova licitação no banco de dados"""
        if not self.conn:
            return False
        
        try:
            cursor = self.conn.cursor()
            
            query = """
                INSERT INTO licitacoes (
                    numero, titulo, orgao, portal, modalidade, 
                    data_publicacao, data_abertura, valor_estimado, 
                    status, descricao, link_edital, palavra_chave
                ) VALUES (
                    %(numero)s, %(titulo)s, %(orgao)s, %(portal)s, %(modalidade)s,
                    %(data_publicacao)s, %(data_abertura)s, %(valor_estimado)s,
                    %(status)s, %(descricao)s, %(link_edital)s, %(palavra_chave)s
                )
                ON CONFLICT (numero, portal) DO UPDATE SET
                    titulo = EXCLUDED.titulo,
                    status = EXCLUDED.status,
                    data_atualizacao = CURRENT_TIMESTAMP
            """
            
            cursor.execute(query, licitacao)
            cursor.close()
            return True
            
        except Exception as e:
            print(f"Erro ao inserir licitação: {e}")
            return False
    
    def insert_item_licitacao(self, item: Dict) -> bool:
        """Insere item de licitação na tabela itens_licitacao"""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            query = """
                INSERT INTO itens_licitacao (
                    id_licitacao, numero_item, descricao, unidade, quantidade,
                    valor_unitario, valor_total, data_publicacao, portal
                ) VALUES (
                    %(id_licitacao)s, %(numero_item)s, %(descricao)s, %(unidade)s, %(quantidade)s,
                    %(valor_unitario)s, %(valor_total)s, %(data_publicacao)s, %(portal)s
                )
                ON CONFLICT (id_licitacao, numero_item, portal) DO UPDATE SET
                    descricao = EXCLUDED.descricao,
                    quantidade = EXCLUDED.quantidade,
                    valor_unitario = EXCLUDED.valor_unitario,
                    valor_total = EXCLUDED.valor_total,
                    data_atualizacao = CURRENT_TIMESTAMP
            """
            cursor.execute(query, item)
            cursor.close()
            return True
        except Exception as e:
            print(f"Erro ao inserir item de licitação: {e}")
            return False
    
    def insert_contrato(self, contrato: Dict) -> bool:
        """Insere contrato na tabela contratos"""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            query = """
                INSERT INTO contratos (
                    id_licitacao, numero_contrato, orgao, cnpj, fornecedor,
                    objeto, valor_inicial, valor_final, data_assinatura,
                    vigencia_inicio, vigencia_fim, portal
                ) VALUES (
                    %(id_licitacao)s, %(numero_contrato)s, %(orgao)s, %(cnpj)s, %(fornecedor)s,
                    %(objeto)s, %(valor_inicial)s, %(valor_final)s, %(data_assinatura)s,
                    %(vigencia_inicio)s, %(vigencia_fim)s, %(portal)s
                )
                ON CONFLICT (numero_contrato, portal) DO UPDATE SET
                    objeto = EXCLUDED.objeto,
                    valor_final = EXCLUDED.valor_final,
                    data_atualizacao = CURRENT_TIMESTAMP
            """
            cursor.execute(query, contrato)
            cursor.close()
            return True
        except Exception as e:
            print(f"Erro ao inserir contrato: {e}")
            return False
    
    def upsert_fornecedor(self, fornecedor: Dict) -> bool:
        """Insere/atualiza fornecedor pela chave única CNPJ"""
        if not self.conn:
            return False
        try:
            cursor = self.conn.cursor()
            query = """
                INSERT INTO fornecedores (
                    cnpj, razao_social, tipo, porte, uf, municipio, atualizado_em
                ) VALUES (
                    %(cnpj)s, %(razao_social)s, %(tipo)s, %(porte)s, %(uf)s, %(municipio)s, %(atualizado_em)s
                )
                ON CONFLICT (cnpj) DO UPDATE SET
                    razao_social = EXCLUDED.razao_social,
                    tipo = EXCLUDED.tipo,
                    porte = EXCLUDED.porte,
                    uf = EXCLUDED.uf,
                    municipio = EXCLUDED.municipio,
                    atualizado_em = EXCLUDED.atualizado_em,
                    data_atualizacao = CURRENT_TIMESTAMP
            """
            cursor.execute(query, fornecedor)
            cursor.close()
            return True
        except Exception as e:
            print(f"Erro ao inserir/atualizar fornecedor: {e}")
            return False
    
    def get_licitacoes(self, portais: Optional[List[str]] = None, 
                       status: Optional[List[str]] = None,
                       palavra_chave: Optional[str] = None) -> pd.DataFrame:
        """Busca licitações do banco com filtros opcionais"""
        if not self.conn:
            return pd.DataFrame()
        
        try:
            query = "SELECT * FROM licitacoes WHERE 1=1"
            params = []
            
            if portais:
                placeholders = ','.join(['%s'] * len(portais))
                query += f" AND portal IN ({placeholders})"
                params.extend(portais)
            
            if status:
                placeholders = ','.join(['%s'] * len(status))
                query += f" AND status IN ({placeholders})"
                params.extend(status)
            
            if palavra_chave:
                query += " AND (titulo ILIKE %s OR descricao ILIKE %s)"
                params.extend([f"%{palavra_chave}%", f"%{palavra_chave}%"])
            
            query += " ORDER BY data_publicacao DESC LIMIT 1000"
            
            df = pd.read_sql_query(query, self.conn, params=params if params else None)
            return df
            
        except Exception as e:
            print(f"Erro ao buscar licitações: {e}")
            return pd.DataFrame()
    
    def count_licitacoes(self) -> int:
        """Retorna o total de licitações no banco"""
        if not self.conn:
            return 0
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM licitacoes")
            count = cursor.fetchone()[0]
            cursor.close()
            return count
        except:
            return 0
    
    def close(self):
        """Fecha a conexão com o banco"""
        if self.conn:
            self.conn.close()
