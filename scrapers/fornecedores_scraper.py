from datetime import datetime
from typing import List, Dict, Optional
import time

from scrapers.ckan_client import CKANClient


class FornecedoresScraper:
    """Extrai fornecedores via CKAN (dataset: fornecedores)."""
    def __init__(self):
        self.client = CKANClient()
        self.page_size = 200
        self.max_pages = 5
        self.dataset_id = "fornecedores"
    
    def _format_date(self, d) -> Optional[str]:
        if not d:
            return None
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        try:
            return datetime.combine(d, datetime.min.time()).strftime("%Y-%m-%d")
        except Exception:
            return None
    
    def _norm(self, rec: Dict) -> Dict:
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
            "cnpj": str(rec.get("cnpj") or ""),
            "razao_social": rec.get("razao_social") or rec.get("nome") or "",
            "tipo": rec.get("tipo") or rec.get("natureza_juridica") or "",
            "porte": rec.get("porte") or "",
            "uf": (rec.get("uf") or "")[:2],
            "municipio": rec.get("municipio") or rec.get("cidade") or "",
            "atualizado_em": parse_dt(rec.get("atualizado_em") or rec.get("data_atualizacao")),
        }
    
    def buscar(self, palavra_chave: str, data_inicial, data_final) -> List[Dict]:
        rid = self.client.get_datastore_resource_id(self.dataset_id)
        if not rid:
            return []
        
        kw = (palavra_chave or "").strip()
        dmin = self._format_date(data_inicial)
        dmax = self._format_date(data_final)
        
        # Evitar varreduras gigantes: filtramos por razão social contendo a keyword
        where = []
        if kw:
            where.append("\"razao_social\" ILIKE '%{}%'".format(kw.replace("'", "''")))
        if dmin and dmax:
            where.append(f"\"atualizado_em\" BETWEEN '{dmin}' AND '{dmax}'")
        elif dmin:
            where.append(f"\"atualizado_em\" >= '{dmin}'")
        elif dmax:
            where.append(f"\"atualizado_em\" <= '{dmax}'")
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        
        resultados: List[Dict] = []
        for page in range(self.max_pages):
            offset = page * self.page_size
            sql = f'SELECT * FROM "{rid}"{where_sql} ORDER BY "atualizado_em" DESC NULLS LAST LIMIT {self.page_size} OFFSET {offset}'
            try:
                rows = self.client.datastore_search_sql(rid, sql)
            except Exception:
                rows = []
            if not rows:
                break
            for r in rows:
                try:
                    resultados.append(self._norm(r))
                except Exception:
                    continue
            if len(rows) < self.page_size:
                break
            time.sleep(0.2)
        return resultados


