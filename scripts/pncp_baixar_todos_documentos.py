import sys
import argparse
from datetime import datetime, timedelta

from scrapers.pncp_api_scraper import PncpApiScraper
from scrapers.pncp_documentos_scraper import PncpDocumentosScraper
from database.db_manager import DatabaseManager


def parse_date(s: str) -> datetime.date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser(description="Baixar TODOS os documentos PNCP por período (API oficial).")
    ap.add_argument("--inicio", required=False, help="Data inicial (YYYY-MM-DD). Default: hoje-30d")
    ap.add_argument("--fim", required=False, help="Data final (YYYY-MM-DD). Default: hoje")
    ap.add_argument("--ano", type=int, default=0, help="Forçar ano (ex.: 2024). Default: derivado de --fim")
    ap.add_argument("--modalidade", default="", help="Ex.: PREGAO_ELETRONICO (vazio = sem filtro)")
    ap.add_argument("--situacao", default="", help="Ex.: PUBLICADA (vazio = sem filtro)")
    ap.add_argument("--keyword", default="", help="Filtro opcional por palavra no objeto")
    ap.add_argument("--limit", type=int, default=0, help="Limitar quantidade de contratações processadas")
    args = ap.parse_args()

    hoje = datetime.now().date()
    data_final = parse_date(args.fim) if args.fim else hoje
    data_inicial = parse_date(args.inicio) if args.inicio else (hoje - timedelta(days=30))

    print(f"Período: {data_inicial} .. {data_final}")
    print(f"Filtros: modalidade='{args.modalidade}' situacao='{args.situacao}' keyword='{args.keyword}' ano={args.ano or 'auto'}")

    list_scraper = PncpApiScraper()
    doc_scraper = PncpDocumentosScraper()
    db = DatabaseManager()

    contratacoes = list_scraper.buscar(
        palavra_chave=args.keyword,
        data_inicial=data_inicial,
        data_final=data_final,
        modalidade=(args.modalidade or ""),
        situacao=(args.situacao or ""),
        ano_override=(args.ano if args.ano > 0 else None),
    )
    total = len(contratacoes)
    print(f"Contratações retornadas: {total}")
    if total == 0:
        return 0

    to_process = contratacoes if args.limit <= 0 else contratacoes[:args.limit]
    total_docs = 0
    processed = 0
    for lic in to_process:
        processed += 1
        meta = lic.get("pncp_meta") or {}
        numero = meta.get("numeroControlePNCP")
        print(f"[{processed}/{len(to_process)}] numeroControlePNCP={numero} ...", flush=True)
        try:
            docs = doc_scraper.buscar_documentos(meta, base_export_dir="export")
        except Exception as e:
            print(f"  ! Erro ao buscar documentos: {e}")
            docs = []
        print(f"  - documentos encontrados: {len(docs)}")
        for d in docs:
            if db.insert_documento(d):
                total_docs += 1
    print(f"Total de documentos inseridos/atualizados: {total_docs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


