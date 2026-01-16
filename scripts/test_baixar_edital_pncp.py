import sys
import argparse
from datetime import datetime, timedelta

from scrapers.pncp_14133_scraper import Pncp14133Scraper
from scrapers.pncp_documentos_scraper import PncpDocumentosScraper
from database.db_manager import DatabaseManager


def status_parece_aberto(nome: str) -> bool:
    if not nome:
        return False
    s = nome.lower()
    if "publicad" in s or "abert" in s or "andament" in s or "divulgad" in s:
        if "encerr" in s or "homolog" in s or "cancel" in s or "suspens" in s:
            return False
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description="Teste: baixar edital PNCP aberto")
    ap.add_argument("--days", type=int, default=30, help="Janela de dias atrás para buscar (default: 30)")
    ap.add_argument("--keyword", type=str, default="", help="Palavra-chave opcional para filtrar")
    args = ap.parse_args()

    data_final = datetime.now().date()
    data_inicial = data_final - timedelta(days=args.days)

    print(f"Buscando PNCP {data_inicial}..{data_final} keyword='{args.keyword}'")
    lic_scraper = Pncp14133Scraper()
    docs_scraper = PncpDocumentosScraper()
    db = DatabaseManager()

    resultados = lic_scraper.buscar(args.keyword, data_inicial, data_final)
    print(f"Total de contratações retornadas: {len(resultados)}")
    candidato = None
    for lic in resultados:
        if status_parece_aberto(lic.get("status") or ""):
            candidato = lic
            break
    if not candidato:
        candidato = resultados[0] if resultados else None
    if not candidato:
        print("Nenhuma contratação encontrada para teste.")
        return 1

    meta = candidato.get("pncp_meta") or {}
    print(f"Candidato PNCP: numero={candidato.get('numero')} status={candidato.get('status')} meta={meta}")

    docs = docs_scraper.buscar_documentos(meta, base_export_dir="export")
    print(f"Documentos encontrados: {len(docs)}")
    inseridos = 0
    for d in docs:
        if db.insert_documento(d):
            inseridos += 1
    print(f"Documentos inseridos/atualizados no banco: {inseridos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


