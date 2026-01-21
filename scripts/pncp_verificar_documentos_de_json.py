import sys
import argparse
import json
import re
import csv
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from urllib.parse import quote, urlparse


PNCP_REGEX = re.compile(r"\b\d{14}-\d-\d{6}/\d{4}\b")


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
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
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def safe_json_get(session: requests.Session, url: str) -> Optional[Any]:
    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def extract_numbers_from_obj(obj: Any, found: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                for m in PNCP_REGEX.findall(v):
                    found.add(m)
            elif isinstance(v, (dict, list)):
                extract_numbers_from_obj(v, found)
            if isinstance(k, str):
                for m in PNCP_REGEX.findall(k):
                    found.add(m)
    elif isinstance(obj, list):
        for item in obj:
            extract_numbers_from_obj(item, found)
    elif isinstance(obj, str):
        for m in PNCP_REGEX.findall(obj):
            found.add(m)


def extract_numbers_from_json(path: str) -> List[str]:
    found: set = set()
    text = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        try:
            obj = json.loads(text)
            extract_numbers_from_obj(obj, found)
        except Exception:
            for m in PNCP_REGEX.findall(text):
                found.add(m)
    except Exception as e:
        print(f"Erro ao ler {path}: {e}")
    return list(found)


def get_details(session: requests.Session, numero: str, cnpj: Optional[str]) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Retorna (detalhes_json, base_usada)
    Tenta por órgão (se cnpj) e sem órgão, nas três bases conhecidas.
    """
    bases = ("https://pncp.gov.br/pncp/api/v1", "https://pncp.gov.br/api/pncp/v1", "https://pncp.gov.br/pncp-api/v1")
    enc = quote(str(numero), safe="")
    if cnpj:
        c = quote(str(cnpj), safe="")
        for b in bases:
            u = f"{b}/orgaos/{c}/contratacoes/{enc}"
            j = safe_json_get(session, u)
            if isinstance(j, dict) and j:
                return j, b
    for b in bases:
        u = f"{b}/contratacoes/{enc}"
        j = safe_json_get(session, u)
        if isinstance(j, dict) and j:
            return j, b
    return None, None


def any_event_has_docs(session: requests.Session, base: str, numero: str, cnpj: Optional[str]) -> bool:
    enc = quote(str(numero), safe="")
    urls = []
    if cnpj:
        c = quote(str(cnpj), safe="")
        urls.append(f"{base}/orgaos/{c}/contratacoes/{enc}/eventos")
    urls.append(f"{base}/contratacoes/{enc}/eventos")
    for u in urls:
        ev = safe_json_get(session, u)
        if isinstance(ev, list):
            for e in ev:
                # Se já trouxer contadores, use-os
                q = e.get("quantidadeDocumentos")
                if isinstance(q, int) and q > 0:
                    return True
                # Como alternativa, podemos tentar /eventos/{id}/documentos (apenas para ver se vem algo)
                ev_id = e.get("id") or e.get("idEvento")
                if ev_id:
                    if u.endswith("/eventos"):
                        prefix = u[:-8]  # remove '/eventos'
                    else:
                        parsed = urlparse(u)
                        prefix = f"{parsed.scheme}://{parsed.netloc}"
                    # Construir URL de forma robusta:
                    if "/orgaos/" in u:
                        # .../orgaos/{c}/contratacoes/{enc}
                        idx = u.find("/orgaos/")
                        prefix = u[:idx]
                        rest = u[idx:]
                        rest = rest.split("/eventos")[0]
                        ev_docs = f"{prefix}{rest}/eventos/{ev_id}/documentos"
                    else:
                        # .../contratacoes/{enc}
                        idx = u.find("/contratacoes/")
                        prefix = u[:idx]
                        rest = u[idx:].split("/eventos")[0]
                        ev_docs = f"{prefix}{rest}/eventos/{ev_id}/documentos"
                    d = safe_json_get(session, ev_docs)
                    if isinstance(d, list) and d:
                        return True
    return False


def scan_numbers(numbers: List[str], cnpj_hint: Optional[str], limit: int, write_csv: Optional[str]) -> int:
    sess = build_session()
    report: List[Dict[str, Any]] = []
    hits = 0
    for i, numero in enumerate(numbers[:limit], start=1):
        detalhes, base = get_details(sess, numero, cnpj_hint)
        possui = False
        qnt = 0
        links = 0
        if isinstance(detalhes, dict):
            if isinstance(detalhes.get("quantidadeDocumentos"), int):
                qnt = detalhes["quantidadeDocumentos"]
            if detalhes.get("possuiDocumentos") is True:
                possui = True
            if isinstance(detalhes.get("linksExternos"), list):
                links = len(detalhes["linksExternos"])
                if links > 0:
                    possui = True
            if not possui:
                # Checar eventos
                if base and any_event_has_docs(sess, base, numero, cnpj_hint):
                    possui = True
        if possui:
            hits += 1
        report.append({
            "numeroControlePNCP": numero,
            "possuiDocumentos": possui,
            "quantidadeDocumentos": qnt,
            "linksExternos": links,
            "base": base or "",
            "cnpj_hint": cnpj_hint or "",
        })
        print(f"[{i}/{min(limit, len(numbers))}] {numero} -> possui={possui} qtd={qnt} links={links}")
    if write_csv:
        with open(write_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(report[0].keys()) if report else ["numeroControlePNCP","possuiDocumentos","quantidadeDocumentos","linksExternos","base","cnpj_hint"])
            w.writeheader()
            for row in report:
                w.writerow(row)
        print(f"Relatório salvo em: {write_csv}")
    return hits


def main():
    ap = argparse.ArgumentParser(description="Vasculha um JSON e marca quais numeros PNCP têm documentos anexos.")
    ap.add_argument("--json", required=True, help="Caminho para arquivo JSON que contenha numerosControlePNCP")
    ap.add_argument("--limit", type=int, default=200, help="Máximo de números a verificar (default: 200)")
    ap.add_argument("--cnpj", required=False, help="CNPJ do órgão (opcional, tenta endpoints por órgão primeiro)")
    ap.add_argument("--csv", required=False, help="Salvar relatório CSV neste caminho")
    args = ap.parse_args()

    numbers = extract_numbers_from_json(args.json)
    print(f"Números PNCP encontrados no JSON: {len(numbers)}")
    if not numbers:
        print("Nenhum numeroControlePNCP encontrado no JSON.")
        return 2
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = args.csv or f"export/pncp_documentos_scan_{ts}.csv"
    hits = scan_numbers(numbers, args.cnpj, args.limit, write_csv=out_csv)
    print(f"Total com indicação de documentos: {hits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())



