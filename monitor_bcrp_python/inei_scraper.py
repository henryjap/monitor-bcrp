"""
INEI SIRTOD Scraper — Playwright headless + HTML table parsing
Extrae series estadísticas del portal INEI (JSF/PrimeFaces sin API)

Uso:
    scraper = INEIScraper()
    scraper.fetch_indicators_tree()        # obtiene catálogo de indicadores
    df = scraper.fetch_series(rowkey, ...) # descarga datos
"""
from __future__ import annotations
import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
import pandas as pd
from playwright.sync_api import sync_playwright, Page


FREQ_MAP = {
    "Anual": "1",
    "Semestral": "4",
    "Trimestral": "5",
    "Mensual": "2",
}
DEPARTAMENTOS = {
    "Amazonas": "1", "Áncash": "2", "Apurímac": "3", "Arequipa": "4",
    "Ayacucho": "5", "Cajamarca": "6", "Callao": "7", "Cusco": "8",
    "Huancavelica": "9", "Huánuco": "10", "Ica": "11", "Junín": "12",
    "La Libertad": "13", "Lambayeque": "14", "Lima": "15", "Loreto": "16",
    "Madre de Dios": "17", "Moquegua": "18", "Pasco": "19", "Piura": "20",
    "Puno": "21", "San Martín": "22", "Tacna": "23", "Tumbes": "24",
    "Ucayali": "25",
}


class INEIScraper:
    BASE_URL = "https://webapp.inei.gob.pe:8443/sirtod-series"

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self._pw = None
        self._browser = None
        self._page = None

    def _start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page(viewport={"width": 1400, "height": 900})
        self._page.goto(f"{self.BASE_URL}/", wait_until="networkidle",
                        timeout=self.timeout)

    def _stop(self):
        if self._page:
            self._page.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ----------------------------------------------------------------
    #  Árbol de indicadores
    # ----------------------------------------------------------------
    def fetch_indicators_tree(self, max_depth: int = 99) -> list[dict]:
        """Explora el árbol completo expandiendo todos los niveles."""
        self._start()
        try:
            page = self._page
            page.wait_for_timeout(1000)

            # Expandir hasta que no queden togglers colapsados
            for _ in range(max_depth):
                has_collapsed = page.evaluate("""
                    () => {
                        const togglers = document.querySelectorAll(
                            '#formIzquierda\\\\:idArbolIndicadores .ui-tree-toggler.ui-icon-triangle-1-e'
                        );
                        togglers.forEach(t => t.click());
                        return togglers.length > 0;
                    }
                """)
                if not has_collapsed:
                    break
                page.wait_for_timeout(1000)
                page.wait_for_load_state("networkidle")

            # Extraer árbol completo del DOM
            result = page.evaluate("""
                () => {
                    const TREE_ID = 'formIzquierda:idArbolIndicadores';
                    const tree = document.getElementById(TREE_ID);
                    if (!tree) return [];
                    const container = tree.querySelector('.ui-tree-container');
                    if (!container) return [];

                    const nodes = {};

                    function getNode(rk) {
                        if (!nodes[rk]) nodes[rk] = { rowkey: rk, label: '', children: [] };
                        return nodes[rk];
                    }

                    function walk(li, parentRk) {
                        const rk = li.getAttribute('data-rowkey') || '';
                        if (!rk || rk.includes('/')) return;
                        const labelEl = li.querySelector('.ui-treenode-label span');
                        const label = labelEl ? labelEl.innerText.trim() : '';
                        const n = getNode(rk);
                        n.label = label;
                        if (parentRk !== null) {
                            const parent = getNode(parentRk);
                            if (!parent.children.find(c => c.rowkey === rk)) {
                                parent.children.push(n);
                            }
                        }
                        const isParent = li.classList.contains('ui-treenode-parent');
                        if (isParent) {
                            const prefix = TREE_ID + ':' + rk + '_';
                            const children = tree.querySelectorAll('li[id^="' + prefix + '"]');
                            children.forEach(child => walk(child, rk));
                        }
                    }

                    container.querySelectorAll(':scope > li').forEach(li => walk(li, null));

                    const result = [];
                    container.querySelectorAll(':scope > li').forEach(li => {
                        const rk = li.getAttribute('data-rowkey') || '';
                        if (nodes[rk]) result.push(nodes[rk]);
                    });
                    return result;
                }
            """)
            return result
        finally:
            self._stop()

    def explore_indicators_by_frequency(self, freq: str) -> list[dict]:
        """Explora el árbol con una frecuencia específica y devuelve
        solo los nodos que tienen checkbox seleccionable.

        Retorna lista de dicts: [{"rowkey": str, "label": str}, ...]
        """
        self._start()
        try:
            page = self._page
            # 1. Cambiar frecuencia
            self._set_frequency(freq)
            page.wait_for_timeout(2000)
            page.wait_for_load_state("networkidle")

            # 2. Expandir todo el árbol BFS
            for _ in range(99):
                has_collapsed = page.evaluate("""
                    () => {
                        const togglers = document.querySelectorAll(
                            '#formIzquierda\\\\:idArbolIndicadores .ui-tree-toggler.ui-icon-triangle-1-e'
                        );
                        togglers.forEach(t => t.click());
                        return togglers.length > 0;
                    }
                """)
                if not has_collapsed:
                    break
                page.wait_for_timeout(1000)
                page.wait_for_load_state("networkidle")

            # 3. Extraer solo nodos con checkbox
            result = page.evaluate("""() => {
                const tree = document.getElementById('formIzquierda:idArbolIndicadores');
                if (!tree) return [];
                const items = tree.querySelectorAll('li[data-rowkey]');
                const seen = new Set();
                const out = [];
                items.forEach(li => {
                    const rk = li.getAttribute('data-rowkey');
                    if (!rk || rk.includes('/') || seen.has(rk)) return;
                    const cb = li.querySelector('.ui-chkbox-box');
                    if (!cb) return;
                    seen.add(rk);
                    const labelEl = li.querySelector('.ui-treenode-label span');
                    const label = labelEl ? labelEl.innerText.trim() : '';
                    out.push({rowkey: rk, label: label});
                });
                return out;
            }""")
            return result
        finally:
            self._stop()

    @staticmethod
    def get_leaves(nodes: list[dict]) -> list[dict]:
        """Extrae todas las hojas del árbol."""
        leaves = []
        for n in nodes:
            if n["children"]:
                leaves.extend(INEIScraper.get_leaves(n["children"]))
            else:
                leaves.append({"rowkey": n["rowkey"], "label": n["label"]})
        return leaves

    # ----------------------------------------------------------------
    #  Descargar datos de un indicador
    # ----------------------------------------------------------------
    def fetch_series(
        self,
        rowkey: str,
        frequency: str = "Anual",
        start_year: str = "2010",
        end_year: str = None,
        departamento: str | None = None,
    ) -> pd.DataFrame:
        """Descarga datos de un indicador a la frecuencia solicitada.

        Frecuencias soportadas: Anual, Mensual, Trimestral, Semestral.
        """
        self._start()
        end_year = end_year or str(date.today().year)
        try:
            # 1. Configurar frecuencia, ámbito, años (dispara evento change para
            #    que PrimeFaces re-renderice el árbol si es necesario)
            self._set_frequency(frequency)
            self._set_values_silent(frequency, start_year, end_year, departamento)
            # 2. Expandir árbol y checkear checkbox
            self._expand_tree(rowkey)
            self._check_indicator(rowkey)
            # 3. Buscar
            self._click_buscar()
            # 4. Leer datos según frecuencia
            df = self._read_table(frequency)
            # 5. Filtrar por años en Python
            if not df.empty and "fecha" in df.columns:
                mask = (
                    df["fecha"].dt.year >= int(start_year)
                ) & (df["fecha"].dt.year <= int(end_year))
                df = df[mask].reset_index(drop=True)
            return df
        finally:
            self._stop()

    def _expand_tree(self, target_rowkey: str):
        """Expande los ancestros del nodo sin seleccionarlo."""
        page = self._page
        parts = target_rowkey.split("_")
        for i in range(len(parts)):
            ancestor = "_".join(parts[:i+1])
            toggler = page.query_selector(
                f"li[data-rowkey='{ancestor}'] .ui-tree-toggler"
            )
            if toggler and "ui-icon-triangle-1-e" in (toggler.get_attribute("class") or ""):
                try:
                    toggler.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

    def _set_frequency(self, freq: str):
        """Cambia la frecuencia en el selector y dispara change event."""
        page = self._page
        freq_val = FREQ_MAP.get(freq, "1")
        page.evaluate("""(val) => {
            const sel = document.getElementById('formIzquierda:j_idt50');
            if (sel) {
                sel.value = val;
                sel.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }""", freq_val)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

    def _set_values_silent(self, freq: str, start: str, end: str,
                            depto: str | None):
        """Configura selects via JS sin disparar eventos (los valores se envían al hacer Buscar)."""
        page = self._page
        ambito_val = "1" if depto else "0"
        freq_val = FREQ_MAP.get(freq, "1")
        page.evaluate("""(args) => {
            const a = args[0], s_yr = args[1], e_yr = args[2], f = args[3], d = args[4];
            const elAmbito = document.getElementById('formIzquierda:j_idt21');
            if (elAmbito) elAmbito.value = a;
            const elFreq = document.getElementById('formIzquierda:j_idt50');
            if (elFreq) elFreq.value = f;
            const elIni = document.getElementById('formIzquierda:idAnioInicio');
            if (elIni) elIni.value = s_yr;
            const elFin = document.getElementById('formIzquierda:idAnioFin');
            if (elFin) elFin.value = e_yr;
            const elDepto = document.getElementById('formIzquierda:j_idt29');
            if (elDepto && d) elDepto.value = d;
        }""", [ambito_val, start, end, freq_val, depto])
        page.wait_for_timeout(300)

    def _check_indicator(self, rowkey: str):
        """Checkea el checkbox del nodo hoja.

        Si el nodo no tiene checkbox (folder expandible), busca el primer
        hijo con checkbox. Si el nodo no existe en el DOM (porque la
        frecuencia cambió la estructura del árbol), sube un nivel al padre."""
        page = self._page

        def find_checkbox(rk: str):
            li = page.query_selector(f"li[data-rowkey='{rk}']")
            if not li:
                return None
            cb = li.query_selector(".ui-chkbox-box")
            if cb:
                return cb
            # Sin checkbox: expandir y buscar primer hijo con checkbox
            toggler = li.query_selector(".ui-tree-toggler")
            if toggler and "ui-icon-triangle-1-e" in (toggler.get_attribute("class") or ""):
                toggler.click()
                page.wait_for_timeout(1500)
                page.wait_for_load_state("networkidle")
            children = page.query_selector_all(
                f"li[id^='formIzquierda:idArbolIndicadores:{rk}_']"
            )
            for child in children:
                child_cb = child.query_selector(".ui-chkbox-box")
                if child_cb:
                    return child_cb
            return None

        cb = find_checkbox(rowkey)
        if cb:
            cb.click()
            page.wait_for_timeout(1500)
            return

        # Nodo no encontrado: probar con el padre
        parts = rowkey.split("_")
        for i in range(len(parts) - 1, 0, -1):
            parent = "_".join(parts[:i])
            cb = find_checkbox(parent)
            if cb:
                cb.click()
                page.wait_for_timeout(1500)
                return

    def _click_buscar(self):
        btn = self._page.query_selector(
            "button[id='formIzquierda:idLnkBuscar']"
        )
        if btn:
            btn.click()
            self._page.wait_for_timeout(3000)

    def _read_table(self, frequency: str = "Anual") -> pd.DataFrame:
        page = self._page
        # Intentar leer datos desde Highcharts (pestaña Gráfico)
        df = self._read_highcharts()
        if df is not None and not df.empty:
            return df

        # Fallback: leer desde la tabla HTML (pestaña Datos)
        result = page.query_selector("#centro\\:formSeccRes\\:resultado")
        if not result:
            return pd.DataFrame(columns=["fecha", "valor"])
        table = result.query_selector("table")
        if not table:
            return pd.DataFrame(columns=["fecha", "valor"])

        header_row = table.query_selector("thead tr")
        body_rows = table.query_selector_all("tbody tr")
        if not header_row or not body_rows:
            return pd.DataFrame(columns=["fecha", "valor"])

        headers = [
            th.inner_text().strip()
            for th in header_row.query_selector_all("th")
        ]

        # Detectar formato de columnas y parsear según frecuencia
        if frequency == "Anual":
            return self._parse_anual(headers, body_rows)
        elif frequency in ("Mensual", "Trimestral", "Semestral"):
            return self._parse_periodico(headers, body_rows, frequency)
        return self._parse_anual(headers, body_rows)

    def _read_highcharts(self) -> pd.DataFrame | None:
        page = self._page
        graf_tab = page.query_selector("li.ui-tabs-header:has-text('Gráfico')")
        if not graf_tab:
            return None
        graf_tab.click()
        page.wait_for_timeout(3000)
        chart_data = page.evaluate("""() => {
            try {
                if (typeof Highcharts !== 'undefined' && Highcharts.charts && Highcharts.charts[0]) {
                    var c = Highcharts.charts[0];
                    var cats = c.xAxis[0].categories || [];
                    var series = [];
                    for (var i = 0; i < c.series.length; i++) {
                        var data = [];
                        for (var j = 0; j < c.series[i].data.length; j++) {
                            data.push(c.series[i].data[j].y);
                        }
                        series.push({name: c.series[i].name, data: data});
                    }
                    return JSON.stringify({categories: cats, series: series});
                }
            } catch(e) {}
            return null;
        }()""")
        if not chart_data:
            return None
        data = json.loads(chart_data)
        categories = data.get("categories", [])
        series_list = data.get("series", [])
        rows = []
        for s in series_list:
            name = s.get("name", "")
            for i, val in enumerate(s.get("data", [])):
                cat = categories[i] if i < len(categories) else ""
                if val is not None and cat:
                    try:
                        fecha = self._parse_hc_date(str(cat))
                        if fecha is not None:
                            rows.append({
                                "fecha": fecha,
                                "valor": float(val),
                                "indicador": name,
                            })
                    except (ValueError, TypeError):
                        pass
        if rows:
            return pd.DataFrame(rows).sort_values("fecha").reset_index(drop=True)
        return None

    def _parse_hc_date(self, cat: str) -> pd.Timestamp | None:
        """Parsea categoría de Highcharts a Timestamp.
        Soporta: YYYY, YYYY-M, YYYY-MM, texto mes."""
        cat = cat.strip()
        # YYYY-M o YYYY-MM
        m = re.match(r"^(\d{4})-(\d{1,2})$", cat)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            if 1 <= month <= 12:
                return pd.Timestamp(year=year, month=month, day=1)
        # Solo año
        m = re.match(r"^(\d{4})$", cat)
        if m:
            return pd.Timestamp(year=int(m.group(1)), month=1, day=1)
        # Mes texto + año (ej: "Enero 2010", "2010Enero")
        meses = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }
        cat_lower = cat.lower()
        for mes_nombre, mes_num in meses.items():
            if mes_nombre in cat_lower:
                nums = re.findall(r"\d+", cat)
                if nums:
                    return pd.Timestamp(year=int(nums[0]), month=mes_num, day=1)
        return None

    def _parse_anual(self, headers: list[str],
                     body_rows: list) -> pd.DataFrame:
        """Parsea tabla con columnas de año (YYYY)."""
        year_cols = [h for h in headers[3:] if h.isdigit()]
        rows = []
        for tr in body_rows:
            tds = tr.query_selector_all("td")
            vals = [td.inner_text().strip() for td in tds]
            if len(vals) < 4:
                continue
            indicador = vals[1] if len(vals) > 1 else ""
            for i, year in enumerate(year_cols):
                val_idx = 3 + i
                if val_idx < len(vals):
                    raw = vals[val_idx].strip().replace(",", "")
                    if raw and raw != "-" and raw != "…" and raw != "":
                        try:
                            v = float(raw)
                            rows.append({
                                "fecha": pd.Timestamp(f"{year}-01-01"),
                                "valor": v,
                                "indicador": indicador,
                            })
                        except ValueError:
                            pass
        if rows:
            df = pd.DataFrame(rows)
            return df.sort_values("fecha").drop_duplicates().reset_index(drop=True)
        return pd.DataFrame(columns=["fecha", "valor", "indicador"])

    def _parse_periodico(self, headers: list[str],
                         body_rows: list,
                         frequency: str) -> pd.DataFrame:
        """Parsea tabla con columnas YYYY-M (M=mes o trimestre o semestre)."""
        col_headers = headers[3:]
        # Mapear a qué rango de M corresponde según frecuencia
        max_m = {"Mensual": 12, "Trimestral": 4, "Semestral": 2}
        max_val = max_m.get(frequency, 12)
        rows = []
        for tr in body_rows:
            tds = tr.query_selector_all("td")
            vals = [td.inner_text().strip() for td in tds]
            if len(vals) < 4:
                continue
            indicador = vals[1] if len(vals) > 1 else ""
            for i, col_h in enumerate(col_headers):
                val_idx = 3 + i
                if val_idx >= len(vals):
                    continue
                raw = vals[val_idx].strip().replace(",", "")
                if not raw or raw in ("-", "…", ""):
                    continue
                m = re.match(r"^(\d{4})-(\d{1,2})$", col_h)
                if not m:
                    continue
                year, period = int(m.group(1)), int(m.group(2))
                if period < 1 or period > max_val:
                    continue
                try:
                    v = float(raw)
                    # Convertir período a mes de inicio
                    if frequency == "Mensual":
                        month = period
                    elif frequency == "Trimestral":
                        month = (period - 1) * 3 + 1
                    elif frequency == "Semestral":
                        month = (period - 1) * 6 + 1
                    else:
                        month = 1
                    if 1 <= month <= 12:
                        rows.append({
                            "fecha": pd.Timestamp(year=year, month=month, day=1),
                            "valor": v,
                            "indicador": indicador,
                        })
                except (ValueError, TypeError):
                    pass
        if rows:
            df = pd.DataFrame(rows)
            return df.sort_values("fecha").drop_duplicates().reset_index(drop=True)
        return pd.DataFrame(columns=["fecha", "valor", "indicador"])

    # ----------------------------------------------------------------
    #  Metadata
    # ----------------------------------------------------------------
    def fetch_metadata(self, rowkey: str) -> dict[str, str]:
        self._start()
        try:
            self._expand_tree(rowkey)
            self._set_values_silent("Anual", "2010", "2024", None)
            self._check_indicator(rowkey)
            self._click_buscar()
            meta_tab = self._page.query_selector(
                "li.ui-tabs-header:has-text('Metadatos')"
            )
            if meta_tab:
                meta_tab.click()
                self._page.wait_for_timeout(3000)
            return self._parse_metadata()
        finally:
            self._stop()

    def _parse_metadata(self) -> dict[str, str]:
        page = self._page
        panel = page.query_selector("[id*='idPanelMetadato']")
        if not panel:
            return {}
        html = panel.inner_html()
        meta = {}
        # El metadato está en una tabla con filas label: valor
        rows = re.findall(
            r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>',
            html, re.DOTALL
        )
        for label, value in rows:
            clean_label = re.sub(r'<[^>]+>', '', label).strip()
            clean_value = re.sub(r'<[^>]+>', '', value).strip()
            if clean_label and clean_value:
                meta[clean_label] = clean_value
        if not meta:
            text = re.sub(r'<[^>]+>', '\n', html)
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for i in range(0, len(lines)-1, 2):
                meta[lines[i]] = lines[i+1]
        return meta

    # ----------------------------------------------------------------
    #  Batch
    # ----------------------------------------------------------------
    def fetch_batch(
        self,
        leaves: list[dict],
        frequency: str = "Anual",
        start_year: str = "2014",
        end_year: str = None,
    ) -> pd.DataFrame:
        """Descarga múltiples indicadores secuencialmente."""
        end_year = end_year or str(date.today().year)
        all_dfs = []
        total = len(leaves)
        for idx, leaf in enumerate(leaves):
            print(f"  [{idx+1}/{total}] {leaf['label']} ({leaf['rowkey']})")
            try:
                df = self.fetch_series(
                    leaf["rowkey"], frequency, start_year, end_year
                )
                if not df.empty:
                    df["codigo"] = leaf["rowkey"]
                    df["nombre"] = leaf["label"]
                    all_dfs.append(df)
                    print(f"    -> {len(df)} registros")
                else:
                    print(f"    -> vacío")
            except Exception as e:
                print(f"    -> Error: {e}")
            time.sleep(0.5)
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        return pd.DataFrame()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tree"

    scraper = INEIScraper(headless=False)
    if cmd == "tree":
        nodes = scraper.fetch_indicators_tree(max_depth=4)
        leaves = scraper.get_leaves(nodes)
        print(f"Total de indicadores: {len(leaves)}")
        for l in leaves[:20]:
            print(f"  {l['rowkey']}: {l['label']}")
        with open("inei_indicators.json", "w", encoding="utf-8") as f:
            json.dump(leaves, f, indent=2, ensure_ascii=False)

    elif cmd == "series":
        rk = sys.argv[2] if len(sys.argv) > 2 else "0_1_0_0"
        df = scraper.fetch_series(rk, "Anual", "2010", "2024")
        print(df.to_string())

    elif cmd == "meta":
        rk = sys.argv[2] if len(sys.argv) > 2 else "0_1_0_0"
        meta = scraper.fetch_metadata(rk)
        for k, v in meta.items():
            print(f"{k}: {v}")

    elif cmd == "batch":
        nodes = scraper.fetch_indicators_tree(max_depth=4)
        leaves = scraper.get_leaves(nodes)
        df = scraper.fetch_batch(leaves[:5], "Anual", "2018", "2024")
        print(df.head(20))
