import requests
from typing import List, Dict, Optional
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class LicitacaoIdScraper:
    """
    Consulta detalhes de uma licitação por id_compra no módulo legado:
      GET https://dadosabertos.compras.gov.br/modulo-legado/1.1_consultarLicitacao_Id
    Parâmetros:
      - id_compra (obrigatório)
      - dt_alteracao (opcional)
    """
    def __init__(self):
        self.base_url = "https://dadosabertos.compras.gov.br/modulo-legado/1.1_consultarLicitacao_Id"
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

    def _parse_dt(self, val: Optional[str]) -> Optional[datetime]:
        if not val:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(val[:19], fmt)
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

    def _map_licitacao(self, rec: Dict, palavra_chave: Optional[str]) -> Dict:
        numero = rec.get("numero_aviso") or rec.get("numero") or rec.get("identificador") or rec.get("id_compra") or ""
        orgao = rec.get("orgao") or rec.get("uasg") or rec.get("nome_orgao") or ""
        modalidade = rec.get("nome_modalidade") or rec.get("modalidade") or ""
        descricao = rec.get("objeto") or rec.get("informacoes_gerais") or rec.get("descricao") or ""
        titulo = rec.get("titulo") or (descricao[:120] if descricao else f"Licitacao {numero}")
        status = rec.get("situacao_aviso") or rec.get("status") or ""
        link = rec.get("link") or ""

        data_pub = self._parse_dt(rec.get("data_publicacao") or rec.get("data"))
        data_abertura = self._parse_dt(rec.get("data_abertura_proposta") or rec.get("abertura"))

        valor_estimado = self._parse_float(rec.get("valor_estimado_total") or rec.get("valor_estimado"))

        return {
            "numero": str(numero),
            "titulo": titulo,
            "orgao": str(orgao),
            "portal": "Comprasnet",
            "modalidade": str(modalidade),
            "data_publicacao": data_pub or datetime.now(),
            "data_abertura": data_abertura or data_pub or datetime.now(),
            "valor_estimado": valor_estimado or 0.0,
            "status": str(status) or "Indefinido",
            "descricao": descricao or titulo,
            "link_edital": link,
            "palavra_chave": palavra_chave or "",
        }

    def buscar(self, id_compra: str, palavra_chave: Optional[str] = None, dt_alteracao: Optional[str] = None) -> List[Dict]:
        params = {"id_compra": id_compra}
        if dt_alteracao:
            params["dt_alteracao"] = dt_alteracao
        try:
            resp = self.session.get(self.base_url, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("resultado") or []
            resultados: List[Dict] = []
            for rec in rows:
                try:
                    resultados.append(self._map_licitacao(rec, palavra_chave))
                except Exception:
                    continue
            return resultados
        except Exception as e:
            print(f"Erro ao consultar licitação por ID (legado): {e}")
            return []






