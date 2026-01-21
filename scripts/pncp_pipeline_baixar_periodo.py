import argparse
from datetime import datetime, timedelta
from scrapers.pncp_pipeline import processar_periodo


def parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser(description="Baixa documentos via PNCP Pipeline por período.")
    ap.add_argument("--inicio", required=False, help="YYYY-MM-DD (default: hoje-7d)")
    ap.add_argument("--fim", required=False, help="YYYY-MM-DD (default: hoje)")
    ap.add_argument("--limit", type=int, default=50, help="máximo de contratações a processar (default: 50)")
    args = ap.parse_args()

    hoje = datetime.now().date()
    fim = parse_date(args.fim) if args.fim else hoje
    inicio = parse_date(args.inicio) if args.inicio else (hoje - timedelta(days=7))

    inserted = processar_periodo(inicio, fim, limit=args.limit)
    print(f"Documentos inseridos: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


