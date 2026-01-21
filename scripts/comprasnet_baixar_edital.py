import argparse
from scrapers.comprasnet_edital_downloader import baixar_e_registrar


def main():
    ap = argparse.ArgumentParser(description="Baixa edital do Comprasnet por coduasg/numprp/modprp (ASP público).")
    ap.add_argument("--coduasg", required=True)
    ap.add_argument("--numprp", required=True)
    ap.add_argument("--modprp", required=True)
    args = ap.parse_args()
    ok = baixar_e_registrar(args.coduasg, args.numprp, args.modprp)
    print("OK" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())



