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
from scrapers.pncp_14133_scraper import Pncp14133Scraper
from scrapers.itens_pregoes_id_scraper import ItensPregoesIdScraper
from scrapers.licitacao_id_scraper import LicitacaoIdScraper
from scrapers.pregoes_id_scraper import PregoesIdScraper
from scrapers.modulo_fornecedor_scraper import ModuloFornecedorScraper
from scrapers.pncp_documentos_scraper import PncpDocumentosScraper
from scrapers.pncp_api_scraper import PncpApiScraper
from scrapers.compras_gov_documentos_scraper import ComprasGovDocumentosScraper
from scrapers.comprasnet_edital_downloader import baixar_e_registrar as comprasnet_baixar_edital
from scrapers.pncp_to_comprasnet import extract_trio_from_pncp
from scrapers.pncp_api_arquivos import baixar_todos_por_numero as pncp_api_baixar_todos
import io
import re
import requests
import os
import base64
import streamlit.components.v1 as components

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
# Remover silenciosamente registros fictícios de execuções antigas
try:
    if hasattr(db, "cleanup_demo_data"):
        db.cleanup_demo_data()
except Exception:
    pass

# Título
st.title("🤖 Robô de Varredura de Licitações - Brasil")
st.markdown("---")

# Sidebar para configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Seleção de portais
    st.subheader("Origem dos dados")
    # Mantemos apenas PNCP como origem principal
    portais = {
        "PNCP": st.checkbox("PNCP", value=True),
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
    st.subheader("📦 Itens de Pregões por ID (módulo legado)")
    incluir_itens_legado_id = st.checkbox("Incluir Itens de Pregões por ID (módulo legado)", value=False)
    id_compra_legado = st.text_input("id_compra (obrigatório)", value="")
    id_compra_item_legado = st.text_input("id_compra_item (opcional)", value="")
    dt_alteracao_legado = st.text_input("dt_alteracao (opcional, YYYY-MM-DD ou ISO)", value="")
    st.caption("Dica: preencha apenas id_compra para trazer todos os itens desse pregão.")
    
    st.subheader("📄 Licitação por ID (módulo legado)")
    incluir_licitacao_legado_id = st.checkbox("Incluir Licitação por ID (módulo legado)", value=False)
    id_compra_licitacao = st.text_input("id_compra (licitação)", value="")
    dt_alteracao_licitacao = st.text_input("dt_alteracao (opcional, licitação)", value="")
    
    st.subheader("📣 Pregão por ID (módulo legado)")
    incluir_pregao_legado_id = st.checkbox("Incluir Pregão por ID (módulo legado)", value=False)
    id_compra_pregao = st.text_input("id_compra (pregão)", value="")
    dt_alteracao_pregao = st.text_input("dt_alteracao (opcional, pregão)", value="")
    
    st.subheader("🏢 Fornecedor (módulo fornecedor)")
    incluir_modulo_fornecedor = st.checkbox("Incluir Fornecedor (módulo fornecedor)", value=False)
    fornecedor_ativo = st.checkbox("Fornecedor ativo?", value=True)
    fornecedor_cnpj = st.text_input("CNPJ (opcional)", value="")
    fornecedor_cpf = st.text_input("CPF (opcional)", value="")
    fornecedor_nat_jur = st.text_input("naturezaJuridicaId (opcional)", value="")
    fornecedor_porte = st.text_input("porteEmpresaId (opcional)", value="")
    fornecedor_cnae = st.text_input("codigoCnae (opcional)", value="")
    
    st.subheader("📎 Editais PNCP (PDF)")
    baixar_editais_pncp = st.checkbox("Baixar e salvar editais PNCP (quando disponíveis)", value=False)
    
    st.subheader("📎 Editais Compras.gov (HTML→PDF)")
    baixar_compras_gov = st.checkbox("Baixar e salvar editais do Compras.gov (por aviso/UASG)", value=False)
    compras_gov_aviso = st.text_input("numero_aviso (Compras.gov)", value="")
    compras_gov_uasg = st.text_input("UASG (opcional, Compras.gov)", value="")
    
    st.subheader("📎 Edital Comprasnet (download direto ASP)")
    comprasnet_coduasg = st.text_input("coduasg", value="")
    comprasnet_numprp = st.text_input("numprp", value="")
    comprasnet_modprp = st.text_input("modprp", value="")
    acionar_comprasnet_download = st.button("⬇️ Baixar Edital (Comprasnet ASP)", use_container_width=True)
    
    st.subheader("🔄 PNCP → Comprasnet (auto)")
    pncp_numero_controle = st.text_input("numeroControlePNCP (auto-extrair trio e baixar)", value="")
    acionar_pncp_auto = st.button("🔎 Extrair e baixar (PNCP → Comprasnet)", use_container_width=True)
    
    st.subheader("📎 PNCP API (arquivos por numeroControlePNCP)")
    pncp_api_numero = st.text_input("numeroControlePNCP (PNCP API arquivos)", value="")
    acionar_pncp_api = st.button("⬇️ Baixar todos (PNCP API arquivos)", use_container_width=True)
    
    st.markdown("---")
    
    # Botões de busca
    iniciar_varredura = st.button("🚀 Iniciar Varredura (legado)", use_container_width=True)
    buscar_pncp_btn = st.button("🔎 Buscar Licitações PNCP", use_container_width=True)

# Main content
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total de Licitações", db.count_licitacoes())
    
with col2:
    st.metric("Portais Selecionados", sum(portais.values()))
    
with col3:
    st.metric("Última Atualização", datetime.now().strftime("%d/%m/%Y %H:%M"))

st.markdown("---")

# Executar busca PNCP (consulta por período) - preferencial
if buscar_pncp_btn:
    try:
        st.info("Consultando PNCP (consulta v1) ...")
        base = "https://pncp.gov.br/api/consulta/v1/contratacoes"
        resultados = []
        for pagina in range(1, 6):
            params = {
                "pagina": pagina,
                "tamanhoPagina": 50,
                "dataInicial": data_inicial.strftime("%Y-%m-%d"),
                "dataFinal": data_final.strftime("%Y-%m-%d"),
            }
            r = requests.get(base, params=params, timeout=60, headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
            j = r.json()
            data = j.get("data") if isinstance(j, dict) else []
            if not data:
                break
            resultados.extend(data)
            if len(data) < 50:
                break
        inseridos = 0
        for it in resultados:
            numero = it.get("numeroControlePNCP") or ""
            objeto = it.get("objeto") or it.get("objetoCompra") or ""
            orgao = ""
            if isinstance(it.get("orgaoEntidade"), dict):
                orgao = it["orgaoEntidade"].get("nome", "")
            modalidade = it.get("modalidade") or it.get("modalidadeNome") or ""
            situacao = it.get("situacao") or it.get("situacaoCompraNomePncp") or ""
            lic = {
                "numero": str(numero),
                "titulo": (objeto[:500] if isinstance(objeto, str) else "Licitação PNCP"),
                "orgao": orgao,
                "portal": "PNCP",
                "modalidade": str(modalidade),
                "data_publicacao": datetime.now(),
                "data_abertura": datetime.now(),
                "valor_estimado": 0.0,
                "status": str(situacao) or "Indefinido",
                "descricao": objeto or "",
                "link_edital": it.get("linkExterno") or "",
                "palavra_chave": palavra_chave or "",
            }
            if db.insert_licitacao(lic):
                inseridos += 1
        st.success(f"✅ PNCP: {inseridos} registros inseridos/atualizados.")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao consultar PNCP: {e}")


# Executar varredura (legado)
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
                if portal == "PNCP":
                    scraper = Pncp14133Scraper()
                    resultados = scraper.buscar(palavra_chave, data_inicial, data_final)
                    # Baixar documentos PNCP (best-effort)
                    if baixar_editais_pncp and resultados:
                        try:
                            status_text.text("📎 Baixando editais PNCP (PDF)...")
                            doc_scraper = PncpDocumentosScraper()
                            api_list_scraper = PncpApiScraper()
                            total_docs = 0
                            # 1) Tentar direto a partir dos resultados 14133 (se trouxerem pncp_meta)
                            for lic in resultados:
                                meta = lic.get("pncp_meta") or {}
                                if not meta:
                                    continue
                                docs = doc_scraper.buscar_documentos(meta, base_export_dir="export")
                                for d in docs:
                                    if db.insert_documento(d):
                                        total_docs += 1
                            # 2) Listar também via API oficial PNCP (datas do período) e baixar documentos
                            status_text.text("📎 PNCP API: listando contratações por período para baixar documentos...")
                            api_list = api_list_scraper.buscar(
                                palavra_chave=palavra_chave or "",
                                data_inicial=data_inicial,
                                data_final=data_final,
                                modalidade="",  # sem restringir para maximizar documentos
                                situacao=""     # idem
                            )
                            for lic in api_list:
                                meta = lic.get("pncp_meta") or {}
                                if not meta:
                                    continue
                                docs = doc_scraper.buscar_documentos(meta, base_export_dir="export")
                                for d in docs:
                                    if db.insert_documento(d):
                                        total_docs += 1
                            if total_docs > 0:
                                st.success(f"✅ Documentos PNCP inseridos/atualizados: {total_docs}")
                            else:
                                st.info("ℹ️ Nenhum documento PNCP encontrado para os registros retornados.")
                        except Exception as e:
                            st.error(f"❌ Erro ao baixar documentos PNCP: {str(e)}")
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
        
        # Fornecedor (módulo fornecedor)
        if incluir_modulo_fornecedor and fornecedor_ativo is not None:
            try:
                status_text.text("🏢 Buscando Fornecedores (módulo fornecedor)...")
                mod_forn = ModuloFornecedorScraper()
                def to_int_or_none(s: str):
                    s = (s or "").strip()
                    try:
                        return int(s) if s else None
                    except Exception:
                        return None
                fornecedores_mod = mod_forn.buscar(
                    ativo=bool(fornecedor_ativo),
                    cnpj=fornecedor_cnpj.strip() or None,
                    cpf=fornecedor_cpf.strip() or None,
                    naturezaJuridicaId=to_int_or_none(fornecedor_nat_jur),
                    porteEmpresaId=to_int_or_none(fornecedor_porte),
                    codigoCnae=to_int_or_none(fornecedor_cnae),
                )
                upserts_mod = 0
                for fm in fornecedores_mod:
                    if db.upsert_fornecedor(fm):
                        upserts_mod += 1
                st.success(f"✅ Fornecedores (módulo) inseridos/atualizados: {upserts_mod}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar fornecedores (módulo fornecedor): {str(e)}")
        
        # Itens de Pregões por ID (módulo legado)
        if incluir_itens_legado_id and id_compra_legado.strip():
            try:
                status_text.text("🧩 Buscando Itens de Pregões por ID (módulo legado)...")
                itens_id_scraper = ItensPregoesIdScraper()
                itens_id = itens_id_scraper.buscar(
                    id_compra=id_compra_legado.strip(),
                    id_compra_item=id_compra_item_legado.strip() or None,
                    dt_alteracao=dt_alteracao_legado.strip() or None
                )
                inseridos_legado = 0
                for it in itens_id:
                    if db.insert_item_licitacao(it):
                        inseridos_legado += 1
                st.success(f"✅ Itens (módulo legado por ID) inseridos/atualizados: {inseridos_legado}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar Itens por ID (módulo legado): {str(e)}")
        
        # Licitação por ID (módulo legado)
        if incluir_licitacao_legado_id and id_compra_licitacao.strip():
            try:
                status_text.text("📄 Buscando Licitação por ID (módulo legado)...")
                lic_id_scraper = LicitacaoIdScraper()
                lic_rows = lic_id_scraper.buscar(
                    id_compra=id_compra_licitacao.strip(),
                    palavra_chave=palavra_chave or "",
                    dt_alteracao=dt_alteracao_licitacao.strip() or None
                )
                inseridos_lic = 0
                for lic in lic_rows:
                    if db.insert_licitacao(lic):
                        inseridos_lic += 1
                        licitacoes_encontradas.append(lic)
                st.success(f"✅ Licitações (módulo legado por ID) inseridas/atualizadas: {inseridos_lic}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar Licitação por ID (módulo legado): {str(e)}")
        
        # Pregão por ID (módulo legado)
        if incluir_pregao_legado_id and id_compra_pregao.strip():
            try:
                status_text.text("📣 Buscando Pregão por ID (módulo legado)...")
                prg_id_scraper = PregoesIdScraper()
                prg_rows = prg_id_scraper.buscar(
                    id_compra=id_compra_pregao.strip(),
                    palavra_chave=palavra_chave or "",
                    dt_alteracao=dt_alteracao_pregao.strip() or None
                )
                inseridos_prg = 0
                for prg in prg_rows:
                    if db.insert_licitacao(prg):
                        inseridos_prg += 1
                        licitacoes_encontradas.append(prg)
                st.success(f"✅ Pregões (módulo legado por ID) inseridos/atualizados: {inseridos_prg}")
            except Exception as e:
                st.error(f"❌ Erro ao buscar Pregão por ID (módulo legado): {str(e)}")
        
        status_text.text("✅ Varredura concluída!")
        st.success(f"🎉 Foram encontradas {len(licitacoes_encontradas)} licitações!")
        
        # Recarregar a página para atualizar as métricas
        st.rerun()

# Acionadores independentes (Compras.gov) caso usuário queira apenas baixar por aviso/UASG
if not iniciar_varredura and baixar_compras_gov and compras_gov_aviso.strip():
    st.info("Executando download de edital(s) no Compras.gov...")
    try:
        cg_scraper = ComprasGovDocumentosScraper()
        docs = cg_scraper.buscar_documentos(
            numero_aviso=compras_gov_aviso.strip(),
            uasg=(compras_gov_uasg.strip() or None),
            base_export_dir="export"
        )
        inseridos = 0
        for d in docs:
            if db.insert_documento(d):
                inseridos += 1
        if inseridos > 0:
            st.success(f"✅ Documentos (Compras.gov) inseridos/atualizados: {inseridos}")
        else:
            st.info("ℹ️ Nenhum PDF localizado nas páginas consultadas do Compras.gov para este aviso/UASG.")
    except Exception as e:
        st.error(f"❌ Erro ao buscar editais do Compras.gov: {str(e)}")

# Comprasnet download direto
if not iniciar_varredura and acionar_comprasnet_download and comprasnet_coduasg.strip() and comprasnet_numprp.strip() and comprasnet_modprp.strip():
    try:
        ok = comprasnet_baixar_edital(comprasnet_coduasg.strip(), comprasnet_numprp.strip(), comprasnet_modprp.strip())
        if ok:
            st.success("✅ Edital (Comprasnet) baixado e registrado.")
        else:
            st.info("ℹ️ Não foi possível baixar o edital com os parâmetros informados.")
    except Exception as e:
        st.error(f"❌ Erro ao baixar edital (Comprasnet): {str(e)}")

# PNCP → Comprasnet auto
if not iniciar_varredura and acionar_pncp_auto and pncp_numero_controle.strip():
    try:
        trio = extract_trio_from_pncp(pncp_numero_controle.strip())
        if trio:
            c, n, m = trio
            ok = comprasnet_baixar_edital(c, n, m)
            if ok:
                st.success(f"✅ Trio extraído: coduasg={c}, numprp={n}, modprp={m}. Edital baixado e registrado.")
            else:
                st.info(f"ℹ️ Trio extraído: coduasg={c}, numprp={n}, modprp={m}, mas o download falhou.")
        else:
            st.info("ℹ️ Não foi possível extrair (coduasg,numprp,modprp) a partir do PNCP para esse número de controle.")
    except Exception as e:
        st.error(f"❌ Erro PNCP→Comprasnet: {str(e)}")

# PNCP API arquivos direto
if not iniciar_varredura and acionar_pncp_api and pncp_api_numero.strip():
    try:
        saved = pncp_api_baixar_todos(pncp_api_numero.strip())
        if saved:
            st.success(f"✅ Documentos baixados via PNCP API: {saved}")
        else:
            st.info("ℹ️ Nenhum arquivo retornado pela PNCP API para esse número de controle.")
    except Exception as e:
        st.error(f"❌ Erro PNCP API (arquivos): {str(e)}")

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
# Remover quaisquer registros fictícios remanescentes na visualização
if not licitacoes_df.empty:
    try:
        mask_portal = ~licitacoes_df["portal"].isin(["Licitações-e", "Comprasnet", "Portal de Compras Públicas"])
        mask_num = ~licitacoes_df["numero"].astype(str).str.startswith(("LICE-", "COMP-"), na=False)
        mask_titulo = ~licitacoes_df["titulo"].astype(str).str.contains(r"Licitação exemplo", case=False, na=False)
        licitacoes_df = licitacoes_df[mask_portal & mask_num & mask_titulo]
    except Exception:
        pass

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

# Ações por licitação (baixar documentos a partir da lista)
if not licitacoes_df.empty:
    st.markdown("---")
    st.subheader("⚙️ Ações por Licitação (baixar documentos)")
    st.caption("Para licitações PNCP, tentamos primeiro a PNCP API (arquivos); se não houver, tentamos PNCP→Comprasnet automaticamente.")
    max_rows = min(30, len(licitacoes_df))
    for idx in range(max_rows):
        row = licitacoes_df.iloc[idx]
        c1, c2, c3, c4 = st.columns([3, 3, 2, 2], gap="small")
        with c1:
            st.write(f"{row.get('portal','')} | {str(row.get('numero',''))[:60]}")
        with c2:
            st.write(str(row.get('titulo',''))[:60])
        with c3:
            if st.button("⬇️ Baixar docs", key=f"baixar_docs_{idx}"):
                numero_raw = str(row.get('numero','') or "")
                # Tentar extrair numeroControlePNCP do campo numero (padrão CNPJ-?-SEQ/ANO)
                m = re.match(r"^(\d{14})-\d-(\d{6})/(\d{4})$", numero_raw)
                downloaded = 0
                try:
                    if m:
                        numero_ctrl = numero_raw
                        downloaded = pncp_api_baixar_todos(numero_ctrl)
                    if not downloaded:
                        # Fallback PNCP→Comprasnet, se possível a partir do numero controle no título/descricao (pior cenário)
                        numero_hint = numero_raw
                        if not m:
                            # tentar achar em titulo/descricao
                            for src in [str(row.get('descricao','') or ""), str(row.get('titulo','') or "")]:
                                mm = re.search(r"(\d{14})-\d-(\d{6})/(\d{4})", src)
                                if mm:
                                    numero_hint = mm.group(0)
                                    break
                        if numero_hint:
                            trio = extract_trio_from_pncp(numero_hint)
                            if trio:
                                c, n, m2 = trio
                                ok = comprasnet_baixar_edital(c, n, m2)
                                downloaded = 1 if ok else 0
                except Exception as e:
                    st.error(f"Erro ao baixar documentos: {e}")
                    downloaded = 0
                if downloaded:
                    st.success("✅ Documentos baixados/registrados.")
                    # Propagar filtro para a seção de documentos
                    st.session_state["doc_filter_numero"] = numero_raw
                else:
                    st.info("ℹ️ Nenhum documento encontrado via PNCP API / fallback neste item.")
        with c4:
            if st.button("👁️ Ver docs", key=f"ver_docs_{idx}"):
                st.session_state["doc_filter_numero"] = str(row.get('numero','') or "")
                st.experimental_rerun()

# Documentos baixados
st.markdown("---")
st.subheader("📄 Documentos Baixados")
col_doc1, col_doc2, col_doc3 = st.columns(3)
with col_doc1:
    filtro_numero_controle = st.text_input("numeroControlePNCP", value=st.session_state.get("doc_filter_numero",""))
with col_doc2:
    filtro_portal_doc = st.selectbox("Portal", options=["", "PNCP 14133", "Compras.gov"], index=0)
with col_doc3:
    limite_docs = st.number_input("Limite", min_value=10, max_value=500, value=100, step=10)

docs_df = db.get_documentos(
    numero_controle=(filtro_numero_controle.strip() or None),
    portal=(filtro_portal_doc if filtro_portal_doc else None),
    limit=int(limite_docs)
)

if not docs_df.empty:
    st.dataframe(docs_df[["portal", "numero_controle", "tipo_documento", "nome_arquivo", "data_criacao"]], use_container_width=True, height=300)
    st.markdown("#### 💾 Baixar arquivo")
    for _, row in docs_df.iterrows():
        try:
            caminho_local = str(row["caminho_local"])
            with open(caminho_local, "rb") as f:
                st.download_button(
                    label=f"📥 {row['nome_arquivo']} ({row['portal']})",
                    data=f.read(),
                    file_name=row["nome_arquivo"],
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_{int(row['id'])}"
                )
        except Exception as e:
            st.warning(f"Arquivo não disponível: {row['caminho_local']}")
else:
    st.info("ℹ️ Nenhum documento encontrado no banco.")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center'>Desenvolvido com ❤️ para facilitar o acesso às licitações públicas brasileiras</div>",
    unsafe_allow_html=True
)
