import requests
from datetime import datetime
from typing import List, Dict, Optional
import time
import urllib.parse
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

class ComprasnetScraper:
    """Scraper usando APIs públicas (CKAN e endpoint REST modulo-legado) sem scraping de HTML."""
    
    def __init__(self):
        # Bases da API CKAN
        self.ckan_base = "https://compras.dados.gov.br/api/3/action"
        # Endpoint REST legado (documentado)
        self.legado_base = "https://dadosabertos.compras.gov.br/modulo-legado/1_consultarLicitacao"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; LicitacoesBot/1.0; +https://example.com/bot)',
            'Accept': 'application/json'
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
        # Paginação
        self.page_size = 100
        self.max_pages = 10
        self.only_open_default = False
    
    def _format_date(self, d: Optional[datetime]) -> Optional[str]:
        if not d:
            return None
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        try:
            return datetime.combine(d, datetime.min.time()).strftime("%Y-%m-%d")
        except Exception:
            return None
    
    def _get_licitacoes_resource(self) -> Dict:
        """Obtém metadados do dataset 'licitacoes' e escolhe o melhor recurso (DataStore se houver)."""
        url = f"{self.ckan_base}/package_show"
        try:
            resp = self.session.get(url, params={"id": "licitacoes"}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return {}
            pkg = data.get("result") or {}
            resources = pkg.get("resources") or []
            # Preferir DataStore ativo
            for r in resources:
                if r.get("datastore_active"):
                    return {"type": "datastore", "resource": r}
            # Senão, preferir JSON/CSV
            for fmt in ("JSON", "CSV"):
                for r in resources:
                    if (r.get("format") or "").upper() == fmt:
                        return {"type": fmt.lower(), "resource": r}
        except Exception as e:
            print(f"Erro ao obter recurso CKAN: {e}")
        return {}
    
    def _normalize_record(self, raw: Dict, palavra_chave: Optional[str]) -> Dict:
        """Mapeia um registro genérico para o schema interno do app."""
        identificador = raw.get("identificador") or raw.get("id_licitacao") or raw.get("_id") or raw.get("id") or ""
        numero = raw.get("numero_aviso") or raw.get("numero") or identificador or ""
        orgao = raw.get("orgao") or raw.get("uasg") or raw.get("nome_orgao") or ""
        modalidade = raw.get("modalidade_licitacao") or raw.get("modalidade") or ""
        descricao = raw.get("objeto") or raw.get("descricao") or ""
        titulo = raw.get("titulo") or (descricao[:120] if descricao else f"Licitacao {numero}")
        status = raw.get("situacao_licitacao") or raw.get("status") or ""
        link = raw.get("link") or raw.get("url") or raw.get("_links", {}).get("self", {}).get("href") or ""
        
        def parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(val[:19], fmt)
                except Exception:
                    continue
            return None
        
        data_pub = parse_dt(raw.get("data_publicacao") or raw.get("data_publicacao_portal") or raw.get("data"))
        data_abertura = parse_dt(raw.get("data_abertura") or raw.get("abertura") or raw.get("data_sessao_publica"))
        
        # Valor estimado (nem sempre disponível)
        valor_estimado = None
        for key in ("valor_estimado", "valor_total_estimado", "valor_total"):
            v = raw.get(key)
            if isinstance(v, (int, float)):
                valor_estimado = float(v)
                break
            if isinstance(v, str):
                try:
                    valor_estimado = float(v.replace(".", "").replace(",", "."))
                    break
                except Exception:
                    pass
        
        return {
            'numero': str(numero) if numero else str(identificador),
            'titulo': titulo,
            'orgao': str(orgao),
            'portal': 'Comprasnet',
            'modalidade': str(modalidade),
            'data_publicacao': data_pub or datetime.now(),
            'data_abertura': data_abertura or data_pub or datetime.now(),
            'valor_estimado': valor_estimado or 0.0,
            'status': str(status) or 'Indefinido',
            'descricao': descricao or titulo,
            'link_edital': link,
            'palavra_chave': palavra_chave or ''
        }
    
    def _query_datastore_sql(self, resource_id: str, palavra_chave: Optional[str], data_min: Optional[str], data_max: Optional[str], offset: int, limit: int) -> List[Dict]:
        """
        Usa datastore_search_sql com filtro de data e palavra-chave no 'objeto' (quando disponível).
        """
        where_parts = []
        params: List[str] = []
        # Filtro por palavra-chave (objeto) - best effort
        if palavra_chave:
            where_parts.append('"objeto" ILIKE %s')
            params.append(f"%{palavra_chave}%")
        # Filtro de período por data_publicacao (se existir)
        if data_min and data_max:
            where_parts.append('"data_publicacao" BETWEEN %s AND %s')
            params.extend([data_min, data_max])
        elif data_min:
            where_parts.append('"data_publicacao" >= %s')
            params.append(data_min)
        elif data_max:
            where_parts.append('"data_publicacao" <= %s')
            params.append(data_max)
        
        where_sql = ""
        if where_parts:
            # CKAN SQL não aceita bind parameters no GET; interpolamos com segurança mínima
            # Aspas simples escapadas
            def esc(v: str) -> str:
                return v.replace("'", "''")
            tmp = []
            pi = 0
            for part in where_parts:
                if "%s" in part:
                    count = part.count("%s")
                    vals = params[pi:pi+count]
                    pi += count
                    for val in vals:
                        part = part.replace("%s", f"'{esc(val)}'", 1)
                tmp.append(part)
            where_sql = " WHERE " + " AND ".join(tmp)
        
        sql = f'SELECT * FROM "{resource_id}"{where_sql} ORDER BY "data_publicacao" DESC NULLS LAST LIMIT {limit} OFFSET {offset}'
        url = f"{self.ckan_base}/datastore_search_sql"
        try:
            resp = self.session.get(url, params={"sql": sql}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if data.get("success") and isinstance(data.get("result", {}).get("records"), list):
                return data["result"]["records"]
        except Exception as e:
            print(f"Erro no datastore_search_sql: {e}")
        return []
    
    def _map_legado(self, rec: Dict, palavra_chave: Optional[str]) -> Dict:
        """Mapeia um registro do endpoint modulo-legado para o schema interno."""
        def parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(val[:19], fmt)
                except Exception:
                    continue
            return None
        return {
            'numero': str(rec.get('numero_aviso') or rec.get('identificador') or rec.get('id_compra') or ''),
            'titulo': (rec.get('objeto') or rec.get('informacoes_gerais') or 'Licitação')[:500],
            'orgao': str(rec.get('uasg') or ''),
            'portal': 'Comprasnet',
            'modalidade': str(rec.get('nome_modalidade') or rec.get('modalidade') or ''),
            'data_publicacao': parse_dt(rec.get('data_publicacao')),
            'data_abertura': parse_dt(rec.get('data_abertura_proposta')),
            'valor_estimado': float(rec.get('valor_estimado_total') or 0) if isinstance(rec.get('valor_estimado_total'), (int, float)) else 0.0,
            'status': str(rec.get('situacao_aviso') or ''),
            'descricao': rec.get('objeto') or rec.get('informacoes_gerais') or '',
            'link_edital': '',  # o endpoint não fornece link direto
            'palavra_chave': palavra_chave or ''
        }
    
    def _buscar_via_legado(self, palavra_chave: str, data_inicial, data_final, somente_abertas: bool) -> List[Dict]:
        """Usa o endpoint REST modulo-legado com paginação."""
        resultados: List[Dict] = []
        # Datas YYYY-MM-DD
        di = self._format_date(data_inicial)
        df = self._format_date(data_final)
        if not di or not df:
            return resultados
        # Garantir janela <= 365 dias (API limita)
        try:
            d1 = datetime.strptime(di, "%Y-%m-%d")
            d2 = datetime.strptime(df, "%Y-%m-%d")
            if (d2 - d1).days > 365:
                d1 = d2.replace(year=d2.year - 1)
                di = d1.strftime("%Y-%m-%d")
        except Exception:
            pass
        # Páginas
        pagina = 1
        tamanho = max(10, min(self.page_size, 100))  # intervalo aceito 10..500
        pages_fetched = 0
        # Tentar com pertence14133 True, False e sem parâmetro (maximiza cobertura)
        for flag in (True, False, None):
            pagina = 1
            pages_fetched = 0
            while pages_fetched < self.max_pages:
                params = {
                    'pagina': pagina,
                    'tamanhoPagina': tamanho,
                    'data_publicacao_inicial': di,
                    'data_publicacao_final': df
                }
                if flag is True:
                    params['pertence14133'] = 'true'
                elif flag is False:
                    params['pertence14133'] = 'false'
                try:
                    r = self.session.get(self.legado_base, params=params, timeout=60)
                    r.raise_for_status()
                    j = r.json()
                except Exception as e:
                    print(f"Erro modulo-legado: {e}")
                    break
                items = j.get('resultado') or []
                if not isinstance(items, list) or not items:
                    break
                for rec in items:
                    # Filtro de 'abertas' e palavra-chave (client-side)
                    situacao = (rec.get('situacao_aviso') or '').lower()
                    if somente_abertas and not ('abert' in situacao):
                        continue
                    if palavra_chave:
                        obj = (rec.get('objeto') or '') + ' ' + (rec.get('informacoes_gerais') or '')
                        if palavra_chave.lower() not in obj.lower():
                            continue
                    try:
                        resultados.append(self._map_legado(rec, palavra_chave))
                    except Exception:
                        continue
                pages_fetched += 1
                pagina += 1
                # Se a API retornar páginasRestantes, podemos parar cedo
                if isinstance(j.get('paginasRestantes'), int) and j['paginasRestantes'] <= 0:
                    break
                if len(items) < tamanho:
                    break
                time.sleep(0.2)
        return resultados
    
    def buscar(self, palavra_chave: str, data_inicial, data_final, somente_abertas: Optional[bool] = None) -> List[Dict]:
        """
        Busca licitações usando primeiro o endpoint REST modulo-legado.
        Se falhar, tenta CKAN (DataStore/CSV).
        """
        resultados: List[Dict] = []
        only_open = self.only_open_default if somente_abertas is None else bool(somente_abertas)
        # 1) Tentar REST modulo-legado
        try:
            leg = self._buscar_via_legado(palavra_chave, data_inicial, data_final, only_open)
            if leg:
                return leg
        except Exception as e:
            print(f"Falha na rota modulo-legado: {e}")
        # 2) Tentar CKAN
        data_min = self._format_date(data_inicial)
        data_max = self._format_date(data_final)
        kw = (palavra_chave or "").strip()
        
        meta = self._get_licitacoes_resource()
        if not meta:
            print("Não foi possível localizar recurso CKAN para 'licitacoes'.")
            return resultados
        
        rtype = meta.get("type")
        res = meta.get("resource", {})
        
        # Preferir DataStore (consultas filtradas sem baixar tudo)
        if rtype == "datastore" and res.get("id"):
            resource_id = res["id"]
            for page in range(self.max_pages):
                offset = page * self.page_size
                rows = self._query_datastore_sql(
                    resource_id=resource_id,
                    palavra_chave=kw,
                    data_min=data_min,
                    data_max=data_max,
                    offset=offset,
                    limit=self.page_size
                )
                if not rows:
                    break
                for raw in rows:
                    try:
                        resultados.append(self._normalize_record(raw, kw))
                    except Exception as e:
                        print(f"Erro ao normalizar registro: {e}")
                        continue
                if len(rows) < self.page_size:
                    break
                time.sleep(0.2)
            return resultados
        # Fallback CSV: baixar em chunks e filtrar por período/palavra (limite de segurança)
        if rtype == "csv" and res.get("url"):
            url_csv = res["url"]
            try:
                limit_rows = self.page_size * self.max_pages  # segurança
                chunks = pd.read_csv(url_csv, sep=";", dtype=str, chunksize=5000, encoding="utf-8", on_bad_lines="skip")
                count = 0
                for chunk in chunks:
                    # Normalizar colunas possíveis
                    cols = {c.lower(): c for c in chunk.columns}
                    def col(name: str) -> Optional[str]:
                        return cols.get(name)
                    # Filtros best-effort
                    if kw and col("objeto"):
                        chunk = chunk[chunk[col("objeto")].str.contains(kw, case=False, na=False)]
                    # Filtrar por data_publicacao se existir
                    if col("data_publicacao"):
                        mask = pd.Series([True] * len(chunk))
                        if data_min:
                            mask &= pd.to_datetime(chunk[col("data_publicacao")], errors="coerce").dt.date >= pd.to_datetime(data_min).date()
                        if data_max:
                            mask &= pd.to_datetime(chunk[col("data_publicacao")], errors="coerce").dt.date <= pd.to_datetime(data_max).date()
                        chunk = chunk[mask]
                    for _, row in chunk.iterrows():
                        raw = {str(k): row[k] for k in chunk.columns}
                        try:
                            resultados.append(self._normalize_record(raw, kw))
                        except Exception:
                            continue
                        count += 1
                        if count >= limit_rows:
                            break
                    if count >= limit_rows:
                        break
                return resultados
            except Exception as e:
                print(f"Falha no fallback CSV: {e}")
                return resultados
        
        # Sem DataStore e sem CSV, retorna vazio
        return resultados
