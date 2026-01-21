import os
from typing import List, Dict, Optional, Tuple
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from database.db_manager import DatabaseManager


def _session(timeout: int = 90) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
        "Accept": "application/json,application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    })
    retry = Retry(total=5, connect=5, read=5, status=5, backoff_factor=1.2,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]),
                  raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.timeout = timeout
    return s


def parse_numero_controle(numero: str) -> Tuple[str, str, str]:
    # Ex.: 83102269000106-1-000163/2025
    m = re.match(r"^(\d{14})-\d-(\d{6})/(\d{4})$", numero.strip())
    if not m:
        raise ValueError("numeroControlePNCP inválido (espera CNPJ-?-SEQ/ANO)")
    cnpj, seq, ano = m.group(1), m.group(2), m.group(3)
    return cnpj, ano, str(int(seq))


def listar_arquivos(cnpj: str, ano: str, seq: str) -> List[Dict]:
    s = _session()
    url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
    try:
        r = s.get(url, timeout=90)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def baixar_arquivo(cnpj: str, ano: str, seq: str, arquivo_id: str) -> Optional[str]:
    s = _session()
    url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos/{arquivo_id}"
    try:
        r = s.get(url, stream=True, timeout=90)
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "pdf" not in ctype and "octet-stream" not in ctype:
            return None
        out_dir = os.path.join("export", "editais", "PNCP_API", cnpj, ano, seq)
        os.makedirs(out_dir, exist_ok=True)
        fname = "documento.pdf"
        cd = r.headers.get("Content-Disposition") or ""
        if "filename=" in cd:
            try:
                fname = cd.split("filename=")[1].strip().strip('"').strip("'")
            except Exception:
                pass
        path = os.path.join(out_dir, os.path.basename(fname) or "documento.pdf")
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return path
    except Exception:
        return None


def baixar_todos_por_numero(numero_controle: str) -> int:
    cnpj, ano, seq = parse_numero_controle(numero_controle)
    arquivos = listar_arquivos(cnpj, ano, seq)
    if not arquivos:
        return 0
    db = DatabaseManager()
    inserted = 0
    for arq in arquivos:
        arq_id = str(arq.get("id") or arq.get("arquivoId") or "")
        if not arq_id:
            continue
        p = baixar_arquivo(cnpj, ano, seq, arq_id)
        if not p:
            continue
        meta = {
            "portal": "PNCP API",
            "numero_controle": numero_controle,
            "id_compra": None,
            "ano_compra": int(ano),
            "sequencial_compra": int(seq),
            "tipo_documento": "DOCUMENTO",
            "nome_arquivo": os.path.basename(p),
            "url": f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos/{arq_id}",
            "caminho_local": p,
            "tamanho_bytes": os.path.getsize(p),
            "sha256": None,
            "data_publicacao": None,
        }
        if db.insert_documento(meta):
            inserted += 1
    return inserted


