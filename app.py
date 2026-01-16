import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database.db_manager import DatabaseManager
from scrapers.comprasnet_scraper import ComprasnetScraper
from scrapers.portal_compras_scraper import PortalComprasScraper
from scrapers.licitacoes_scraper import LicitacoesScraper
from scrapers.itens_licitacao_scraper import ItensLicitacaoScraper
from scrapers.contratos_scraper import ContratosScraper
from scrapers.fornecedores_scraper import FornecedoresScraper
import io

# Configuração da página
st.set_page_config(
    page_title="Robô de Licitações Brasil",
    page_icon="🤖",
    layout="wide"
)

# Inicializar database manager
@st.cache_resource
def get_db_manager():
    return DatabaseManager()

db = get_db_manager()

# Título
st.title("🤖 Robô de Varredura de Licitações - Brasil")
st.markdown("---")

# Sidebar para configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Seleção de portais
    st.subheader("Escolha os portais de compras")
    
    portais = {
        "Comprasnet": st.checkbox("Comprasnet", value=True),
        "Portal de Compras Públicas": st.checkbox("Portal de Compras Públicas"),
        "Licitações-e": st.checkbox("Licitações-e"),
        "Licitações Caixa": st.checkbox("Licitações Caixa"),
        "Petrobras": st.checkbox("Petrobras"),
        "Compras Amazonas": st.checkbox("COMPRAS AMAZONAS"),
        "Comprasnet Goiás": st.checkbox("COMPRASNET GOIÁS"),
        "Compras RJ": st.checkbox("COMPRAS RJ"),
        "Compras Recife": st.checkbox("COMPRAS RECIFE"),
        "Licitanet": st.checkbox("Licitanet"),
        "BLL Compras": st.checkbox("BLL COMPRAS"),
        "Portal e-LIC Santa Catarina": st.checkbox("PORTAL e-LIC - SANTA CATARINA"),
        "Procergs": st.checkbox("PROCERGS"),
        "Compras Minas Gerais": st.checkbox("COMPRAS MINAS GERAIS"),
        "Banpará": st.checkbox("BANPARÁ"),
        "PE Integrado": st.checkbox("PE Integrado"),
        "BNC": st.checkbox("BNC"),
        "PNCP": st.checkbox("Outros / PNCP"),
    }
    
    st.markdown("---")
    
    # Filtros de busca
    st.subheader("🔍 Filtros de Busca")
    palavra_chave = st.text_input("Palavra-chave", placeholder="Ex: construção, equipamentos...")
    
    data_inicial = st.date_input("Data inicial", datetime.now() - timedelta(days=30))
    data_final = st.date_input("Data final", datetime.now())
    somente_abertas = st.checkbox("Somente licitações em aberto (quando suportado)", value=False)
    
    st.markdown("---")
    
    # Dados complementares
    st.subheader("📎 Dados Complementares")
    incluir_itens = st.checkbox("Incluir Itens de Licitação (CKAN)", value=False)
    incluir_contratos = st.checkbox("Incluir Contratos (CKAN)", value=False)
    incluir_fornecedores = st.checkbox("Incluir Fornecedores (CKAN)", value=False)
    
    st.markdown("---")
    
    # Botão de iniciar varredura
    iniciar_varredura = st.button("🚀 Iniciar Varredura", type="primary", use_container_width=True)

# Main content
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total de Licitações", db.count_licitacoes())
    
with col2:
    st.metric("Portais Selecionados", sum(portais.values()))
    
with col3:
    st.metric("Última Atualização", datetime.now().strftime("%d/%m/%Y %H:%M"))

st.markdown("---")

# Executar varredura
if iniciar_varredura:
    portais_selecionados = [nome for nome, selecionado in portais.items() if selecionado]
    
    if not portais_selecionados:
        st.warning("⚠️ Selecione pelo menos um portal para realizar a varredura.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_portais = len(portais_selecionados)
        licitacoes_encontradas = []
        
        for idx, portal in enumerate(portais_selecionados):
            status_text.text(f"🔄 Varrendo {portal}...")
            
            try:
                # Aqui você chamaria o scraper específico de cada portal
                if portal == "Comprasnet":
                    scraper = ComprasnetScraper()
                    resultados = scraper.buscar(palavra_chave, data_inicial, data_final, somente_abertas=somente_abertas)
                elif portal == "Portal de Compras Públicas":
                    scraper = PortalComprasScraper()
                    resultados = scraper.buscar(palavra_chave, data_inicial, data_final)
                elif portal == "Licitações-e":
                    scraper = LicitacoesScraper()
                    resultados = scraper.buscar(palavra_chave, data_inicial, data_final)
                else:
                    # Placeholder para outros portais
                    resultados = []
                    st.info(f"ℹ️ Scraper para {portal} em desenvolvimento")
                
                # Salvar no banco de dados
                for licitacao in resultados:
                    db.insert_licitacao(licitacao)
                    licitacoes_encontradas.append(licitacao)
                
            except Exception as e:
                st.error(f"❌ Erro ao varrer {portal}: {str(e)}")
            
            progress_bar.progress((idx + 1) / total_portais)
        
        # Enriquecimento CKAN (opcional)
        if incluir_itens:
            try:
                status_text.text("📦 Buscando Itens de Licitação (CKAN)...")
                itens_scraper = ItensLicitacaoScraper()
                itens = itens_scraper.buscar(palavra_chave, data_inicial, data_final)
                inseridos = 0
                for it in itens:
                    if db.insert_item_licitacao(it):
                        inseridos += 1
                st.success(f"✅ Itens inseridos/atualizados: {inseridos}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar itens CKAN: {str(e)}")
        
        if incluir_contratos:
            try:
                status_text.text("📄 Buscando Contratos (CKAN)...")
                contratos_scraper = ContratosScraper()
                contratos = contratos_scraper.buscar(palavra_chave, data_inicial, data_final)
                inseridos = 0
                fornecedores_upserts = 0
                for ct in contratos:
                    if db.insert_contrato(ct):
                        inseridos += 1
                    # Tentar enriquecer fornecedor por CNPJ básico (se posteriormente houver toggle de fornecedores)
                    # Mantemos aqui somente inserção de contratos; fornecedores será buscado abaixo caso selecionado
                st.success(f"✅ Contratos inseridos/atualizados: {inseridos}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar contratos CKAN: {str(e)}")
        
        if incluir_fornecedores:
            try:
                status_text.text("🏢 Buscando Fornecedores (CKAN)...")
                forn_scraper = FornecedoresScraper()
                fornecedores = forn_scraper.buscar(palavra_chave, data_inicial, data_final)
                upserts = 0
                for fz in fornecedores:
                    if db.upsert_fornecedor(fz):
                        upserts += 1
                st.success(f"✅ Fornecedores inseridos/atualizados: {upserts}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar fornecedores CKAN: {str(e)}")
        
        status_text.text("✅ Varredura concluída!")
        st.success(f"🎉 Foram encontradas {len(licitacoes_encontradas)} licitações!")
        
        # Recarregar a página para atualizar as métricas
        st.rerun()

# Exibir resultados
st.subheader("📊 Resultados da Varredura")

# Filtros para visualização
col_filtro1, col_filtro2 = st.columns(2)

with col_filtro1:
    filtro_portal = st.multiselect(
        "Filtrar por portal",
        options=list(portais.keys()),
        default=[]
    )

with col_filtro2:
    filtro_status = st.multiselect(
        "Filtrar por status",
        options=["Aberta", "Em andamento", "Fechada"],
        default=[]
    )

# Buscar licitações do banco
licitacoes_df = db.get_licitacoes(
    portais=filtro_portal if filtro_portal else None,
    status=filtro_status if filtro_status else None,
    palavra_chave=palavra_chave if palavra_chave else None
)

if not licitacoes_df.empty:
    st.dataframe(licitacoes_df, use_container_width=True, height=400)
    
    # Botões de download
    st.subheader("💾 Download dos Dados")
    
    col_download1, col_download2, col_download3 = st.columns(3)
    
    with col_download1:
        # Download CSV
        csv = licitacoes_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"licitacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col_download2:
        # Download Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            licitacoes_df.to_excel(writer, index=False, sheet_name='Licitações')
        
        st.download_button(
            label="📥 Download Excel",
            data=buffer.getvalue(),
            file_name=f"licitacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    with col_download3:
        # Download JSON
        json_str = licitacoes_df.to_json(orient='records', force_ascii=False)
        st.download_button(
            label="📥 Download JSON",
            data=json_str,
            file_name=f"licitacoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )
else:
    st.info("ℹ️ Nenhuma licitação encontrada. Inicie uma varredura para buscar dados.")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center'>Desenvolvido com ❤️ para facilitar o acesso às licitações públicas brasileiras</div>",
    unsafe_allow_html=True
)
