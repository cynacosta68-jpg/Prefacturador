"""Bot de extracción de EVWEB (Playwright). Misma lógica que el bot de Galeno:
fragmenta el rango de fechas en tramos de 9 días, filtra por obra social,
estado de auditoría y facturado, y descarga 'EXPORTAR PRÁCTICAS EXCEL'."""
import os
import time
from datetime import date, timedelta

import pandas as pd

EVWEB_URL = os.environ.get("EVWEB_URL", "https://cmsc.evweb.com.ar/Account/Login")
ESTADO_APROBADO_OS = "APOB"   # APROBADO EN OBRA SOCIAL
FACTURADAS_NO = "NO"


def generar_rangos_9_dias(inicio: date, fin: date):
    rangos, actual = [], inicio
    while actual <= fin:
        tramo = min(actual + timedelta(days=8), fin)
        rangos.append((actual.strftime("%d/%m/%Y"), tramo.strftime("%d/%m/%Y")))
        actual = tramo + timedelta(days=1)
    return rangos


def _iframe(page):
    time.sleep(1)
    for fr in page.frames:
        try:
            if fr.locator("#body_btnFiltro").count() > 0 or fr.locator("#body_btnBusquedaHide").count() > 0:
                return fr
        except Exception:
            pass
    return page.frames[1] if len(page.frames) > 1 else page.main_frame


def _set_fecha(fr, selector, valor):
    loc = fr.locator(selector)
    loc.wait_for(state="visible", timeout=10000)
    loc.click()
    loc.press("Control+a")
    loc.press("Delete")
    time.sleep(0.2)
    loc.type(valor, delay=100)
    time.sleep(0.3)
    if loc.input_value() != valor:
        loc.evaluate(
            "(el, v) => { el.value = v;"
            " el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true}));"
            " el.dispatchEvent(new Event('blur', {bubbles:true})); }", valor)
        time.sleep(0.3)
    return loc.input_value()


def ejecutar_extractor(usuario, clave, codigo_os, rangos, progreso, headless=True):
    """Devuelve {"excels": [DataFrame por tramo], "error": str|None, "avisos": [...]}"""
    from playwright.sync_api import sync_playwright

    excels, avisos, n = [], [], len(rangos)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--start-maximized", "--no-sandbox"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        try:
            progreso("Iniciando sesión en EVWEB…", 0.05)
            page.goto(EVWEB_URL, timeout=60000)
            page.fill("input[name='UserName']", usuario)
            page.fill("#Password", clave)
            page.click("button[type='submit']")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            time.sleep(2)

            progreso("Sesión iniciada. Abriendo Facturación…", 0.08)
            try:
                menu = page.locator("text=/Facturaci/i >> visible=true").first
                menu.wait_for(state="visible", timeout=30000)
                menu.click()
            except Exception:
                if "Login" in (page.url or ""):
                    msg = ""
                    try:
                        err = page.locator(".validation-summary-errors, .field-validation-error, .text-danger")
                        if err.count() > 0:
                            msg = err.first.inner_text().strip()
                    except Exception:
                        pass
                    raise RuntimeError("Login fallido: verificá usuario y contraseña de EVWEB."
                                       + (f" El sitio respondió: '{msg}'." if msg else ""))
                raise RuntimeError("Login OK pero no apareció el menú 'Facturación' en 30s "
                                   "(el sitio pudo cambiar o estar lento).")
            try:
                sub = page.locator("text=/prestaci/i >> visible=true").first
                sub.wait_for(state="visible", timeout=20000)
                sub.click()
            except Exception:
                raise RuntimeError("Apareció 'Facturación' pero no la opción 'prestaciones'.")
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            time.sleep(3)

            for idx, (desde, hasta) in enumerate(rangos):
                avance = 0.10 + (idx / n) * 0.75
                progreso(f"Tramo {idx + 1}/{n}: {desde} → {hasta}", avance)
                if idx > 0:
                    page.reload(wait_until="domcontentloaded")
                    time.sleep(3)

                fr = _iframe(page)
                fr.locator("#body_btnBusquedaHide").wait_for(state="attached", timeout=15000)
                fr.locator("#body_btnBusquedaHide").click(force=True)
                time.sleep(2)

                # Obra social (autocomplete por código)
                inp = fr.locator("#body_txtFiltroObraSocial")
                inp.wait_for(state="visible", timeout=15000)
                inp.click()
                inp.clear()
                inp.press_sequentially(str(codigo_os), delay=150)
                time.sleep(2.5)
                item = fr.locator(".ui-menu-item, .ui-autocomplete li").first
                item.wait_for(state="visible", timeout=10000)
                item.click()
                time.sleep(5)

                fr = _iframe(page)
                fr.locator("#body_cboEstados").wait_for(state="visible", timeout=15000)
                fr.locator("#body_cboEstados").select_option(value=ESTADO_APROBADO_OS)
                time.sleep(3)

                fr = _iframe(page)
                fr.locator("#body_cboFiltroFacturado").wait_for(state="visible", timeout=15000)
                fr.locator("#body_cboFiltroFacturado").select_option(value=FACTURADAS_NO)
                time.sleep(1.5)

                fr = _iframe(page)
                _set_fecha(fr, "#body_txtFiltroFechaCargaDesde", desde)
                _set_fecha(fr, "#body_txtFiltroFechaCargaHasta", hasta)
                time.sleep(1)

                fr.locator("#body_btnFiltro").click()
                progreso(f"Procesando {desde} → {hasta}…", avance + 0.02)
                time.sleep(7)

                fr = _iframe(page)
                if "No Hay Registros" in fr.locator("body").inner_text():
                    avisos.append(f"{desde} → {hasta}: sin registros")
                    continue

                # "Todas" ya viene seleccionada y no dispara el onchange: se fuerza el postback
                try:
                    combo = fr.locator("#body_cboPageSize")
                    if combo.count() > 0:
                        opts, todas, nums = combo.locator("option"), None, []
                        for i in range(opts.count()):
                            v = opts.nth(i).get_attribute("value")
                            t = (opts.nth(i).inner_text() or "").strip().lower()
                            if any(k in t for k in ("todas", "todos", "ver todo", "all")):
                                todas = v
                            try:
                                nums.append((int(str(v).strip()), v))
                            except Exception:
                                pass
                        objetivo = todas or (max(nums)[1] if nums else None)
                        if objetivo:
                            try:
                                combo.select_option(value=objetivo)
                            except Exception:
                                pass
                            for f2 in (fr, page.main_frame):
                                try:
                                    f2.evaluate("__doPostBack('ctl00$body$cboPageSize','')")
                                    break
                                except Exception:
                                    continue
                            try:
                                page.wait_for_load_state("networkidle", timeout=20000)
                            except Exception:
                                pass
                            time.sleep(5)
                            fr = _iframe(page)
                except Exception:
                    pass

                try:
                    chk = fr.locator("#body_grdIntervencion_idChkAll")
                    if chk.count() > 0:
                        chk.click(force=True)
                        time.sleep(1.5)
                except Exception:
                    pass

                try:
                    ham = fr.locator(".btn-group .dropdown-toggle, .dropdown-toggle, button:has(.fa-bars)").first
                    if ham.count() > 0:
                        ham.click()
                        time.sleep(1)
                    with page.expect_download(timeout=50000) as dl:
                        fr.locator("a:has-text('EXPORTAR PRÁCTICAS EXCEL')").click(force=True)
                    df = pd.read_excel(dl.value.path(), dtype=str)
                    excels.append(df)
                    progreso(f"✓ Tramo {idx + 1}/{n}: {len(df)} filas", avance + 0.05)
                except Exception as e:
                    avisos.append(f"{desde} → {hasta}: no se pudo descargar ({e})")
                    continue

            return {"excels": excels, "error": None, "avisos": avisos}
        except Exception as e:
            url = ""
            try:
                url = f" [URL: {page.url}]"
            except Exception:
                pass
            return {"excels": excels, "error": f"{e}{url}", "avisos": avisos}
        finally:
            browser.close()
