import requests
from typing import List, Dict, Optional
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import time


class Pncp14133Scraper:
    """
    Scraper para Consultar contratações da Lei 14.133/21 (PNCP).
    Endpoint:
    https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133
    Parâmetros mínimos exigidos: dataPublicacaoPncpInicial, dataPublicacaoPncpFinal, codigoModalidade.
    Estratégia: iterar por um conjunto de modalidades comuns e paginar.
    """
    def __init__(self):
        self.base_url = "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133"
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
        self.page_size = 100
        self.max_pages_per_modality = 10
        # Modalidades conhecidas (códigos PNCP)
        # 01-CONVITE; 02-TOMADA DE PREÇOS; 03-CONCORRÊNCIA; 04-CONCORRÊNCIA INTERNACIONAL;
        # 05-PREGÃO; 06-DISPENSA; 07-INEXIGIBILIDADE; 12-CREDENCIAMENTO; 20-CONCURSO;
        # 22-TOMADA DE PREÇOS POR TÉCNICA E PREÇO; 33-CONCORRÊNCIA POR TÉCNICA E PREÇO;
        # 44-CONCORRÊNCIA INTERNACIONAL POR TÉCNICA E PREÇO; 57-CONVÊNIO
        self.modalities = [1, 2, 3, 4, 5, 6, 7, 12, 20, 22, 33, 44, 57]

    def _format_date(self, d) -> Optional[str]:
        if not d:
            return None
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        try:
            return datetime.combine(d, datetime.min.time()).strftime("%Y-%m-%d")
        except Exception:
            return None

    def _parse_dt(self, v: Optional[str]) -> Optional[datetime]:
        if not v:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                return datetime.strptime(str(v)[:26], fmt)
            except Exception:
                continue
        return None

    def _parse_float(self, v) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).replace(".", "").replace(",", "."))
        except Exception:
            return None

    def _normalize(self, rec: Dict, palavra_chave: Optional[str]) -> Dict:
        """
        Mapeia registro PNCP para o schema interno 'licitacoes'.
        """
        numero = rec.get("numeroCompra") or rec.get("numeroControlePNCP") or rec.get("idCompra") or ""
        titulo = rec.get("objetoCompra") or "Compra PNCP"
        orgao = rec.get("orgaoEntidadeRazaoSocial") or rec.get("codigoOrgao") or ""
        modalidade_nome = rec.get("modalidadeNome") or ""
        situacao = rec.get("situacaoCompraNomePncp") or ""
        valor_estimado = self._parse_float(rec.get("valorTotalEstimado"))
        data_publicacao = self._parse_dt(rec.get("dataPublicacaoPncp"))
        data_abertura = self._parse_dt(rec.get("dataAberturaPropostaPncp"))

        return {
            "numero": str(numero),
            "titulo": titulo[:500] if isinstance(titulo, str) else "Compra PNCP",
            "orgao": str(orgao),
            "portal": "PNCP 14133",
            "modalidade": str(modalidade_nome),
            "data_publicacao": data_publicacao or datetime.now(),
            "data_abertura": data_abertura or data_publicacao or datetime.now(),
            "valor_estimado": valor_estimado or 0.0,
            "status": str(situacao) or "Indefinido",
            "descricao": rec.get("informacaoComplementar") or rec.get("objetoCompra") or "",
            "link_edital": "",  # PNCP não fornece link direto neste endpoint
            "palavra_chave": palavra_chave or "",
            # Metadados PNCP úteis para buscar documentos
            "pncp_meta": {
                "idCompra": rec.get("idCompra"),
                "numeroControlePNCP": rec.get("numeroControlePNCP"),
                "anoCompraPncp": rec.get("anoCompraPncp"),
                "sequencialCompraPncp": rec.get("sequencialCompraPncp"),
                "codigoOrgao": rec.get("codigoOrgao"),
                "orgaoEntidadeCnpj": rec.get("orgaoEntidadeCnpj"),
            }
        }

    def _fetch_page(self, codigo_modalidade: int, di: str, df: str, pagina: int) -> List[Dict]:
        params = {
            "pagina": pagina,
            "tamanhoPagina": self.page_size,
            "dataPublicacaoPncpInicial": di,
            "dataPublicacaoPncpFinal": df,
            "codigoModalidade": codigo_modalidade,
            # Demais parâmetros são opcionais e omitidos por padrão
        }
        try:
            resp = self.session.get(self.base_url, params=params, timeout=60)
            resp.raise_for_status()
            j = resp.json()
            if isinstance(j.get("resultado"), list):
                return j["resultado"]
        except Exception as e:
            print(f"Erro PNCP 14133 (modalidade {codigo_modalidade}, página {pagina}): {e}")
        return []

    def buscar(self, palavra_chave: str, data_inicial, data_final) -> List[Dict]:
        """
        Coleta contratações PNCP 14.133/21 no período informado.
        Itera por modalidades conhecidas e pagina até limite por modalidade.
        Aplica filtro simples por palavra-chave no objeto/descrição (client-side).
        """
        resultados: List[Dict] = []
        di = self._format_date(data_inicial)
        df = self._format_date(data_final)
        if not di or not df:
            return resultados

        kw = (palavra_chave or "").strip().lower()

        for mod in self.modalities:
            pagina = 1
            pages_fetched = 0
            while pages_fetched < self.max_pages_per_modality:
                rows = self._fetch_page(mod, di, df, pagina)
                if not rows:
                    break
                for r in rows:
                    # Filtro por palavra-chave (best-effort)
                    if kw:
                        texto = ((r.get("objetoCompra") or "") + " " + (r.get("informacaoComplementar") or "")).lower()
                        if kw not in texto:
                            continue
                    try:
                        resultados.append(self._normalize(r, palavra_chave))
                    except Exception:
                        continue
                pages_fetched += 1
                pagina += 1
                # Heurística de parada: se veio menos que page_size, provavelmente acabou
                if len(rows) < self.page_size:
                    break
                time.sleep(0.2)

        return resultados






