import argparse
from scrapers.pncp_to_comprasnet import extract_trio_from_pncp
from scrapers.comprasnet_edital_downloader import baixar_e_registrar


def main():
    ap = argparse.ArgumentParser(description="Extrai (coduasg,numprp,modprp) do PNCP e baixa edital via Comprasnet.")
    ap.add_argument("--numero", required=True, help="numeroControlePNCP (ex: 83102269000106-1-000163/2025)")
    args = ap.parse_args()

    trio = extract_trio_from_pncp(args.numero)
    if not trio:
        print("FAIL: trio não encontrado a partir do PNCP")
        return 2
    c, n, m = trio
    print(f"Trio extraído: coduasg={c}, numprp={n}, modprp={m}")
    ok = baixar_e_registrar(c, n, m)
    print("OK" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())



