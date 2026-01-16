# 🤖 Robô de Varredura de Licitações - Brasil

Sistema automatizado para coleta e análise de licitações públicas de diversos portais brasileiros.

## 📋 Características

- ✅ Varredura em 18+ portais de licitações
- ✅ Banco de dados PostgreSQL local
- ✅ Interface web intuitiva com Streamlit
- ✅ Filtros avançados de busca
- ✅ Download em múltiplos formatos (CSV, Excel, JSON)
- ✅ Sistema de cache e histórico
- ✅ Busca por palavra-chave e período

## 🚀 Instalação

### 1. Pré-requisitos

- Python 3.8+
- PostgreSQL 12+

### 2. Instalar PostgreSQL

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows:**
Baixe e instale do site oficial: https://www.postgresql.org/download/windows/

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

### 3. Configurar o Banco de Dados

```bash
# Acessar PostgreSQL
sudo -u postgres psql

# Criar usuário (se necessário)
CREATE USER postgres WITH PASSWORD 'postgres';
ALTER USER postgres WITH SUPERUSER;

# Sair
\q
```

### 4. Executar o Script SQL

```bash
# Linux/macOS
psql -U postgres -f scripts/create_database.sql

# Windows (no PowerShell ou CMD)
psql -U postgres -f scripts\create_database.sql
```

### 5. Instalar Dependências Python

```bash
pip install -r requirements.txt
```

## 🎯 Como Usar

### 1. Iniciar a Aplicação

```bash
streamlit run app.py
```

A aplicação abrirá automaticamente no navegador em `http://localhost:8501`

### 2. Configurar a Varredura

1. **Selecione os portais** desejados na barra lateral
2. **Digite uma palavra-chave** (opcional)
3. **Defina o período** de busca
4. Clique em **"🚀 Iniciar Varredura"**

### 3. Visualizar e Baixar Resultados

- Os resultados aparecem em uma tabela interativa
- Use os filtros para refinar a visualização
- Clique nos botões de download para exportar:
  - 📥 CSV
  - 📥 Excel
  - 📥 JSON

## 🔧 Configuração do Banco de Dados

Se você usar credenciais diferentes, edite o arquivo `database/db_manager.py`:

```python
self.connection_params = {
    'dbname': 'licitacoes_db',
    'user': 'seu_usuario',      # Altere aqui
    'password': 'sua_senha',     # Altere aqui
    'host': 'localhost',
    'port': '5432'
}
```

## 📊 Portais Suportados

1. Comprasnet (Gov Federal)
2. Portal de Compras Públicas
3. Licitações-e (Banco do Brasil)
4. Licitações Caixa
5. Petrobras
6. Compras Amazonas
7. Comprasnet Goiás
8. Compras RJ
9. Compras Recife
10. Licitanet
11. BLL Compras
12. Portal e-LIC Santa Catarina
13. Procergs
14. Compras Minas Gerais
15. Banpará
16. PE Integrado
17. BNC
18. PNCP (Portal Nacional de Contratações Públicas)

## 🛠️ Desenvolvimento

### Estrutura do Projeto

```
.
├── app.py                          # Aplicação principal Streamlit
├── database/
│   └── db_manager.py              # Gerenciador do banco de dados
├── scrapers/
│   ├── comprasnet_scraper.py      # Scraper Comprasnet
│   ├── portal_compras_scraper.py  # Scraper Portal Compras
│   └── licitacoes_scraper.py      # Scraper Licitações-e
├── scripts/
│   └── create_database.sql        # Script de criação do BD
├── requirements.txt               # Dependências Python
└── README.md                      # Documentação
```

### Adicionar Novos Scrapers

1. Crie um novo arquivo em `scrapers/`
2. Implemente a classe com método `buscar()`
3. Importe e use em `app.py`

Exemplo:

```python
class NovoPortalScraper:
    def buscar(self, palavra_chave, data_inicial, data_final):
        # Sua lógica de scraping aqui
        return licitacoes_encontradas
```

## ⚠️ Notas Importantes

- **Respeite os termos de uso** de cada portal
- **Implemente rate limiting** para não sobrecarregar os servidores
- **Os scrapers são exemplos** - adapte para a estrutura real de cada portal
- **Alguns portais podem exigir autenticação** - adicione credenciais conforme necessário
- **Use proxies se necessário** para evitar bloqueios

## 📝 Licença

Este projeto é fornecido como exemplo educacional. Use com responsabilidade.

## 🤝 Contribuições

Contribuições são bem-vindas! Sinta-se livre para:
- Adicionar novos scrapers
- Melhorar a interface
- Corrigir bugs
- Adicionar funcionalidades

## 📧 Suporte

Para dúvidas ou problemas:
1. Verifique se o PostgreSQL está rodando
2. Confirme as credenciais do banco
3. Execute o script SQL novamente se necessário
4. Verifique os logs de erro no console
