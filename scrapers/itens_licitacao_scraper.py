from datetime import datetime
from typing import List, Dict, Optional
import time

from scrapers.ckan_client import CKANClient


class ItensLicitacaoScraper:
    """Extrai itens de licitação via CKAN (dataset: itens_licitacao)."""
    def __init__(self):
        self.client = CKANClient()
        self.page_size = 200
        self.max_pages = 10
        self.dataset_id = "itens_licitacao"
    
    def _format_date(self, d) -> Optional[str]:
        if not d:
            return None
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        try:
            return datetime.combine(d, datetime.min.time()).strftime("%Y-%m-%d")
        except Exception:
            return None
    
    def _norm(self, rec: Dict, palavra_chave: Optional[str]) -> Dict:
        def parse_float(v):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).replace(".", "").replace(",", "."))
            except Exception:
                return None
        
        def parse_dt(v):
            if not v:
                return None
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
                try:
                    return datetime.strptime(str(v)[:19], fmt)
                except Exception:
                    continue
            return None
        
        return {
            "id_licitacao": str(rec.get("id_licitacao") or rec.get("identificador") or rec.get("id") or ""),
            "numero_item": str(rec.get("numero_item") or rec.get("item") or ""),
            "descricao": rec.get("descricao") or rec.get("objeto") or "",
            "unidade": rec.get("unidade") or rec.get("unidade_fornecimento") or "",
            "quantidade": parse_float(rec.get("quantidade")),
            "valor_unitario": parse_float(rec.get("valor_unitario")),
            "valor_total": parse_float(rec.get("valor_total")),
            "data_publicacao": parse_dt(rec.get("data_publicacao") or rec.get("data")),
            "portal": "Comprasnet",
        }
    
    def buscar(self, palavra_chave: str, data_inicial, data_final) -> List[Dict]:
        rid = self.client.get_datastore_resource_id(self.dataset_id)
        if not rid:
            return []
        
        kw = (palavra_chave or "").strip()
        dmin = self._format_date(data_inicial)
        dmax = self._format_date(data_final)
        
        where = []
        if kw:
            where.append("\"descricao\" ILIKE '%{}%'".format(kw.replace("'", "''")))
        if dmin and dmax:
            where.append(f"\"data_publicacao\" BETWEEN '{dmin}' AND '{dmax}'")
        elif dmin:
            where.append(f"\"data_publicacao\" >= '{dmin}'")
        elif dmax:
            where.append(f"\"data_publicacao\" <= '{dmax}'")
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        
        resultados: List[Dict] = []
        for page in range(self.max_pages):
            offset = page * self.page_size
            sql = f'SELECT * FROM "{rid}"{where_sql} ORDER BY "data_publicacao" DESC NULLS LAST LIMIT {self.page_size} OFFSET {offset}'
            try:
                rows = self.client.datastore_search_sql(rid, sql)
            except Exception:
                rows = []
            if not rows:
                break
            for r in rows:
                try:
                    resultados.append(self._norm(r, kw))
                except Exception:
                    continue
            if len(rows) < self.page_size:
                break
            time.sleep(0.2)
        return resultados







