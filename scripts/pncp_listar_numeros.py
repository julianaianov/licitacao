import sys
import argparse
import json
import csv
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


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


def parse_date(s: str) -> datetime.date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def normalize_rows(j: Any) -> List[Dict]:
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        for key in ("content", "items", "resultado", "contratacoes", "dados", "data"):
            rows = j.get(key)
            if isinstance(rows, list):
                return rows
    return []


def extract_numero_controle(row: Dict) -> Optional[str]:
    for key in ("numeroControlePNCP", "numero_controle", "numeroControle"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fallback: tentar em sub-objetos conhecidos
    meta = row.get("pncp_meta")
    if isinstance(meta, dict):
        v = meta.get("numeroControlePNCP")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def listar_numeros(inicio: datetime.date,
                   fim: datetime.date,
                   pagina_inicial: int,
                   paginas: int,
                   tamanho: int,
                   modalidade: str,
                   situacao: str,
                   objeto: str) -> List[Dict[str, str]]:
    sess = build_session()
    bases = [
        "https://pncp.gov.br/pncp/api/v1/contratacoes",
        "https://pncp.gov.br/api/pncp/v1/contratacoes",
        "https://pncp.gov.br/pncp-api/v1/contratacoes",
    ]
    date_variants = [
        ("dataPublicacaoPncpInicial", "dataPublicacaoPncpFinal"),
        ("dataPublicacaoInicial", "dataPublicacaoFinal"),
    ]
    dmin = inicio.strftime("%Y-%m-%d")
    dmax = fim.strftime("%Y-%m-%d")
    resultados: List[Dict[str, str]] = []

    for base in bases:
        for dkeys in date_variants:
            found_any = False
            for page in range(pagina_inicial, pagina_inicial + paginas):
                params: Dict[str, Any] = {
                    "pagina": page,
                    "tamanhoPagina": tamanho,
                }
                params[dkeys[0]] = dmin
                params[dkeys[1]] = dmax
                if modalidade:
                    params["modalidade"] = modalidade
                if situacao:
                    params["situacao"] = situacao
                if objeto:
                    params["objeto"] = objeto
                try:
                    r = sess.get(base, params=params, timeout=60)
                    r.raise_for_status()
                    j = r.json()
                except Exception:
                    break
                rows = normalize_rows(j)
                if not rows:
                    break
                found_any = True
                for row in rows:
                    num = extract_numero_controle(row)
                    if num:
                        resultados.append({
                            "numeroControlePNCP": num,
                            "modalidade": str(row.get("modalidade") or ""),
                            "situacao": str(row.get("situacao") or ""),
                            "ano": str(row.get("ano") or ""),
                            "sequencial": str(row.get("sequencial") or ""),
                        })
                if len(rows) < tamanho:
                    break
            if found_any:
                return resultados
    return resultados


def main():
    ap = argparse.ArgumentParser(description="Listar numerosControlePNCP por período e filtros")
    ap.add_argument("--inicio", required=False, help="Data inicial (YYYY-MM-DD). Default: hoje-30d")
    ap.add_argument("--fim", required=False, help="Data final (YYYY-MM-DD). Default: hoje")
    ap.add_argument("--pagina-inicial", type=int, default=1, help="Página inicial (default: 1)")
    ap.add_argument("--paginas", type=int, default=10, help="Quantas páginas ler (default: 10)")
    ap.add_argument("--tamanho", type=int, default=50, help="Tamanho da página (default: 50)")
    ap.add_argument("--modalidade", default="", help="Ex.: PREGAO_ELETRONICO (vazio = sem filtro)")
    ap.add_argument("--situacao", default="", help="Ex.: PUBLICADA (vazio = sem filtro)")
    ap.add_argument("--objeto", default="", help="Filtro por palavra no objeto (vazio = sem filtro)")
    ap.add_argument("--saida", default="export/pncp_numeros.json", help="Arquivo de saída (.json ou .csv)")
    args = ap.parse_args()

    hoje = datetime.now().date()
    fim = parse_date(args.fim) if args.fim else hoje
    inicio = parse_date(args.inicio) if args.inicio else (hoje - timedelta(days=30))

    print(f"Período: {inicio} .. {fim}")
    print(f"Filtros: modalidade='{args.modalidade}' situacao='{args.situacao}' objeto='{args.objeto}'")
    numeros = listar_numeros(
        inicio=inicio,
        fim=fim,
        pagina_inicial=args.pagina_inicial,
        paginas=args.paginas,
        tamanho=args.tamanho,
        modalidade=args.modalidade,
        situacao=args.situacao,
        objeto=args.objeto,
    )
    print(f"Total de numerosControlePNCP: {len(numeros)}")
    if args.saida.lower().endswith(".csv"):
        if numeros:
            fieldnames = list(numeros[0].keys())
        else:
            fieldnames = ["numeroControlePNCP", "modalidade", "situacao", "ano", "sequencial"]
        with open(args.saida, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in numeros:
                w.writerow(row)
        print(f"Salvo: {args.saida}")
    else:
        with open(args.saida, "w", encoding="utf-8") as f:
            json.dump(numeros, f, ensure_ascii=False, indent=2)
        print(f"Salvo: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())



