import requests
from typing import List, Dict, Optional
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class ItensPregoesIdScraper:
    """
    Consulta itens de pregões por ID no módulo legado (4.1_consultarItensPregoes_ID).
    Parâmetros:
      - id_compra (obrigatório)
      - id_compra_item (opcional)
      - dt_alteracao (opcional)
    Endpoint:
      https://dadosabertos.compras.gov.br/modulo-legado/4.1_consultarItensPregoes_ID
    """
    def __init__(self):
        self.base_url = "https://dadosabertos.compras.gov.br/modulo-legado/4.1_consultarItensPregoes_ID"
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

    def _parse_float(self, v) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).replace(".", "").replace(",", "."))
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

    def _normalize(self, rec: Dict) -> Dict:
        """
        Converte o registro do endpoint para o schema de itens_licitacao.
        Observação: usamos id_compra como id_licitacao (não há FK real).
        """
        # Seleciona melhor valor unitário disponível
        valor_unitario = self._parse_float(rec.get("menor_lance")) \
            or self._parse_float(rec.get("valor_estimado_item"))
        valor_total = self._parse_float(rec.get("valorHomologadoItem")) \
            or self._parse_float(rec.get("valor_negociado"))

        descricao = rec.get("descricao_item") or ""
        desc_det = rec.get("descricao_detalhada_item") or ""
        descricao_final = (descricao + (" - " + desc_det if desc_det else ""))[:1000]

        return {
            "id_licitacao": str(rec.get("id_compra") or ""),
            "numero_item": str(rec.get("id_compra_item") or ""),
            "descricao": descricao_final,
            "unidade": rec.get("unidade_fornecimento") or "",
            "quantidade": self._parse_float(rec.get("quantidade_item")),
            "valor_unitario": valor_unitario,
            "valor_total": valor_total,
            "data_publicacao": self._parse_dt(rec.get("dt_alteracao") or rec.get("dt_hom") or rec.get("dt_adjudic")),
            "portal": "Comprasnet",
        }

    def buscar(self, id_compra: str, id_compra_item: Optional[str] = None, dt_alteracao: Optional[str] = None) -> List[Dict]:
        params: Dict[str, str] = {"id_compra": id_compra}
        if id_compra_item:
            params["id_compra_item"] = id_compra_item
        if dt_alteracao:
            params["dt_alteracao"] = dt_alteracao
        try:
            resp = self.session.get(self.base_url, params=params, timeout=60)
            resp.raise_for_status()
            j = resp.json()
            rows = j.get("resultado") or []
            resultados: List[Dict] = []
            for r in rows:
                try:
                    resultados.append(self._normalize(r))
                except Exception:
                    continue
            return resultados
        except Exception as e:
            print(f"Erro ao consultar Itens Pregões por ID: {e}")
            return []














