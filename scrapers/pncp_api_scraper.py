import requests
from typing import List, Dict, Optional
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class PncpApiScraper:
    """
    Lista contratações via PNCP API oficial:
      GET https://pncp.gov.br/pncp/api/v1/contratacoes
    Filtros principais: modalidade=PREGAO_ELETRONICO, situacao=PUBLICADA, ano=YYYY, pagina, tamanhoPagina.
    Retorna registros normalizados compatíveis com a tabela licitacoes e inclui pncp_meta.
    """
    def __init__(self):
        self.base = "https://pncp.gov.br/pncp/api/v1/contratacoes"
        self.session = requests.Session()
        self.session.headers.update({
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
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.page_size = 50
        self.max_pages = 20

    def _fmt_date(self, d) -> Optional[str]:
        if not d:
            return None
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        try:
            return datetime.combine(d, datetime.min.time()).strftime("%Y-%m-%d")
        except Exception:
            return None

    def _parse_dt(self, v):
        if not v:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                return datetime.strptime(str(v)[:26], fmt)
            except Exception:
                continue
        return None

    def _norm(self, rec: Dict, palavra_chave: Optional[str]) -> Dict:
        numero = rec.get("numeroControlePNCP") or rec.get("numero") or ""
        modalidade = rec.get("modalidade") or ""
        situacao = rec.get("situacao") or ""
        objeto = rec.get("objeto") or ""
        orgao_nome = (rec.get("orgao") or {}).get("nome") if isinstance(rec.get("orgao"), dict) else (rec.get("orgao") or "")
        ano = rec.get("ano")
        sequencial = rec.get("sequencial")

        return {
            "numero": str(numero),
            "titulo": (objeto[:500] if isinstance(objeto, str) else "Compra PNCP"),
            "orgao": orgao_nome or "",
            "portal": "PNCP 14133",
            "modalidade": str(modalidade),
            "data_publicacao": None,
            "data_abertura": None,
            "valor_estimado": 0.0,
            "status": str(situacao) or "Indefinido",
            "descricao": objeto or "",
            "link_edital": "",
            "palavra_chave": palavra_chave or "",
            "pncp_meta": {
                "numeroControlePNCP": rec.get("numeroControlePNCP"),
                "anoCompraPncp": ano,
                "sequencialCompraPncp": sequencial,
                "idCompra": rec.get("id"),  # se existir
            }
        }

    def buscar(self, palavra_chave: str, data_inicial, data_final,
               modalidade: str = "PREGAO_ELETRONICO",
               situacao: str = "PUBLICADA",
               ano_override: Optional[int] = None) -> List[Dict]:
        resultados: List[Dict] = []
        # Preparar variantes de base e parâmetros
        ano = (ano_override if ano_override else (data_final.year if hasattr(data_final, "year") else datetime.now().year))
        dmin = self._fmt_date(data_inicial)
        dmax = self._fmt_date(data_final)
        bases = [
            "https://pncp.gov.br/pncp/api/v1/contratacoes",
            "https://pncp.gov.br/api/pncp/v1/contratacoes",
            "https://pncp.gov.br/pncp-api/v1/contratacoes",
        ]
        # Variantes de chaves de data
        date_variants = [
            ("dataPublicacaoPncpInicial", "dataPublicacaoPncpFinal"),
            ("dataPublicacaoInicial", "dataPublicacaoFinal"),
        ]
        found_any = False
        for base in bases:
            for date_keys in date_variants:
                for page in range(1, self.max_pages + 1):
                    params = {
                        "pagina": page,
                        "tamanhoPagina": self.page_size
                    }
                    # Filtros opcionais
                    if modalidade:
                        params["modalidade"] = modalidade
                    if situacao:
                        params["situacao"] = situacao
                    # Se temos datas, NÃO enviar ano; se não temos, enviar ano (quando existir)
                    if dmin and dmax:
                        params[date_keys[0]] = dmin
                        params[date_keys[1]] = dmax
                    elif ano:
                        params["ano"] = ano
                    if palavra_chave:
                        params["objeto"] = palavra_chave
                    try:
                        r = self.session.get(base, params=params, timeout=60)
                        r.raise_for_status()
                        j = r.json()
                    except Exception:
                        break
                    if isinstance(j, list):
                        rows = j
                    elif isinstance(j, dict):
                        rows = (j.get("content") or j.get("items") or j.get("resultado")
                                or j.get("contratacoes") or j.get("dados") or j.get("data") or [])
                    else:
                        rows = []
                    if not isinstance(rows, list) or not rows:
                        # se nada nessa página, parar este loop de páginas e tentar próxima variante
                        break
                    found_any = True
                    for rec in rows:
                        try:
                            resultados.append(self._norm(rec, palavra_chave))
                        except Exception:
                            continue
                    if len(rows) < self.page_size:
                        break
                if found_any:
                    break
            if found_any:
                break
        return resultados


