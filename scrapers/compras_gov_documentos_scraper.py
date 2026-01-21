import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup


class ComprasGovDocumentosScraper:
    """
    Best-effort para localizar e baixar PDFs (edital/anexos) no portal Compras.gov a partir de:
      - numero_aviso (obrigatório)
      - UASG (opcional, melhora a busca)
    Estratégia: tentar páginas conhecidas e varrer por links .pdf.
    """
    def __init__(self, timeout: int = 60):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
        self.timeout = timeout

    def _candidate_urls(self, numero_aviso: str, uasg: Optional[str]) -> List[str]:
        """
        Gera URLs candidatas do portal Compras.gov onde, geralmente, há links de PDF.
        Observação: os caminhos podem variar entre entes/portais; esta lista é heurística.
        """
        n = str(numero_aviso).strip()
        u = str(uasg).strip() if uasg else None
        urls: List[str] = []
        # Áreas comuns de publicação de editais
        # Transparência / Licitações por tribunal/órgão específico (heurístico)
        if u:
            urls.append(f"https://www.gov.br/compras/pt-br/acesso-a-informacao/licitacoes/uasg-{u}/aviso-{n}")
        urls.append(f"https://www.gov.br/compras/pt-br/acesso-a-informacao/licitacoes/aviso-{n}")
        # Página genérica de busca (pode conter link para detalhe)
        urls.append(f"https://www.gov.br/compras/pt-br/acesso-a-informacao/licitacoes?searchterm={n}")
        return urls

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def _find_pdf_links(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        pdfs: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not isinstance(href, str):
                continue
            href_lower = href.lower()
            if ".pdf" in href_lower:
                if href_lower.startswith("http://") or href_lower.startswith("https://"):
                    pdfs.append(href)
                else:
                    from urllib.parse import urljoin
                    pdfs.append(urljoin(base_url, href))
        return list(dict.fromkeys(pdfs))  # unique

    def _download(self, url: str, dest_dir: str) -> Optional[Tuple[str, int]]:
        try:
            os.makedirs(dest_dir, exist_ok=True)
            name = os.path.basename(url.split("?")[0]) or "documento.pdf"
            dest_path = os.path.join(dest_dir, name)
            with self.session.get(url, timeout=self.timeout, stream=True) as r:
                r.raise_for_status()
                size = 0
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            size += len(chunk)
            return dest_path, size
        except Exception:
            return None

    def buscar_documentos(self, numero_aviso: str, uasg: Optional[str], base_export_dir: str = "export") -> List[Dict]:
        """
        Retorna metadados dos PDFs baixados com portal='Compras.gov'.
        """
        resultados: List[Dict] = []
        for url in self._candidate_urls(numero_aviso, uasg):
            html = self._fetch_html(url)
            if not html:
                continue
            pdf_links = self._find_pdf_links(html, url)
            if not pdf_links:
                continue
            # Salvar PDFs
            dest_dir = os.path.join(base_export_dir, "editais", "ComprasGov", str(numero_aviso))
            for link in pdf_links:
                dl = self._download(link, dest_dir)
                if not dl:
                    continue
                caminho, tamanho = dl
                resultados.append({
                    "portal": "Compras.gov",
                    "numero_controle": str(numero_aviso),
                    "id_compra": None,
                    "ano_compra": None,
                    "sequencial_compra": None,
                    "tipo_documento": "PDF",
                    "nome_arquivo": os.path.basename(caminho),
                    "url": link,
                    "caminho_local": caminho,
                    "tamanho_bytes": tamanho,
                    "sha256": None,
                    "data_publicacao": None,
                })
            # Se já baixamos algum PDF nessa URL, podemos parar
            if resultados:
                break
        return resultados



