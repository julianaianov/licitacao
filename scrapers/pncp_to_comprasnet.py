import re
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, parse_qs
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


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


def _parse_trio_from_url(u: str) -> Optional[Tuple[str, str, str]]:
    try:
        p = urlparse(u)
        q = parse_qs(p.query)
        coduasg = (q.get("coduasg") or q.get("uasg") or [None])[0]
        numprp = (q.get("numprp") or q.get("numprocesso") or [None])[0]
        modprp = (q.get("modprp") or q.get("modalidade") or [None])[0]
        if coduasg and numprp and modprp:
            return str(coduasg), str(numprp), str(modprp)
    except Exception:
        return None
    return None


def _extract_from_links(links: List[str]) -> Optional[Tuple[str, str, str]]:
    for u in links:
        if not isinstance(u, str):
            continue
        if "comprasnet.gov.br" in u.lower():
            trio = _parse_trio_from_url(u)
            if trio:
                return trio
    return None


def extract_trio_from_pncp(numero_controle: str) -> Optional[Tuple[str, str, str]]:
    """
    Tenta extrair (coduasg, numprp, modprp) a partir do PNCP:
    1) API de detalhes (linksExternos)
    2) Página app/editais/{cnpj}/{ano}/{seq}, buscando anchors com 'ConsLicitacao' ou 'download_editais_detalhe.asp'
    """
    s = _session()
    # Tentar extrair componentes do numero_controle
    cnpj = None
    ano = None
    seq = None
    try:
        parts = numero_controle.split("-")
        if len(parts) >= 3 and "/" in parts[-1]:
            cnpj = parts[0]
            seq_part, ano_part = parts[-1].split("/", 1)
            ano = ano_part
            seq = str(int(seq_part))
    except Exception:
        pass

    # 1) API de detalhes
    if cnpj:
        for base in ("https://pncp.gov.br/pncp/api/v1", "https://pncp.gov.br/api/pncp/v1", "https://pncp.gov.br/pncp-api/v1"):
            try:
                j = s.get(f"{base}/orgaos/{cnpj}/contratacoes/{numero_controle}", timeout=60).json()
            except Exception:
                j = None
            if isinstance(j, dict):
                links = j.get("linksExternos") or []
                trio = _extract_from_links(links)
                if trio:
                    return trio

    # 2) Scrape da página app
    if cnpj and ano and seq:
        for host in ("https://pncp.gov.br",):
            url = f"{host}/app/editais/{cnpj}/{ano}/{seq}"
            try:
                r = s.get(url, timeout=60)
                r.raise_for_status()
                html = r.text
            except Exception:
                continue
            # Procurar anchors
            for m in re.finditer(r'href=[\'"]([^\'"]+)[\'"]', html, re.IGNORECASE):
                href = m.group(1)
                # Resolver relativo
                if href.startswith("/"):
                    href = f"{host}{href}"
                trio = _parse_trio_from_url(href)
                if trio:
                    return trio
            # Procurar padrões em texto
            patt = r"coduasg=(\d+).+?numprp=(\d+).+?modprp=(\d+)"
            mm = re.search(patt, html, re.IGNORECASE | re.DOTALL)
            if mm:
                return mm.group(1), mm.group(2), mm.group(3)

    return None



