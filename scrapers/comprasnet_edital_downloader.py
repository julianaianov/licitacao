import os
from typing import Optional, Dict
import requests
from database.db_manager import DatabaseManager


DOWNLOAD_BASE = "https://comprasnet.gov.br/ConsultaLicitacoes/download/download_editais_detalhe.asp"


def baixar_edital_por_parametros(coduasg: str, numprp: str, modprp: str, timeout: int = 60) -> Optional[Dict]:
    """
    Baixa o PDF do edital diretamente do Comprasnet via endpoint ASP público.
    Retorna metadados para inserção no banco ou None em caso de erro.
    """
    params = {
        "coduasg": str(coduasg).strip(),
        "numprp": str(numprp).strip(),
        "modprp": str(modprp).strip(),
    }
    try:
        with requests.get(DOWNLOAD_BASE, params=params, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "pdf" not in ctype and "octet-stream" not in ctype:
                return None
            # Caminho de saída
            out_dir = os.path.join("export", "editais", "Comprasnet", f"{params['coduasg']}_{params['numprp']}_{params['modprp']}")
            os.makedirs(out_dir, exist_ok=True)
            fname = "edital.pdf"
            path = os.path.join(out_dir, fname)
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return {
                "portal": "Comprasnet",
                "numero_controle": f"{params['coduasg']}-{params['numprp']}-{params['modprp']}",
                "id_compra": None,
                "ano_compra": None,
                "sequencial_compra": None,
                "tipo_documento": "Edital",
                "nome_arquivo": fname,
                "url": r.url,
                "caminho_local": path,
                "tamanho_bytes": os.path.getsize(path),
                "sha256": None,
                "data_publicacao": None,
            }
    except Exception:
        return None


def baixar_e_registrar(coduasg: str, numprp: str, modprp: str) -> bool:
    meta = baixar_edital_por_parametros(coduasg, numprp, modprp)
    if not meta:
        return False
    db = DatabaseManager()
    return db.insert_documento(meta)



