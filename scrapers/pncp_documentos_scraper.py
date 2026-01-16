import os
import hashlib
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from urllib.parse import quote
from bs4 import BeautifulSoup


class PncpDocumentosScraper:
    """
    Best-effort para coletar documentos (editais/anexos) de contratações PNCP (Lei 14.133).
    Observação: Endpoints podem variar; tentamos alguns formatos conhecidos. Falhas são tratadas silenciosamente.
    Requer metadados PNCP do registro: numeroControlePNCP, anoCompraPncp, sequencialCompraPncp e/ou idCompra.
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
            "Accept": "application/json",
        })
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=1.2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _candidate_endpoints(self, meta: Dict) -> List[Tuple[str, Optional[Dict], bool]]:
        """
        Gera endpoints candidatos para buscar documentos PNCP.
        Prioriza o endpoint oficial por numeroControlePNCP:
          GET https://pncp.gov.br/pncp/api/v1/contratacoes/{numeroControlePNCP}/documentos
        Depois testa variantes heurísticas.
        """
        numero = meta.get("numeroControlePNCP")
        ano = meta.get("anoCompraPncp")
        seq = meta.get("sequencialCompraPncp")
        idc = meta.get("idCompra")
        candidates: List[Tuple[str, Optional[Dict], bool]] = []
        # 1) Endpoint direto por numeroControlePNCP (conforme especificação fornecida)
        if numero:
            numero_str = str(numero)
            enc = quote(numero_str, safe="")
            enc_dash = quote(numero_str.replace("/", "-"), safe="")
            # Principal
            candidates.append((
                f"https://pncp.gov.br/pncp/api/v1/contratacoes/{enc}/documentos",
                None,
                True  # direct path (sem params)
            ))
            # Variante de base (alguns ambientes usam api/pncp ao invés de pncp/api)
            candidates.append((
                f"https://pncp.gov.br/api/pncp/v1/contratacoes/{enc}/documentos",
                None,
                True
            ))
            # Variante pncp-api
            candidates.append((
                f"https://pncp.gov.br/pncp-api/v1/contratacoes/{enc}/documentos",
                None,
                True
            ))
            # Variante com slash substituído por hífen
            candidates.append((
                f"https://pncp.gov.br/pncp/api/v1/contratacoes/{enc_dash}/documentos",
                None,
                True
            ))
            candidates.append((
                f"https://pncp.gov.br/api/pncp/v1/contratacoes/{enc_dash}/documentos",
                None,
                True
            ))
            candidates.append((
                f"https://pncp.gov.br/pncp-api/v1/contratacoes/{enc_dash}/documentos",
                None,
                True
            ))
        # 2) Heurística antiga (consulta genérica), pode retornar lista de docs
        # Formato por ano/seq (hipotético)
        if ano and seq:
            candidates.append((
                "https://pncp.gov.br/api/pncp/v1/consulta/contratacoes/documentos",
                {"ano": ano, "sequencial": seq},
                False
            ))
        # Formato por idCompra (hipotético)
        if idc:
            candidates.append((
                "https://pncp.gov.br/api/pncp/v1/consulta/contratacoes/documentos",
                {"idCompra": idc},
                False
            ))
        # Endpoint alternativo (compras.dados.gov.br) caso exista proxy:
        if numero:
            candidates.append((
                "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarDocumentos_PNCP_14133",
                {"numeroControlePNCP": numero},
                False
            ))
        return candidates

    def _safe_json(self, url: str, params: Optional[Dict], direct: bool) -> Optional[object]:
        try:
            if direct:
                r = self.session.get(url, timeout=60)
            else:
                r = self.session.get(url, params=params or {}, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def _sha256_file(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _download(self, url: str, dest_path: str) -> Optional[Tuple[int, str]]:
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with self.session.get(url, timeout=120, stream=True) as r:
                r.raise_for_status()
                size = 0
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            size += len(chunk)
            sha = self._sha256_file(dest_path)
            return size, sha
        except Exception:
            # Remover arquivo incompleto
            try:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
            except Exception:
                pass
            return None
    
    def _download_link_externo(self, url: str, dest_dir: str) -> Optional[Tuple[str, int, str]]:
        """
        Tenta baixar um PDF de um link externo:
         - se content-type for PDF ou URL terminar com .pdf, baixa diretamente
         - senão, busca links <a> para PDFs na página e baixa o primeiro
        Retorna (caminho_local, tamanho_bytes, sha256) se sucesso.
        """
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with self.session.get(url, timeout=60, stream=True) as r:
                r.raise_for_status()
                ctype = (r.headers.get("Content-Type") or "").lower()
                # Se já é PDF direto:
                if "pdf" in ctype or url.lower().endswith(".pdf"):
                    nome = os.path.basename(url.split("?")[0]) or "documento.pdf"
                    dest_path = os.path.join(dest_dir, nome)
                    size = 0
                    with open(dest_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                size += len(chunk)
                    sha = self._sha256_file(dest_path)
                    return dest_path, size, sha
                # Se é HTML, tentar achar links PDF
                content = b""
                for chunk in r.iter_content(chunk_size=16384):
                    if chunk:
                        content += chunk
                        if len(content) > 5_000_000:  # limite 5MB
                            break
                html = content.decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, "lxml")
                a = soup.find("a", href=lambda h: h and h.lower().endswith(".pdf"))
                if a and a.get("href"):
                    href = a["href"]
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    # baixar o PDF encontrado
                    nome = os.path.basename(href.split("?")[0]) or "documento.pdf"
                    dest_path = os.path.join(dest_dir, nome)
                    dl = self._download(href, dest_path)
                    if dl:
                        size, sha = dl
                        return dest_path, size, sha
        except Exception:
            return None
        return None

    def buscar_documentos(self, pncp_meta: Dict, base_export_dir: str) -> List[Dict]:
        """
        Retorna lista de documentos com metadados mínimos e, quando possível, baixa o PDF para disco.
        Estrutura do retorno (cada item):
            {
              portal: 'PNCP 14133',
              numero_controle, id_compra, ano_compra, sequencial_compra,
              tipo_documento, nome_arquivo, url, caminho_local, tamanho_bytes, sha256, data_publicacao
            }
        """
        docs: List[Dict] = []
        # 0) Checar detalhes da contratação para saber se tem documentos/linksExternos
        numero = (pncp_meta or {}).get("numeroControlePNCP")
        detalhes = None
        if numero:
            enc = quote(str(numero), safe="")
            for base in ("https://pncp.gov.br/pncp/api/v1", "https://pncp.gov.br/api/pncp/v1", "https://pncp.gov.br/pncp-api/v1"):
                url = f"{base}/contratacoes/{enc}"
                j = self._safe_json(url, None, True)
                if isinstance(j, dict) and j:
                    detalhes = j
                    break
        tem_indicacao_docs = False
        links_externos = []
        if isinstance(detalhes, dict):
            if detalhes.get("possuiDocumentos") or (isinstance(detalhes.get("quantidadeDocumentos"), int) and detalhes["quantidadeDocumentos"] > 0):
                tem_indicacao_docs = True
            if isinstance(detalhes.get("linksExternos"), list):
                links_externos = [x for x in detalhes["linksExternos"] if isinstance(x, str)]
                if links_externos:
                    tem_indicacao_docs = True

        endpoints = self._candidate_endpoints(pncp_meta or {})
        payloads: List[Dict] = []
        if tem_indicacao_docs:
            for url, params, direct in endpoints:
                j = self._safe_json(url, params, direct)
                if not j:
                    continue
                rows = []
                if isinstance(j, list):
                    rows = j
                elif isinstance(j, dict):
                    rows = j.get("resultado") or j.get("documentos") or []
                if not isinstance(rows, list) or not rows:
                    continue
                payloads.extend(rows)
                if payloads:
                    break
            # 1.1) Tentar documentos por eventos (se ainda nada encontrado)
            if not payloads and numero:
                enc = quote(str(numero), safe="")
                for base in ("https://pncp.gov.br/pncp/api/v1", "https://pncp.gov.br/api/pncp/v1", "https://pncp.gov.br/pncp-api/v1"):
                    eventos_url = f"{base}/contratacoes/{enc}/eventos"
                    ev = self._safe_json(eventos_url, None, True)
                    if isinstance(ev, list):
                        for e in ev:
                            ev_id = e.get("id") or e.get("idEvento")
                            if not ev_id:
                                continue
                            ev_docs_url = f"{base}/contratacoes/{enc}/eventos/{ev_id}/documentos"
                            d = self._safe_json(ev_docs_url, None, True)
                            if isinstance(d, list) and d:
                                payloads.extend(d)
                                break
                        if payloads:
                            break
        else:
            # Se não houver indicação de documentos, aproveitar linksExternos (se houver)
            for link in links_externos:
                payloads.append({
                    "tipoDocumento": "Link Externo",
                    "nomeArquivo": os.path.basename(link) or "documento",
                    "url": link,
                    "dataPublicacao": None
                })
        for rec in payloads:
            # Heurísticas de campo
            nome = rec.get("nomeArquivo") or rec.get("titulo") or rec.get("nome") or "documento.pdf"
            url_doc = rec.get("url") or rec.get("link") or rec.get("href")
            tipo = rec.get("tipoDocumento") or rec.get("tipo") or "DOCUMENTO"
            dt_pub = rec.get("dataPublicacao") or rec.get("data") or rec.get("dataInclusao")
            try:
                dt_pub_parsed = None
                if dt_pub:
                    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
                        try:
                            dt_pub_parsed = datetime.strptime(str(dt_pub)[:26], fmt)
                            break
                        except Exception:
                            continue
                ano_dir = str(pncp_meta.get("anoCompraPncp") or datetime.now().year)
                idc_dir = str(pncp_meta.get("idCompra") or pncp_meta.get("numeroControlePNCP") or "desconhecido")
                safe_nome = str(nome).replace("/", "_").replace("\\", "_")
                dest_dir = os.path.join(base_export_dir, "editais", ano_dir, idc_dir)
                dest_path = os.path.join(dest_dir, safe_nome)
            except Exception:
                dest_path = None
                dt_pub_parsed = None

            tamanho = None
            sha = None
            caminho_local = None
            if url_doc:
                if dest_path:
                    dl = self._download(url_doc, dest_path)
                    if dl:
                        tamanho, sha = dl
                        caminho_local = dest_path
                if not caminho_local:
                    # Tentar como link externo (HTML → achar PDF)
                    alt = self._download_link_externo(url_doc, dest_dir=os.path.dirname(dest_path) if dest_path else os.path.join(base_export_dir, "editais"))
                    if alt:
                        caminho_local, tamanho, sha = alt

            docs.append({
                "portal": "PNCP 14133",
                "numero_controle": pncp_meta.get("numeroControlePNCP"),
                "id_compra": pncp_meta.get("idCompra"),
                "ano_compra": pncp_meta.get("anoCompraPncp"),
                "sequencial_compra": pncp_meta.get("sequencialCompraPncp"),
                "tipo_documento": tipo,
                "nome_arquivo": nome,
                "url": url_doc,
                "caminho_local": caminho_local,
                "tamanho_bytes": tamanho,
                "sha256": sha,
                "data_publicacao": dt_pub_parsed,
            })
        return docs


