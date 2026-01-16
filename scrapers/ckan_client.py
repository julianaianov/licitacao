import requests
from typing import Dict, List, Optional
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class CKANClient:
    """
    Cliente simples para a API CKAN do compras.dados.gov.br
    - Descobre resource_id do DataStore de um dataset
    - Executa consultas via datastore_search_sql
    """
    def __init__(self, base: str = "https://compras.dados.gov.br/api/3/action", timeout: int = 90, max_retries: int = 5, backoff_factor: float = 1.2):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)",
            "Accept": "application/json",
        })
        # Retries com backoff para lidar com intermitência
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.timeout = timeout
    
    def get_datastore_resource_id(self, dataset_id: str) -> Optional[str]:
        url = f"{self.base}/package_show"
        resp = self.session.get(url, params={"id": dataset_id}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return None
        pkg = data.get("result") or {}
        for r in pkg.get("resources") or []:
            if r.get("datastore_active") and r.get("id"):
                return r["id"]
        return None
    
    def datastore_search_sql(self, resource_id: str, sql: str) -> List[Dict]:
        url = f"{self.base}/datastore_search_sql"
        resp = self.session.get(url, params={"sql": sql}, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and isinstance(data.get("result", {}).get("records"), list):
            return data["result"]["records"]
        return []

