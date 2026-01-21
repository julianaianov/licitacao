import requests
from typing import List, Dict, Optional, Union
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class ModuloFornecedorScraper:
    """
    Consulta fornecedores no módulo-fornecedor:
      GET https://dadosabertos.compras.gov.br/modulo-fornecedor/1_consultarFornecedor
    Parâmetros aceitos:
      - ativo (bool) [obrigatório]
      - cnpj (str) [opcional]
      - cpf (str) [opcional]
      - naturezaJuridicaId (int) [opcional]
      - porteEmpresaId (int) [opcional]
      - codigoCnae (int) [opcional]
      - pagina / tamanhoPagina (pagina por padrão 1; tamanho por padrão 100)
    Observação: A tabela `fornecedores` exige CNPJ; registros apenas com CPF serão ignorados.
    """
    def __init__(self):
        self.base_url = "https://dadosabertos.compras.gov.br/modulo-fornecedor/1_consultarFornecedor"
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
        self.max_pages = 20

    def _norm(self, rec: Dict) -> Optional[Dict]:
        cnpj = (rec.get("cnpj") or "").strip()
        if not cnpj:
            return None
        return {
            "cnpj": cnpj,
            "razao_social": rec.get("nomeRazaoSocialFornecedor") or "",
            "tipo": rec.get("naturezaJuridicaNome") or "",
            "porte": rec.get("porteEmpresaNome") or "",
            "uf": (rec.get("ufSigla") or "")[:2],
            "municipio": rec.get("nomeMunicipio") or "",
            "atualizado_em": datetime.now(),
        }

    def buscar(
        self,
        ativo: bool,
        cnpj: Optional[str] = None,
        cpf: Optional[str] = None,
        naturezaJuridicaId: Optional[Union[int, str]] = None,
        porteEmpresaId: Optional[Union[int, str]] = None,
        codigoCnae: Optional[Union[int, str]] = None,
    ) -> List[Dict]:
        resultados: List[Dict] = []
        pagina = 1
        pages_fetched = 0
        while pages_fetched < self.max_pages:
            params: Dict[str, Union[str, int, bool]] = {
                "pagina": pagina,
                "tamanhoPagina": self.page_size,
                "ativo": ativo,
            }
            if cnpj:
                params["cnpj"] = cnpj
            if cpf:
                params["cpf"] = cpf
            if naturezaJuridicaId is not None and str(naturezaJuridicaId).strip():
                params["naturezaJuridicaId"] = int(naturezaJuridicaId)
            if porteEmpresaId is not None and str(porteEmpresaId).strip():
                params["porteEmpresaId"] = int(porteEmpresaId)
            if codigoCnae is not None and str(codigoCnae).strip():
                params["codigoCnae"] = int(codigoCnae)
            try:
                resp = self.session.get(self.base_url, params=params, timeout=60)
                resp.raise_for_status()
                j = resp.json()
            except Exception as e:
                print(f"Erro módulo-fornecedor (página {pagina}): {e}")
                break
            rows = j.get("resultado") or []
            if not rows:
                break
            for r in rows:
                item = self._norm(r)
                if item:
                    resultados.append(item)
            pages_fetched += 1
            pagina += 1
            # Parar cedo se não há mais páginas ou veio menos que page_size
            if isinstance(j.get("paginasRestantes"), int) and j["paginasRestantes"] <= 0:
                break
            if len(rows) < self.page_size:
                break
        return resultados














