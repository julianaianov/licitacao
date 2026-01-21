import argparse
import os
import re
import requests
from database.db_manager import DatabaseManager


def infer_numero_from_url(url: str) -> str:
    """
    Tenta inferir numeroControlePNCP a partir do padrão:
    .../orgaos/{cnpj}/compras/{ano}/{seq}/arquivos/{id}
    """
    m = re.search(r"/orgaos/(\d{14})/compras/(\d{4})/(\d+)/arquivos/", url)
    if not m:
        return "desconhecido"
    cnpj, ano, seq = m.group(1), m.group(2), m.group(3)
    # número controle PNCP costuma ter '-1-' entre a raiz e o sequencial (modo de disputa),
    # aqui usamos '-1-' como padrão.
    return f"{cnpj}-1-{int(seq):06d}/{ano}"


def main():
    ap = argparse.ArgumentParser(description="Baixa um PDF direto da API do PNCP e registra no banco.")
    ap.add_argument("--url", required=True, help="URL direta do arquivo na API PNCP")
    ap.add_argument("--numero", required=False, help="numeroControlePNCP (opcional; tenta inferir do URL)")
    args = ap.parse_args()

    url = args.url.strip()
    numero = (args.numero or "").strip() or infer_numero_from_url(url)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    })

    r = s.get(url, stream=True, timeout=90)
    r.raise_for_status()
    ctype = (r.headers.get("Content-Type") or "").lower()
    if "pdf" not in ctype and "octet-stream" not in ctype:
        print(f"Content-Type inesperado: {ctype}")
        return 2

    # Derivar caminho
    out_dir = os.path.join("export", "editais", "PNCP_API")
    # Se conseguirmos inferir cnpj/ano/seq do URL, organizar em pastas
    m = re.search(r"/orgaos/(\d{14})/compras/(\d{4})/(\d+)/arquivos/", url)
    if m:
        cnpj, ano, seq = m.group(1), m.group(2), m.group(3)
        out_dir = os.path.join(out_dir, cnpj, ano, seq)
    os.makedirs(out_dir, exist_ok=True)

    # Nome do arquivo
    fname = "documento.pdf"
    cd = r.headers.get("Content-Disposition") or ""
    if "filename=" in cd:
        try:
            fname = cd.split("filename=")[1].strip().strip('"').strip("'")
        except Exception:
            pass
    path = os.path.join(out_dir, os.path.basename(fname) or "documento.pdf")

    # Salvar binário
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            if chunk:
                f.write(chunk)

    db = DatabaseManager()
    meta = {
        "portal": "PNCP API",
        "numero_controle": numero,
        "id_compra": None,
        "ano_compra": None,
        "sequencial_compra": None,
        "tipo_documento": "DOCUMENTO",
        "nome_arquivo": os.path.basename(path),
        "url": url,
        "caminho_local": path,
        "tamanho_bytes": os.path.getsize(path),
        "sha256": None,
        "data_publicacao": None,
    }
    ok = db.insert_documento(meta)
    print("OK" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())


