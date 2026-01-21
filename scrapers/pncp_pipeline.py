import os
from typing import Dict, List, Optional, Tuple
from datetime import date
from urllib.parse import urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup

from database.db_manager import DatabaseManager
from .pncp_api_arquivos import baixar_todos_por_numero


def _session(timeout: int = 60) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
        "Accept": "application/json,text/html;q=0.9",
    })
    retry = Retry(total=5, connect=5, read=5, status=5, backoff_factor=1.2,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]),
                  raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.timeout = timeout
    return s


def detectar_origem(link: Optional[str]) -> str:
    if not link:
        return "desconhecido"
    l = link.lower()
    if "compras" in l or "comprasnet" in l:
        return "comprasnet"
    if l.endswith(".pdf"):
        return "pdf_direto"
    if "sei" in l:
        return "sei"
    return "portal"


def baixar_pdf(url: str, base_dir: str, file_name: Optional[str] = None) -> Optional[str]:
    s = _session()
    try:
        r = s.get(url, stream=True, timeout=60)
        r.raise_for_status()
        os.makedirs(base_dir, exist_ok=True)
        name = file_name or os.path.basename(url.split("?")[0]) or "documento.pdf"
        path = os.path.join(base_dir, name)
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return path
    except Exception:
        return None


def extrair_links_pdf(url: str) -> List[str]:
    s = _session()
    try:
        r = s.get(url, timeout=60)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        hrefs = [a["href"] for a in soup.select("a[href$='.pdf']")]
        # Resolver relativos
        full: List[str] = []
        from urllib.parse import urljoin
        for h in hrefs:
            full.append(h if h.startswith("http") else urljoin(url, h))
        return list(dict.fromkeys(full))
    except Exception:
        return []


def baixar_por_comprasnet(uasg: str, numero_processo: str, out_dir: str) -> int:
    """
    Exemplo de endpoint público para documentos de licitações no gov.br/compras (pode variar).
    """
    s = _session()
    url = "https://www.gov.br/compras/api/licitacoes/documentos"
    params = {"uasg": str(uasg).strip(), "numeroProcesso": str(numero_processo).strip()}
    try:
        r = s.get(url, params=params, timeout=60)
        r.raise_for_status()
        docs = r.json()
    except Exception:
        docs = []
    saved = 0
    for d in docs if isinstance(docs, list) else []:
        u = d.get("urlArquivo") or ""
        if u.lower().endswith(".pdf"):
            path = baixar_pdf(u, out_dir)
            if path:
                saved += 1
    return saved


def _pncp_index(data_inicial: str, data_final: str, page_size: int = 50, max_pages: int = 20) -> List[Dict]:
    s = _session()
    base = "https://pncp.gov.br/api/consulta/v1/contratacoes"
    resultados: List[Dict] = []
    for pagina in range(1, max_pages + 1):
        params = {
            "pagina": pagina,
            "tamanhoPagina": page_size,
            "dataInicial": data_inicial,
            "dataFinal": data_final,
        }
        try:
            r = s.get(base, params=params, timeout=60)
            r.raise_for_status()
            j = r.json()
            data = j.get("data") if isinstance(j, dict) else (j if isinstance(j, list) else [])
        except Exception:
            break
        if not isinstance(data, list) or not data:
            break
        resultados.extend(data)
        if len(data) < page_size:
            break
    return resultados


def processar_periodo(data_inicial: date, data_final: date, limit: int = 100) -> int:
    """
    Para cada contratação PNCP no período:
      - detecta origem
      - baixa PDFs
      - insere em 'documentos'
    Retorna quantidade de documentos inseridos.
    """
    dmin = data_inicial.strftime("%Y-%m-%d")
    dmax = data_final.strftime("%Y-%m-%d")
    itens = _pncp_index(dmin, dmax, page_size=50, max_pages=10)
    if not itens:
        return 0
    inserted = 0
    db = DatabaseManager()
    for item in itens[:limit]:
        link = item.get("linkExterno") or item.get("link") or ""
        origem = detectar_origem(link)
        numero_ctrl = item.get("numeroControlePNCP") or ""
        # 0) Tentar PNCP API arquivos diretamente primeiro
        if numero_ctrl:
            try:
                saved_api = baixar_todos_por_numero(numero_ctrl)
            except Exception:
                saved_api = 0
            if saved_api:
                inserted += saved_api
                continue
        # Base de destino
        out_dir = os.path.join("export", "editais", "PNCP-Pipeline", numero_ctrl or "desconhecido")
        if origem == "comprasnet":
            uasg = (item.get("orgaoEntidade") or {}).get("codigoUasg") or ""
            numproc = item.get("numeroProcesso") or ""
            if uasg and numproc:
                saved = baixar_por_comprasnet(str(uasg), str(numproc), out_dir)
                inserted += saved
        elif origem == "pdf_direto":
            p = baixar_pdf(link, out_dir)
            if p:
                meta = {
                    "portal": "PNCP Pipeline",
                    "numero_controle": numero_ctrl,
                    "id_compra": None,
                    "ano_compra": None,
                    "sequencial_compra": None,
                    "tipo_documento": "PDF direto",
                    "nome_arquivo": os.path.basename(p),
                    "url": link,
                    "caminho_local": p,
                    "tamanho_bytes": os.path.getsize(p),
                    "sha256": None,
                    "data_publicacao": None,
                }
                if db.insert_documento(meta):
                    inserted += 1
        else:
            # Portal próprio/SEI: raspar HTML e baixar PDFs encontrados
            for u in extrair_links_pdf(link):
                p = baixar_pdf(u, out_dir)
                if p:
                    meta = {
                        "portal": "PNCP Pipeline",
                        "numero_controle": numero_ctrl,
                        "id_compra": None,
                        "ano_compra": None,
                        "sequencial_compra": None,
                        "tipo_documento": "Portal",
                        "nome_arquivo": os.path.basename(p),
                        "url": u,
                        "caminho_local": p,
                        "tamanho_bytes": os.path.getsize(p),
                        "sha256": None,
                        "data_publicacao": None,
                    }
                    if db.insert_documento(meta):
                        inserted += 1
    return inserted


