"use strict";
/* Interfaz sin dependencias de build. Todo texto de datos pasa por esc(). */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pesos = n => "$ " + Number(n || 0).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const miles = n => Number(n || 0).toLocaleString("es-AR");

const SECCIONES = [
  ["padron", "Padrón", "padron"],
  ["valores", "Valores", "valores"],
  ["bot", "Bot EVWEB", null],
  ["evweb", "Datos extraídos EVWEB", "evweb"],
  ["prefact", "Pre-facturación", "prefact"],
  ["fact", "Facturación", "facturacion"],
  ["templates", "Templates", "templates"],
  ["present", "Presentaciones", null],
];
const ICO = {izq: `<svg class="ico" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg>`, der: `<svg class="ico" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 3 5 5-5 5"/></svg>`, ok: `<svg class="ico" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 8.5 3.2 3.2L13 5"/></svg>`, volver: `<svg class="ico" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 3 2.5 8 7 13M3 8h10.5"/></svg>`};
const NOMBRES = { AVALIAN: "AVALIAN", SANCOR: "SANCOR", GALENO: "GALENO", SWISS: "SWISS MEDICAL" };

const S = {
  os: null, sec: "padron",
  me: null, sel: new Set(), filas: [], pagina: 0, limite: 500, filtros: {}, pollBot: null,
};

function periodoPorDefecto() {
  const d = new Date();
  return String(d.getMonth() + 1).padStart(2, "0") + d.getFullYear();
}

async function api(url, opt = {}) {
  opt.headers = Object.assign({ "X-Requested-With": "app" }, opt.headers || {});
  if (opt.json !== undefined) {
    opt.body = JSON.stringify(opt.json);
    opt.headers["Content-Type"] = "application/json";
    opt.method = opt.method || "POST";
  }
  const r = await fetch(url, opt);
  if (r.status === 401 && !url.endsWith("/login")) { mostrarLogin(); throw new Error("Sesión vencida"); }
  if (!r.ok) {
    let m = "Error " + r.status;
    let datos = null;
    try { datos = await r.json(); m = typeof datos.detail === "string" ? datos.detail : JSON.stringify(datos.detail); } catch (e) { /* sin cuerpo */ }
    const err = new Error(m);
    err.estado = r.status;
    err.datos = datos;
    throw err;
  }
  return opt.crudo ? r : r.json();
}

function toast(msg, mal) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (mal ? " mal" : "");
  t.setAttribute("role", mal ? "alert" : "status");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.add("oculto"), mal ? 7000 : 3500);
}
const fallo = e => toast(e.message || String(e), true);

let focoPrevio = null;
function modal(html) {
  focoPrevio = document.activeElement;
  $("#modalCaja").innerHTML = html;
  $("#modal").classList.remove("oculto");
  $$("[data-cerrar]", $("#modalCaja")).forEach(b => b.onclick = cerrarModal);
  const primero = $("#modalCaja input:not([type=checkbox]), #modalCaja select, #modalCaja .pie .btn.primario, #modalCaja .pie .btn");
  if (primero) primero.focus();
}
function cerrarModal() {
  if ($("#modal").classList.contains("oculto")) return;
  $("#modal").classList.add("oculto");
  if (focoPrevio && document.contains(focoPrevio)) focoPrevio.focus();
}
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") cerrarModal(); });
document.addEventListener("keydown", e => {
  // No se cierra con Escape el cambio obligatorio de contraseña (no tiene botón de cancelar)
  if (e.key === "Escape" && !$("#modal").classList.contains("oculto") && $("#modalCaja [data-cerrar], #modalCaja #cNo")) {
    const no = $("#cNo"); no ? no.click() : cerrarModal();
  }
});

function confirmar(texto, etiqueta = "Confirmar", clase = "primario") {
  return new Promise(res => {
    modal(`<h3>${esc(texto)}</h3><div class="pie"><button class="btn" id="cNo">Cancelar</button>
      <button class="btn ${clase}" id="cSi">${esc(etiqueta)}</button></div>`);
    $("#cNo").onclick = () => { cerrarModal(); res(false); };
    $("#cSi").onclick = () => { cerrarModal(); res(true); };
  });
}

function descargarBlob(blob, nombre) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
}
const qs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();

/* ───────────── sesión y navegación ───────────── */

function pantalla(id) {
  ["login", "inicio", "app"].forEach(p => $("#" + p).classList.toggle("oculto", p !== id));
}
function mostrarLogin() { clearInterval(S.pollBot); cerrarModal(); S.me = null; S.os = null; pantalla("login"); }

$("#fLogin").onsubmit = async e => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("#loginError").textContent = "";
  try {
    await api("/api/login", { json: { usuario: f.get("usuario"), clave: f.get("clave") } });
    e.target.reset();
    iniciar();
  } catch (err) { $("#loginError").textContent = err.message; }
};
const salir = async () => { try { await api("/api/logout", { method: "POST" }); } catch (e) { /* ya sin sesión */ } mostrarLogin(); };
$("#salir").onclick = $("#salir0").onclick = salir;
$("#volver").onclick = () => iniciar();
$("#miClave").onclick = () => cambiarClave(false);
$$("[data-global]").forEach(b => b.onclick = () => abrir(null, b.dataset.global));

function cambiarClave(obligatorio) {
  modal(`<h3>${obligatorio ? "Tenés que cambiar tu contraseña para continuar" : "Cambiar contraseña"}</h3>
    <form id="fc"><div class="rejilla">
      <label>Contraseña actual<input name="actual" type="password" autocomplete="current-password" required></label>
      <label>Nueva (mínimo 10, con letras y números)<input name="nueva" type="password" autocomplete="new-password" required minlength="10"></label>
      <label>Repetir nueva<input name="rep" type="password" autocomplete="new-password" required></label></div>
    <div class="pie">${obligatorio ? "" : `<button type="button" class="btn" data-cerrar>Cancelar</button>`}<button class="btn primario">Guardar</button></div></form>`);
  $("#fc").onsubmit = async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    if (d.nueva !== d.rep) return toast("Las contraseñas nuevas no coinciden", true);
    try { await api("/api/mi-clave", { json: { actual: d.actual, nueva: d.nueva } }); cerrarModal(); toast("Contraseña actualizada"); iniciar(); } catch (err) { fallo(err); }
  };
}

/* Pantalla de inicio: se elige la obra social y recién ahí aparece el menú estándar. */
async function iniciar() {
  clearInterval(S.pollBot);
  try { S.me = await api("/api/me"); } catch (e) { return mostrarLogin(); }
  S.os = null;
  pantalla("inicio");
  $("#quien").textContent = `${S.me.nombre || S.me.usuario} · ${S.me.rol === "admin" ? "Administrador" : "Operador"}`;
  $("#adminZona").classList.toggle("oculto", S.me.rol !== "admin");
  $("#tarjetasOS").innerHTML = Object.keys(NOMBRES).filter(k => S.me.obras[k]).map(k => {
    const r = S.me.resumen[k];
    return `<button data-os="${k}"><strong>${NOMBRES[k]}</strong><small>${esc(S.me.obras[k].nombre)}</small>
      <span class="datos"><span><b>${miles(r.prefact)}</b>en pre-facturación</span><span><b>${miles(r.facturacion)}</b>en facturación</span><span><b>${miles(r.templates)}</b>templates</span></span></button>`;
  }).join("");
  $$("#tarjetasOS button").forEach(b => b.onclick = () => abrir(b.dataset.os, "padron"));
  if (S.me.debe_cambiar) cambiarClave(true);
}

const GLOBALES = { auditoria: "Auditoría", backups: "Copias de seguridad", archivo: "Archivo", usuarios: "Usuarios" };

function abrir(os, sec) {
  S.os = os;
  pantalla("app");
  $("#quien2").textContent = S.me.usuario;
  $("#osLateral").textContent = os ? NOMBRES[os] : "Administración";
  $("#osActual").classList.toggle("oculto", !os);
  ir(sec);
}

async function contadores() {
  if (!S.os) {
    $("#nav").innerHTML = Object.entries(GLOBALES).map(([id, n]) => `<button data-sec="${id}" class="${id === S.sec ? "activo" : ""}">${n}</button>`).join("");
  } else {
    let r = {};
    try { r = await api("/api/resumen?os=" + S.os); } catch (e) { return; }
    $("#nav").innerHTML = SECCIONES.map(([id, nombre, clave]) =>
      `<button data-sec="${id}" class="${id === S.sec ? "activo" : ""}">${nombre}${clave && r[clave] ? `<b>${miles(r[clave])}</b>` : ""}</button>`).join("");
  }
  $$("#nav button").forEach(b => b.onclick = () => ir(b.dataset.sec));
}

function ir(sec) {
  if (S.os ? !SECCIONES.some(s => s[0] === sec) : !GLOBALES[sec]) sec = S.os ? "padron" : "auditoria";
  S.sec = sec;
  S.sel = new Set(); S.pagina = 0; S.filtros = {};
  clearInterval(S.pollBot);
  if (S.os) $("#osActual").textContent = S.me.obras[S.os].nombre;
  $("#titulo").textContent = S.os ? SECCIONES.find(s => s[0] === sec)[1] : GLOBALES[sec];
  $("#subtitulo").textContent = "";
  $("#vista").innerHTML = `<div class="cargando" role="status"><span class="girando" aria-hidden="true"></span>Cargando</div>`;
  contadores();
  VISTAS[sec]().catch(fallo);
}

/* ───────────── tabla genérica ───────────── */

/* Orden de columnas elegido por el usuario: se arrastra el encabezado y queda guardado en el navegador */
function ordenGuardado(clave) {
  try { return JSON.parse(localStorage.getItem("cols:" + clave) || "[]"); } catch (e) { return []; }
}
function ordenarCols(cols, clave) {
  const orden = ordenGuardado(clave);
  if (!orden.length) return cols;
  const pos = k => { const i = orden.indexOf(k); return i < 0 ? 1e6 + cols.findIndex(c => c.k === k) : i; };
  return [...cols].sort((a, b) => pos(a.k) - pos(b.k));
}
function enlazarColumnas(clave, cols, recargar) {
  const ths = $$("th[data-k]");
  let origen = null;
  ths.forEach(th => {
    th.ondragstart = e => { origen = th.dataset.k; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", origen); th.classList.add("moviendo"); };
    th.ondragend = () => { th.classList.remove("moviendo"); ths.forEach(x => x.classList.remove("destino")); };
    th.ondragover = e => { if (origen && origen !== th.dataset.k) { e.preventDefault(); th.classList.add("destino"); } };
    th.ondragleave = () => th.classList.remove("destino");
    th.ondrop = e => {
      e.preventDefault();
      const destino = th.dataset.k;
      if (!origen || origen === destino) return;
      const orden = cols.map(c => c.k).filter(k => k !== origen);
      orden.splice(orden.indexOf(destino), 0, origen);      // la columna arrastrada queda delante de la de destino
      try { localStorage.setItem("cols:" + clave, JSON.stringify(orden)); } catch (err) { /* sin almacenamiento: no se guarda */ }
      recargar();
    };
  });
  const b = $("#colsReset");
  if (b) b.onclick = () => { try { localStorage.removeItem("cols:" + clave); } catch (err) { /* nada */ } recargar(); };
}

function tabla(cols, filas, opt = {}) {
  if (!filas.length) return `<div class="tabla"><div class="vacio">${esc(opt.vacio || "Sin datos.")}</div></div>`;
  const th = cols.map(c => `<th class="${c.num ? "num" : ""}${opt.mover ? " movible" : ""}" ${opt.mover ? `draggable="true" data-k="${esc(c.k)}" title="Arrastrá para mover la columna"` : ""}>${esc(c.t)}</th>`).join("");
  const tr = filas.map((f, i) => {
    const tds = cols.map(c => {
      const v = c.f ? c.f(f) : esc(f[c.k]);
      return `<td class="${c.num ? "num" : ""}" title="${c.f ? "" : esc(f[c.k])}">${v}</td>`;
    }).join("");
    const sel = opt.sel ? `<td><input type="checkbox" data-id="${f.id}" ${S.sel.has(f.id) ? "checked" : ""}></td>` : "";
    const acc = opt.acciones ? `<td class="acc">${opt.acciones(f, i)}</td>` : "";
    return `<tr data-id="${f.id ?? i}" class="${opt.sel && S.sel.has(f.id) ? "sel" : ""}">${sel}${tds}${acc}</tr>`;
  }).join("");
  return `<div class="tabla"><table><thead><tr>${opt.sel ? `<th><input type="checkbox" id="selTodo"></th>` : ""}${th}${opt.acciones ? "<th></th>" : ""}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

function enlazarSeleccion(alCambiar, opt = {}) {
  const todo = $("#selTodo");
  const cajas = $$("tbody input[type=checkbox][data-id]");
  const refrescar = () => {
    cajas.forEach(c => c.closest("tr").classList.toggle("sel", c.checked));
    if (todo) todo.checked = cajas.length > 0 && cajas.every(c => c.checked);
    alCambiar();
  };
  cajas.forEach(c => c.onchange = () => { const id = +c.dataset.id; c.checked ? S.sel.add(id) : S.sel.delete(id); refrescar(); });
  // La casilla de la cabecera selecciona TODAS las filas que cumplen el filtro (también las de otras páginas)
  // cuando la vista sabe traer sus ids; si no, solo las de la página.
  if (todo) todo.onchange = async () => {
    const marcar = todo.checked;
    if (opt.traerIds && opt.total > cajas.length) {
      todo.disabled = true;
      try {
        if (marcar) { const ids = await opt.traerIds(); S.sel.clear(); ids.forEach(i => S.sel.add(i)); toast(`${miles(ids.length)} línea(s) seleccionada(s): todas las que cumplen el filtro`); }
        else S.sel.clear();
      } catch (err) { fallo(err); }
      todo.disabled = false;
      cajas.forEach(c => { c.checked = S.sel.has(+c.dataset.id); });
    } else cajas.forEach(c => { c.checked = marcar; const id = +c.dataset.id; marcar ? S.sel.add(id) : S.sel.delete(id); });
    refrescar();
  };
  refrescar();
  return () => { cajas.forEach(c => { c.checked = S.sel.has(+c.dataset.id); }); refrescar(); };
}

const MAX_TODAS = 2000;
function paginador(total) {
  if (S.limite === 0 && total > MAX_TODAS) S.limite = 500;
  const lim = S.limite;
  const pags = lim > 0 ? Math.max(1, Math.ceil(total / lim)) : 1;
  if (S.pagina >= pags) S.pagina = pags - 1;
  const desde = lim > 0 ? S.pagina * lim + 1 : 1;
  const hasta = lim > 0 ? Math.min(total, (S.pagina + 1) * lim) : total;
  // «todas» solo se ofrece con pocas filas: dibujar miles de filas juntas cuelga el navegador
  return `<label>Ver<select id="pLim">${[200, 500, 1500].map(n => `<option value="${n}" ${lim === n ? "selected" : ""}>de a ${n} filas</option>`).join("")}
    ${total <= MAX_TODAS ? `<option value="0" ${lim === 0 ? "selected" : ""}>todas</option>` : ""}</select></label>
    ${lim > 0 && pags > 1 ? `<button class="btn" id="pAnt" ${S.pagina === 0 ? "disabled" : ""} aria-label="Página anterior">${ICO.izq}</button>
    <span class="suave">${miles(desde)}–${miles(hasta)} de ${miles(total)}</span>
    <button class="btn" id="pSig" ${S.pagina >= pags - 1 ? "disabled" : ""} aria-label="Página siguiente">${ICO.der}</button>` : `<span class="suave">${miles(total)} filas</span>`}`;
}
function enlazarPaginador(recargar) {
  $("#pLim").onchange = e => { S.limite = +e.target.value; S.pagina = 0; recargar(); };
  if ($("#pAnt")) $("#pAnt").onclick = () => { S.pagina--; recargar(); };
  if ($("#pSig")) $("#pSig").onclick = () => { S.pagina++; recargar(); };
}
function filtrosBusqueda(F, profesionales) {
  return `<label>Cuenta - profesional<input id="fProf" list="lProf" value="${esc(F.prof || "")}" placeholder="Elegí o escribí" autocomplete="off">
      <datalist id="lProf">${profesionales.map(p => `<option value="${esc(p)}">`).join("")}</datalist></label>
    <label>N° de transacción<input id="fNro" value="${esc(F.nro || "")}" inputmode="numeric" placeholder="Ej: 137713973" size="14"></label>
    <label>Texto libre<input id="q" value="${esc(F.q || "")}" placeholder="Afiliado, código, prestación…"></label>
    ${F.prof || F.nro || F.q || F.fdesde || F.fhasta ? `<button class="btn" id="fLimpiar">Limpiar filtros</button>` : ""}`;
}
function enlazarBusqueda(F, recargar) {
  const tras = id => () => recargar().then(() => { const i = $("#" + id); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } });
  $("#fProf").onchange = e => { F.prof = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  $("#fProf").oninput = e => { if (!e.target.value && F.prof) { F.prof = ""; S.pagina = 0; recargar(); } };
  $("#fNro").oninput = conDemora(e => { F.nro = e.target.value; S.pagina = 0; tras("fNro")(); });
  $("#q").oninput = conDemora(e => { F.q = e.target.value; S.pagina = 0; tras("q")(); });
  if ($("#fLimpiar")) $("#fLimpiar").onclick = () => { ["prof", "nro", "q", "fdesde", "fhasta"].forEach(k => delete F[k]); S.pagina = 0; recargar(); };
}
const conDemora = (fn, ms = 350) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

async function subir(url, campos, archivo) {
  const fd = new FormData();
  Object.entries(campos).forEach(([k, v]) => fd.append(k, v));
  fd.append("archivo", archivo);
  return api(url, { method: "POST", body: fd });
}

const VISTAS = {};

/* ───────────── Padrón ───────────── */

VISTAS.padron = async () => {
  $("#subtitulo").textContent = "Base de profesionales de la obra social. Se usa para completar cuenta, matrícula, CUIT, especialidad y categoría.";
  const q = S.filtros.q || "";
  const { filas } = await api("/api/padron?" + qs({ os: S.os, q }));
  S.filas = filas;
  const cols = [{ k: "cuenta", t: "Cuenta" }, { k: "nombre", t: "Profesional" }, { k: "cuit", t: "CUIT" },
    { k: "especialidad", t: "Especialidad" }, { k: "categoria", t: "Categoría" }, { k: "resp_fiscal", t: "Resp. fiscal" },
    { k: "matricula", t: "Matrícula (MP)" }, { k: "efector", t: "Efector" },
    { k: "codigo_iva", t: "Código de IVA", f: f => `<span class="et ${f.codigo_iva ? "ok" : ""}">${f.codigo_iva ? "1" : "0"}</span>` }];
  $("#vista").innerHTML = `
    <div class="barra">
      <label>Buscar<input id="q" value="${esc(q)}" placeholder="Nombre, cuenta, CUIT, matrícula…"></label>
      <span class="suave">${miles(filas.length)} profesionales</span><span class="sep"></span>
      <button class="btn" id="nuevo">+ Agregar</button>
      <button class="btn primario" id="pArca" title="Consulta en ARCA la condición fiscal de cada profesional">Actualizar condición desde ARCA</button>
      <label class="btn">Importar base (.xlsx)<input type="file" id="arch" accept=".xlsx,.xls,.csv" class="oculto"></label>
      <a class="btn" href="/api/padron/exportar?os=${S.os}">Exportar Excel</a>
    </div>
    ${S.os === "GALENO" && filas.length && !filas.some(f => f.matricula) ? `<div class="aviso info">La base de GALENO no trae matrícula provincial (MP). Para la planilla de Galeno se toma la MP del mismo CUIT en los padrones de SANCOR / AVALIAN; también podés cargarla acá.</div>` : ""}
    ${tabla(cols, filas, { vacio: "Padrón vacío. Importá la base de profesionales de esta obra social.",
      acciones: f => `<button class="btn mini" data-ed="${f.id}">Editar</button>` })}`;
  $("#q").oninput = conDemora(e => { S.filtros.q = e.target.value; VISTAS.padron().then(() => { const i = $("#q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); });
  $("#arch").onchange = async e => {
    const a = e.target.files[0]; if (!a) return;
    if (filas.length && !await confirmar(`Se reemplaza el padrón de ${S.os} (${filas.length} profesionales) por el archivo. ¿Continuar?`, "Reemplazar")) return;
    try { const r = await subir("/api/padron/importar", { os: S.os }, a); toast(`${r.importados} profesionales importados`); ir("padron"); } catch (err) { fallo(err); }
  };
  // Actualización de la responsabilidad fiscal con ARCA (a través de Arcanum): corre en segundo plano
  const informeArca = j => {
    const lista = (t, xs, f) => xs.length ? `<p class="suave">${t}</p><pre class="log">${esc(xs.map(f).join("\n"))}</pre>` : "";
    modal(`<h3>${j.estado === "error" ? "La actualización desde ARCA se interrumpió" : "Padrón actualizado con ARCA"}</h3>
      ${j.error ? `<div class="aviso mal sinMargen" role="alert">${esc(j.error)}</div>` : ""}
      <dl class="detalleFila">
        <div><dt>CUIT consultados</dt><dd>${miles(j.hechos)} de ${miles(j.total)}</dd></div>
        <div><dt>Con cambio de condición</dt><dd>${miles(j.n_cambios)}</dd></div>
        <div><dt>Sin dato en ARCA</dt><dd>${miles(j.n_sin_datos)}</dd></div>
        <div><dt>No se pudieron consultar</dt><dd>${miles(j.n_errores)}</dd></div>
        ${j.sin_cuit ? `<div><dt>Sin CUIT en el padrón</dt><dd>${miles(j.sin_cuit)}</dd></div>` : ""}
      </dl>
      ${lista("Cambios aplicados (responsabilidad fiscal y código de IVA):", j.cambios, c => `${c.profesional} (${c.cuit}): ${c.antes || "—"} → ${c.despues} · código de IVA ${c.codigo_iva}`)}
      ${lista("Sin dato en ARCA (se dejó lo que estaba cargado):", j.sin_datos, c => `${c.profesional} (${c.cuit}): ${c.motivo}`)}
      ${lista("No se pudieron consultar:", j.errores, c => `${c.profesional} (${c.cuit}): ${c.motivo}`)}
      <div class="pie"><button class="btn primario" data-cerrar>Cerrar</button></div>`);
  };
  const seguirArca = async () => {
    const b = $("#pArca"); if (!b) return;
    try {
      const { job } = await api("/api/padron/arca?os=" + S.os);
      if (!job) return;
      if (job.estado === "corriendo") {
        b.disabled = true; b.textContent = `Consultando ARCA… ${miles(job.hechos)} de ${miles(job.total)}`;
        setTimeout(seguirArca, 2000);
      } else if (b.disabled) { await VISTAS.padron(); informeArca(job); }
    } catch (err) { fallo(err); }
  };
  $("#pArca").onclick = async () => {
    if (!await confirmar(`Se va a consultar en ARCA la condición fiscal de los ${miles(filas.length)} profesionales de ${NOMBRES[S.os]} y actualizar la responsabilidad fiscal y el código de IVA de los que hayan cambiado. Antes se hace una copia de seguridad. ¿Actualizar?`, "Actualizar")) return;
    try { await api("/api/padron/arca", { json: { os: S.os } }); $("#pArca").disabled = true; seguirArca(); } catch (err) { fallo(err); }
  };
  seguirArca();
  const form = f => {
    const campos = [["cuenta", "Cuenta"], ["nombre", "Profesional"], ["cuit", "CUIT"], ["especialidad", "Especialidad"],
      ["categoria", "Categoría"], ["resp_fiscal", "Responsabilidad fiscal"], ["matricula", "Matrícula (MP)"], ["efector", "Efector"]];
    modal(`<h3>${f ? "Editar profesional" : "Agregar profesional"}</h3><form id="fp"><div class="rejilla">
      ${campos.map(([k, t]) => `<label>${t}<input name="${k}" value="${esc(f ? (f[k] || "") : "")}"></label>`).join("")}</div>
      <p class="suave">El código de IVA se calcula solo: 1 si la responsabilidad fiscal es «Responsable Inscripto», 0 en los demás casos.</p>
      <div class="pie">${f ? `<button type="button" class="btn peligro" id="pBorrar">Eliminar</button>` : ""}
      <button type="button" class="btn" id="pArcaUno">Consultar ARCA</button><span class="sep"></span>
      <button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Guardar</button></div></form>`);
    // Trae de ARCA la condición fiscal del CUIT cargado y la deja en el formulario (se guarda con «Guardar»)
    $("#pArcaUno").onclick = async () => {
      const fp = $("#fp"), cuit = fp.elements.cuit.value.replace(/\D/g, "");
      if (cuit.length !== 11) return toast("Cargá un CUIT de 11 dígitos", true);
      const b = $("#pArcaUno"); b.disabled = true; b.textContent = "Consultando…";
      try {
        const r = await api("/api/padron/arca/" + cuit);
        if (r.resp_fiscal) { fp.elements.resp_fiscal.value = r.resp_fiscal; toast(`ARCA: ${r.resp_fiscal} · código de IVA ${r.codigo_iva}`); }
        else toast("ARCA no informa la condición frente al IVA" + (r.observacion ? ": " + r.observacion : ""), true);
        if (r.razon_social && !fp.elements.nombre.value) fp.elements.nombre.value = r.razon_social;
      } catch (err) { fallo(err); }
      b.disabled = false; b.textContent = "Consultar ARCA";
    };
    $("#fp").onsubmit = async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target)); d.os = S.os;
      try { await api(f ? "/api/padron/" + f.id : "/api/padron", { method: f ? "PUT" : "POST", json: d }); cerrarModal(); toast("Guardado"); ir("padron"); } catch (err) { fallo(err); }
    };
    if (f) $("#pBorrar").onclick = async () => { try { await api("/api/padron/" + f.id, { method: "DELETE" }); cerrarModal(); ir("padron"); } catch (err) { fallo(err); } };
  };
  $("#nuevo").onclick = () => form(null);
  $$("[data-ed]").forEach(b => b.onclick = () => form(filas.find(f => f.id === +b.dataset.ed)));
};

/* ───────────── Valores ───────────── */

VISTAS.valores = async () => {
  $("#subtitulo").textContent = S.os === "SWISS" ? "Valores fijos (reporte del sistema) y valores por unidades (unidades × valor de la unidad), consolidados por período de vigencia. En «Unidades» se cargan los valores de cada unidad." : "Grilla normalizada: todas las solapas del Excel unificadas. En «Unidades» están los valores por unidad, que son los que se cambian cada período.";
  const meta = await api("/api/valores/meta?os=" + S.os);
  const F = S.filtros;
  const per = F.periodo && meta.periodos.includes(F.periodo) ? F.periodo : (meta.periodos[0] || "");
  let d = { total: 0, filas: [], unidades: [], por_unidad: 0, fijas: 0 };
  if (per) d = await api("/api/valores?" + qs({ os: S.os, periodo: per, especialidad: F.esp || "", q: F.q || "", tipo: F.tipo || "", unidad: F.unidad || "", limite: S.limite, desde: S.pagina * S.limite }));
  const num = n => Number(n).toLocaleString("es-AR", { maximumFractionDigits: 2 });
  const cols = [
    { k: "codigo", t: "Código", f: f => esc(f.codigo || f.codigo_prestador) + (f.codigo && f.codigo_prestador && f.codigo !== f.codigo_prestador ? ` <span class="suave">/ ${esc(f.codigo_prestador)}</span>` : "") },
    { k: "descripcion", t: "Descripción", f: f => esc(f.descripcion) + (f.grupo ? ` <span class="suave">· ${esc(f.grupo)}</span>` : "") },
    { k: "especialidad", t: "Especialidad" },
    { k: "categoria", t: "Cat.", f: f => f.categoria === "R" ? `<span class="et avi">Recert.</span>` : esc(f.categoria) },
    { k: "unidades", t: "Cant. unidades", num: true, f: f => f.tipo_valor === "unidad" ? num(f.unidades) : `<span class="suave">N/A</span>` },
    { k: "valor", t: "Valor", num: true, f: f => f.valor ? pesos(f.valor) : `<span class="et mal">sin unidad</span>` },
    { k: "tipo_valor", t: "Tipo de valor", f: f => f.tipo_valor === "unidad" ? `<span class="et ok">Por unidad</span>` : `<span class="et">Fijo</span>` },
    { k: "tipo_unidad", t: "Unidad", f: f => f.tipo_unidad ? `${esc(f.tipo_unidad)} <span class="suave">${pesos(f.valor_unidad)}</span>` : "" },
  ];
  const opc = (v, t, sel) => `<option value="${esc(v)}" ${String(v) === String(sel || "") ? "selected" : ""}>${esc(t)}</option>`;
  $("#vista").innerHTML = `
    <div class="tarjeta bloque"><h3>${S.os === "SWISS" ? "Actualizar valores de SWISS MEDICAL" : "Subir grilla de " + NOMBRES[S.os]}</h3>
      ${S.os === "SWISS" ? `<p class="suave sinMargen">Subí el <b>reporte de valores fijos</b> que sale del sistema, la tabla <b>unidades</b> (valor de cada unidad) o la tabla <b>Valor en unidades</b> (unidades por prestación); también se acepta el Excel con las tres juntas. La vigencia indicada se usa cuando el archivo no trae su propia columna de período. Los valores fijos y los valores por unidades (unidades × valor de la unidad) quedan consolidados en la solapa «Valores».</p>` : ""}
      <div class="fila">
        <label>${S.os === "SWISS" ? "Vigencia de los valores (MMAAAA)" : "Período de la grilla (MMAAAA)"}<input id="gPer" value="${esc(S.os === "SWISS" ? periodoPorDefecto() : (per || periodoPorDefecto()))}" maxlength="6" size="8"></label>
        <label>${S.os === "SWISS" ? "Archivo (valores fijos, unidades, Valor en unidades, o la base completa)" : "Archivo de la grilla (Excel con todas las solapas)"}<input type="file" id="gArch" accept=".xlsx,.xls"></label>
        <button class="btn primario" id="gSubir">${S.os === "SWISS" ? "Subir y actualizar" : "Subir y extraer"}</button>
        ${per ? `<span class="sep"></span><button class="btn" id="gCopiar">Nuevo período a partir de ${per}</button>` : ""}
      </div><div id="gRes"></div>
    </div>
    ${per ? `
    <div class="pestanas" role="tablist">
      <button role="tab" aria-selected="${F.tab !== "unid" && F.tab !== "otros"}" class="${F.tab !== "unid" && F.tab !== "otros" ? "activo" : ""}" data-tab="prest">Valores</button>
      <button role="tab" aria-selected="${F.tab === "unid"}" class="${F.tab === "unid" ? "activo" : ""}" data-tab="unid">Unidades <b>${miles(d.unidades.length)}</b></button>
      <button role="tab" aria-selected="${F.tab === "otros"}" class="${F.tab === "otros" ? "activo" : ""}" data-tab="otros">Otros</button>
    </div>
    <div id="gCuerpo">
    <div class="banda"><div class="kpis">
      <div class="kpi"><span>Prestaciones</span><b>${miles(d.total)}</b></div>
      <div class="kpi"><span>Por unidad</span><b>${miles(d.por_unidad)}</b></div>
      <div class="kpi"><span>Valor fijo</span><b>${miles(d.fijas)}</b></div>
      <div class="kpi"><span>Valores de unidad</span><b>${miles(d.unidades.length)}</b></div></div>
      <div class="acciones"><a class="btn" href="/api/valores/exportar?${qs({ os: S.os, periodo: per, especialidad: F.esp || "", q: F.q || "", tipo: F.tipo || "", unidad: F.unidad || "" })}">Exportar Excel</a>
      <button class="btn" id="gBorrar">Eliminar período</button></div></div>
    ${F.tab === "unid" ? `
    <div class="filtros">
      <label>Período<select id="fPer">${meta.periodos.map(p => opc(p, p, per)).join("")}</select></label>
      <label>Especialidad<select id="fEsp">${opc("", "Todas", F.esp)}${(meta.especialidades[per] || []).map(e => opc(e, e, F.esp)).join("")}</select></label>
      <span class="suave">Al cambiar un valor se recalculan todas las prestaciones que usan esa unidad (unidades × valor).</span>
      <span class="sep"></span><button class="btn primario" id="uRecalc">Actualizar valores por unidades</button>
    </div>
    ${tabla([
      { k: "especialidad", t: "Especialidad" }, { k: "tipo_unidad", t: "Tipo de unidad", f: x => `<b>${esc(x.tipo_unidad)}</b>` },
      { k: "periodo", t: "Período" },
      { k: "valor", t: "Valor", num: true, f: x => `<input class="valorU" value="${esc(String(x.valor).replace(".", ","))}" data-uid="${x.id}" data-orig="${x.valor}" inputmode="decimal" aria-label="Valor de ${esc(x.tipo_unidad)} · ${esc(x.especialidad)}">` },
      { k: "prestaciones", t: "Prestaciones", num: true, f: x => x.prestaciones ? `<button class="btn mini" data-ver="${x.id}">${miles(x.prestaciones)} · ver</button>` : `<span class="suave">${x.origen === "general" ? "referencia" : "sin uso"}</span>` },
      { k: "origen", t: "Origen", f: x => ({ declarada: "Declarada en la grilla", deducida: "Deducida de la grilla", general: "Listado general", modificada: "Modificada a mano" }[x.origen] || esc(x.origen)) },
    ], d.unidades, { vacio: "Esta selección no tiene valores por unidad.", acciones: x => `<button class="btn mini primario" data-guardar="${x.id}" disabled>Guardar</button>` })}` : `
    <div class="filtros">
      <label>Período<select id="fPer">${meta.periodos.map(p => opc(p, p, per)).join("")}</select></label>
      <label>Especialidad<select id="fEsp">${opc("", "Todas", F.esp)}${(meta.especialidades[per] || []).map(e => opc(e, e, F.esp)).join("")}</select></label>
      <label>Tipo de valor<select id="fTipo">${opc("", "Todos", F.tipo)}${opc("unidad", "Por unidad", F.tipo)}${opc("fijo", "Fijo", F.tipo)}</select></label>
      <label>Buscar<input id="q" value="${esc(F.q || "")}" placeholder="Código o descripción"></label>
      ${F.unidad ? `<button class="btn" id="uQuitar">Quitar filtro de unidad</button>` : ""}
      <button class="btn peligro" id="vElim" disabled>Eliminar seleccionadas</button>
      ${paginador(d.total)}
    </div>
    ${tabla(cols, d.filas, { sel: true, vacio: "Sin prestaciones para ese filtro.", acciones: f => f.tipo_valor === "fijo" ? `<button class="btn mini" data-fijo="${f.id}">Cambiar valor</button>` : "" })}`}
    </div>
` : `<div class="tabla"><div class="vacio">Todavía no hay grillas cargadas para esta obra social. Subí el Excel de la grilla tal como lo entrega la obra social.</div></div>`}`;

  const recargar = () => VISTAS.valores().catch(fallo);
  $("#gSubir").onclick = async () => {
    const a = $("#gArch").files[0]; if (!a) return toast("Elegí el archivo de la grilla", true);
    const b = $("#gSubir"); b.disabled = true; b.setAttribute("aria-busy", "true"); b.textContent = "Procesando…";
    try {
      const r = await subir("/api/valores/importar", { os: S.os, periodo: $("#gPer").value }, a);
      S.filtros = { periodo: r.periodo, tab: "prest" }; S.pagina = 0;
      contadores(); await VISTAS.valores();
      $("#gRes").innerHTML = `<div class="aviso ok sinMargen" role="status">${ICO.ok}${miles(r.filas)} prestaciones unificadas de ${r.hojas.length} solapa(s): ${miles(r.por_unidad)} por unidad y ${miles(r.fijas)} de valor fijo · ${miles(r.unidades)} valores de unidad.</div>
        <div class="chips sinMargen">${r.hojas.map(h => `<span>${esc(h.hoja)}: ${miles(h.prestaciones)}</span>`).join("")}</div>`;
    } catch (err) { fallo(err); b.disabled = false; b.removeAttribute("aria-busy"); b.textContent = "Subir y extraer"; }
  };
  if (!per) return;
  $("#gCopiar").onclick = () => {
    modal(`<h3>Nuevo período a partir de ${per}</h3><p class="suave">Copia las prestaciones y los valores por unidad de ${per}. Después solo cambiás los valores de unidad del período nuevo.</p>
      <form id="fcp"><label>Período nuevo (MMAAAA)<input name="destino" maxlength="6" required pattern="(0[1-9]|1[0-2])[0-9]{4}"></label>
      <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Crear período</button></div></form>`);
    $("#fcp").onsubmit = async e => {
      e.preventDefault();
      const destino = new FormData(e.target).get("destino");
      try { const r = await api("/api/valores/copiar", { json: { os: S.os, origen: per, destino } }); cerrarModal(); toast(`Período ${destino} creado con ${miles(r.prestaciones)} prestaciones`); S.filtros = { periodo: destino }; contadores(); recargar(); } catch (err) { fallo(err); }
    };
  };
  $$("[data-tab]").forEach(b => b.onclick = () => { F.tab = b.dataset.tab; F.unidad = ""; S.pagina = 0; S.sel.clear(); recargar(); });
  // Solapa «Otros»: valores cargados a mano para prestaciones que la grilla no trae
  if (F.tab === "otros") {
    const { filas: otros } = await api("/api/otros?os=" + S.os);
    const monto = v => v ? pesos(v) : `<span class="et mal">completar</span>`;
    $("#gCuerpo").innerHTML = `
      <div class="barra">
        <span class="suave">Valores cargados a mano: mandan sobre la grilla. Sirven para prestaciones que la grilla no trae y para corregir un valor sin tocarla. El valor rige desde la vigencia indicada; para un valor nuevo agregá otra fila con la nueva vigencia. Si el valor depende de la especialidad del profesional, cargá una fila por especialidad. La categoría R usa «Valor R» si está cargado.</span>
        <span class="sep"></span>
        <button class="btn peligro" id="oElim" disabled>Eliminar seleccionadas</button>
        <button class="btn primario" id="oNuevo">+ Agregar</button>
        <label class="btn">Importar Excel<input type="file" id="oArch" accept=".xlsx,.xls,.csv" class="oculto"></label>
        <a class="btn" href="/api/otros/exportar?os=${S.os}">Exportar Excel</a>
      </div>
      ${tabla([
        { k: "codigo", t: "Código", f: x => `<b>${esc(x.codigo)}</b>` }, { k: "descripcion", t: "Descripción" },
        { k: "especialidad", t: "Especialidad", f: x => x.especialidad ? esc(x.especialidad) : `<span class="suave">todas</span>` },
        { k: "vigencia", t: "Vigencia desde" },
        { k: "valor", t: "Valor · todas las categorías", num: true, f: x => monto(x.valor) },
        { k: "valor_r", t: "Valor · categoría R", num: true, f: x => x.valor_r ? pesos(x.valor_r) : `<span class="suave">igual al general</span>` },
      ], otros, { sel: true, vacio: "Todavía no hay valores cargados a mano.", acciones: x => `<button class="btn mini" data-otro="${x.id}">Editar</button>` })}`;
    const formOtro = x => {
      const v = n => n ? String(n).replace(".", ",") : "";
      modal(`<h3>${x ? "Editar valor" : "Agregar valor"}</h3><form id="fo"><div class="rejilla">
        <label>Código de prestación<input name="codigo" value="${esc(x ? x.codigo : "")}" required></label>
        <label>Vigencia desde (MMAAAA)<input name="vigencia" value="${esc(x ? x.vigencia : (per || periodoPorDefecto()))}" maxlength="6" required pattern="(0[1-9]|1[0-2])[0-9]{4}"></label>
        <label>Descripción<input name="descripcion" value="${esc(x ? x.descripcion || "" : "")}"></label>
        <label>Especialidad (vacío = todas; escribila como figura en el padrón)<input name="especialidad" value="${esc(x ? x.especialidad || "" : "")}" placeholder="Ej: CARDIOLOGIA"></label>
        <label>Valor · todas las categorías<input name="valor" value="${esc(x ? v(x.valor) : "")}" inputmode="decimal"></label>
        <label>Valor · categoría R (vacío = igual al general)<input name="valor_r" value="${esc(x ? v(x.valor_r) : "")}" inputmode="decimal"></label></div>
        <div class="pie">${x ? `<button type="button" class="btn peligro" id="oBorrar">Eliminar</button>` : ""}<span class="sep"></span>
        <button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Guardar</button></div></form>`);
      $("#fo").onsubmit = async e => {
        e.preventDefault();
        const d = Object.fromEntries(new FormData(e.target)); d.os = S.os;
        try { await api(x ? "/api/otros/" + x.id : "/api/otros", { method: x ? "PUT" : "POST", json: d }); cerrarModal(); toast("Guardado"); recargar(); } catch (err) { fallo(err); }
      };
      if (x) $("#oBorrar").onclick = async () => {
        if (!await confirmar(`¿Eliminar el valor del código ${x.codigo} (vigencia ${x.vigencia})?`, "Eliminar", "peligro")) return;
        try { await api("/api/otros/" + x.id, { method: "DELETE" }); cerrarModal(); recargar(); } catch (err) { fallo(err); }
      };
    };
    // Selección y borrado en bloque
    enlazarSeleccion(() => { $("#oElim").disabled = S.sel.size === 0; $("#oElim").textContent = S.sel.size ? `Eliminar ${miles(S.sel.size)} seleccionada(s)` : "Eliminar seleccionadas"; });
    $("#oElim").onclick = async () => {
      if (!await confirmar(`¿Eliminar ${miles(S.sel.size)} valor(es) de «Otros»? Queda registrado en la auditoría.`, "Eliminar", "peligro")) return;
      try { const r = await api("/api/otros/eliminar", { json: { os: S.os, ids: [...S.sel] } }); S.sel.clear(); toast(`${miles(r.eliminadas)} valor(es) eliminados`); recargar(); } catch (err) { fallo(err); }
    };
    $("#oNuevo").onclick = () => formOtro(null);
    $$("[data-otro]").forEach(b => b.onclick = () => formOtro(otros.find(x => x.id === +b.dataset.otro)));
    $("#oArch").onchange = async e => {
      const a = e.target.files[0]; if (!a) return;
      try { const r = await subir("/api/otros/importar", { os: S.os }, a); toast(`${miles(r.nuevos)} valor(es) agregados · ${miles(r.actualizados)} actualizados`); recargar(); } catch (err) { fallo(err); }
    };
    return;
  }
  if ($("#pLim")) enlazarPaginador(recargar);
  $("#fPer").onchange = e => { S.filtros = { periodo: e.target.value, tab: F.tab }; S.pagina = 0; recargar(); };
  $("#fEsp").onchange = e => { F.esp = e.target.value; F.unidad = ""; S.pagina = 0; recargar(); };
  if ($("#fTipo")) $("#fTipo").onchange = e => { F.tipo = e.target.value; S.pagina = 0; recargar(); };
  if ($("#q")) $("#q").oninput = conDemora(e => { F.q = e.target.value; S.pagina = 0; VISTAS.valores().then(() => { const i = $("#q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }).catch(fallo); });
  if ($("#uQuitar")) $("#uQuitar").onclick = () => { F.unidad = ""; S.pagina = 0; recargar(); };
  // Recalcula todo el período: valor de cada prestación por unidad = unidades × valor de su unidad
  if ($("#uRecalc")) $("#uRecalc").onclick = async () => {
    const b = $("#uRecalc"); b.disabled = true; b.textContent = "Actualizando…";
    try { const r = await api("/api/valores/recalcular", { json: { os: S.os, periodo: per } }); toast(`${miles(r.recalculadas)} prestaciones recalculadas (unidades × valor de la unidad) para ${per}`); recargar(); }
    catch (err) { fallo(err); b.disabled = false; b.textContent = "Actualizar valores por unidades"; }
  };
  // Selección y borrado en bloque de prestaciones de la grilla
  if ($("#vElim")) {
    enlazarSeleccion(() => { $("#vElim").disabled = S.sel.size === 0; $("#vElim").textContent = S.sel.size ? `Eliminar ${miles(S.sel.size)} seleccionada(s)` : "Eliminar seleccionadas"; });
    $("#vElim").onclick = async () => {
      if (!await confirmar(`¿Eliminar ${miles(S.sel.size)} prestación(es) de la grilla del período ${per}? Las líneas que usen esos códigos quedarán sin valor de grilla. Queda registrado en la auditoría.`, "Eliminar", "peligro")) return;
      try { const r = await api("/api/valores/eliminar", { json: { os: S.os, ids: [...S.sel] } }); S.sel.clear(); toast(`${miles(r.eliminadas)} prestación(es) eliminadas`); contadores(); recargar(); } catch (err) { fallo(err); }
    };
  }
  $$("[data-ver]").forEach(b => b.onclick = () => { F.unidad = b.dataset.ver; F.esp = ""; F.tab = "prest"; S.pagina = 0; recargar(); });
  const aNum = t => Number(String(t).trim().replace(/\./g, "").replace(",", "."));
  $$("[data-uid]").forEach(i => {
    const boton = $(`[data-guardar="${i.dataset.uid}"]`);
    i.oninput = () => { const v = aNum(i.value); boton.disabled = !(v > 0) || Math.abs(v - Number(i.dataset.orig)) < 0.00005; };
    i.onkeydown = e => { if (e.key === "Enter" && !boton.disabled) boton.click(); };
    boton.onclick = async () => {
      const x = d.unidades.find(u => u.id === +i.dataset.uid), v = aNum(i.value);
      if (!await confirmar(`¿Cambiar «${x.tipo_unidad}» de ${x.especialidad} de ${pesos(x.valor)} a ${pesos(v)}? Se recalculan ${miles(x.prestaciones)} prestaciones del período ${per}.`, "Cambiar valor")) return;
      try { const r = await api("/api/unidades/" + x.id, { method: "PUT", json: { valor: v } }); toast(`Unidad actualizada · ${miles(r.recalculadas)} prestaciones recalculadas`); recargar(); } catch (err) { fallo(err); }
    };
  });
  $$("[data-fijo]").forEach(b => b.onclick = () => {
    const f = d.filas.find(x => x.id === +b.dataset.fijo);
    modal(`<h3>Cambiar valor fijo</h3><p>${esc(f.codigo || f.codigo_prestador)} · ${esc(f.descripcion)}</p>
      <form id="ffj"><label>Valor<input name="valor" value="${esc(String(f.valor).replace(".", ","))}" inputmode="decimal" required></label>
      <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Guardar</button></div></form>`);
    $("#ffj").onsubmit = async e => {
      e.preventDefault();
      try { await api("/api/valores/" + f.id, { method: "PUT", json: { valor: aNum(new FormData(e.target).get("valor")) } }); cerrarModal(); toast("Valor actualizado"); recargar(); } catch (err) { fallo(err); }
    };
  });
  $("#gBorrar").onclick = async () => {
    if (!await confirmar(`¿Eliminar la grilla ${per} de ${S.os}, con sus valores por unidad?`, "Eliminar", "peligro")) return;
    try { await api("/api/valores?" + qs({ os: S.os, periodo: per }), { method: "DELETE" }); S.filtros = {}; ir("valores"); } catch (err) { fallo(err); }
  };
};

/* ───────────── Bot EVWEB ───────────── */

VISTAS.bot = async () => {
  const o = S.me.obras[S.os];
  $("#subtitulo").textContent = "Extrae de EVWEB las prestaciones validadas. El rango se fragmenta en tramos de 9 días.";
  const hoy = new Date(), iso = d => d.toISOString().slice(0, 10);
  const ini = new Date(hoy.getFullYear(), hoy.getMonth(), 1, 12);
  $("#vista").innerHTML = `
    <div class="pasos">
      <div class="tarjeta"><h3>Parámetros</h3>
        <div class="rejilla">
          <label>Obra social<input value="${esc(o.nombre)}" disabled></label>
          <label>Estado de auditoría<input value="APROBADO EN OBRA SOCIAL" disabled></label>
          <label>Facturadas<input value="NO" disabled></label>
          <label>Fecha de carga desde<input type="date" id="bDesde" value="${iso(ini)}"></label>
          <label>Fecha de carga hasta<input type="date" id="bHasta" value="${iso(hoy)}"></label>
        </div>
        ${S.os === "SWISS" ? `<p class="suave">SWISS MEDICAL tiene dos códigos: el bot extrae primero 11062 (I.V.A.) y después 11060, y acumula ambos en Datos extraídos EVWEB.</p>` : ""}
        <p class="suave" id="bTramos"></p>
      </div>
      <div class="tarjeta"><h3>Credenciales EVWEB</h3>
        <div class="rejilla">
          <label>Usuario<input id="bUsu" autocomplete="off"></label>
          <label>Contraseña<input id="bCla" type="password" autocomplete="new-password"></label>
        </div>
        <p class="suave">Se usan solo para esta extracción; no se guardan.</p>
        <button class="btn primario" id="bIniciar">Iniciar extracción · ${NOMBRES[S.os]}</button>
      </div>
    </div>
    <div id="bEstado" class="bloque"></div>
    <div class="tarjeta"><h3>¿Ya tenés el Excel de EVWEB?</h3>
      <p class="suave">Podés cargar un «Exportar prácticas Excel» descargado a mano; queda guardado igual en Datos extraídos EVWEB.</p>
      <div class="fila"><input type="file" id="bArch" accept=".xlsx,.xls,.csv"><button class="btn" id="bImportar">Importar archivo</button></div>
    </div>`;
  const tramos = async () => {
    const r = await api("/api/evweb/tramos?" + qs({ desde: $("#bDesde").value, hasta: $("#bHasta").value }));
    $("#bTramos").innerHTML = r.tramos.length ? `<b>${r.tramos.length} tramo(s):</b> <span class="chips">${r.tramos.map(t => `<span>${t[0]} → ${t[1]}</span>`).join("")}</span>` : "Indicá un rango de fechas válido.";
  };
  $("#bDesde").onchange = $("#bHasta").onchange = tramos; tramos();

  const pintar = j => {
    const c = $("#bEstado"); if (!c) return;
    if (!j) { c.innerHTML = ""; return; }
    const [txt, pct] = j.progreso;
    const cab = j.estado === "corriendo" ? `<div class="aviso info" role="status"><span class="girando" aria-hidden="true"></span>${esc(NOMBRES[j.os])}: ${esc(txt)}</div>`
      : j.estado === "listo" ? `<div class="aviso ok" role="status">${ICO.ok}Extracción finalizada: ${miles(j.resultado.filas)} filas descargadas (${miles(j.resultado.nuevas)} nuevas) en ${j.resultado.descargados} de ${j.resultado.tramos} tramo(s). <a class="enlace" href="#" id="bVer">Ver datos extraídos</a></div>`
      : `<div class="aviso mal">Error: ${esc(j.error)}</div>`;
    c.innerHTML = `<div class="tarjeta">${cab}<div class="progreso"><div id="bBarra"></div></div>
      ${j.avisos.length ? `<div class="aviso">${j.avisos.map(esc).join("<br>")}</div>` : ""}<pre class="log">${esc(j.log.join("\n"))}</pre></div>`;
    $("#bBarra").style.width = Math.round(Math.min(pct, 1) * 100) + "%";
    if ($("#bVer")) $("#bVer").onclick = e => { e.preventDefault(); ir("evweb"); };
    $("#bIniciar").disabled = j.estado === "corriendo";
  };
  const seguir = id => {
    clearInterval(S.pollBot);
    const tick = async () => {
      try { const { job } = await api("/api/evweb/job?id=" + id); pintar(job); if (!job || job.estado !== "corriendo") { clearInterval(S.pollBot); contadores(); } } catch (e) { clearInterval(S.pollBot); }
    };
    tick(); S.pollBot = setInterval(tick, 3000);
  };
  const { job } = await api("/api/evweb/job");
  if (job) seguir(job.id);
  $("#bIniciar").onclick = async () => {
    try {
      const r = await api("/api/evweb/extraer", { json: { os: S.os, usuario: $("#bUsu").value, clave: $("#bCla").value, desde: $("#bDesde").value, hasta: $("#bHasta").value } });
      $("#bCla").value = ""; seguir(r.job);
    } catch (err) { fallo(err); }
  };
  $("#bImportar").onclick = async () => {
    const a = $("#bArch").files[0]; if (!a) return toast("Elegí el archivo", true);
    try { const r = await subir("/api/evweb/importar", { os: S.os }, a); toast(`${miles(r.filas)} filas leídas, ${miles(r.nuevas)} nuevas`); contadores(); } catch (err) { fallo(err); }
  };
};

/* ───────────── Datos extraídos EVWEB (solo consulta) ───────────── */

VISTAS.evweb = async () => {
  $("#subtitulo").textContent = "Información validada extraída de EVWEB. Solo consulta: no se puede modificar.";
  const F = S.filtros;
  const par = { os: S.os, q: F.q || "", fdesde: F.fdesde || "", fhasta: F.fhasta || "", prof: F.prof || "", nro: F.nro || "" };
  const d = await api("/api/evweb?" + qs({ ...par, limite: S.limite, desde: S.pagina * S.limite }));
  const cols = d.columnas.map(c => ({ k: c, t: c }));
  const fecha = t => t ? t.split("-").reverse().join("/") : "";
  $("#vista").innerHTML = `
    <div class="filtros">
      <label>Fecha desde<input type="date" id="fDesde" value="${esc(F.fdesde || "")}"></label>
      <label>Fecha hasta<input type="date" id="fHasta" value="${esc(F.fhasta || "")}"></label>
      ${filtrosBusqueda(F, d.profesionales)}
      ${paginador(d.total)}<span class="sep"></span>
      <a class="btn primario" href="/api/evweb/exportar?${qs(par)}">Exportar Excel</a>
      ${d.rango.n ? `<button class="btn peligro" id="evQuitar">Quitar datos EVWEB</button>` : ""}
    </div>
    ${tabla(cols, d.filas, { vacio: d.rango.n ? "Ninguna fila coincide con los filtros." : "Todavía no hay datos extraídos de EVWEB para esta obra social. Usá la sección Bot EVWEB." })}
    <p class="suave">${d.total ? "Hacé doble clic en una fila para ver todo su detalle. " : ""}${d.rango.n ? `En vista: ${miles(d.rango.n)} filas, prestaciones del ${fecha(d.rango.d)} al ${fecha(d.rango.h)}. ` : ""}El día 25 de cada mes se archivan los datos hasta el período ${esc(d.archivar_hasta)} y se quitan de esta vista; el administrador los descarga desde Inicio → Archivo.</p>
    ${d.extracciones.length ? `<p class="suave">Últimas extracciones: ${d.extracciones.slice(0, 6).map(e => `${esc(e.fecha)} (${esc(e.origen)}${e.desde ? ` ${esc(e.desde)}→${esc(e.hasta)}` : ""}: ${miles(e.filas)} filas, ${miles(e.nuevas)} nuevas)`).join(" · ")}</p>` : ""}`;
  const recargar = () => VISTAS.evweb().catch(fallo);
  if ($("#evQuitar")) $("#evQuitar").onclick = async () => {
    const ok = await confirmar(`ATENCIÓN: se van a borrar las ${miles(d.rango.n)} filas extraídas de EVWEB para ${NOMBRES[S.os]}. `
      + "No se puede deshacer desde la aplicación. Si no las borrás, se archivan solas el día 25. ¿Borrar todo ahora?", "Borrar todo", "peligro");
    if (!ok) return;
    try { const r = await api("/api/evweb?os=" + S.os, { method: "DELETE" }); toast(`${miles(r.filas)} filas de EVWEB borradas`); S.filtros = {}; contadores(); recargar(); } catch (err) { fallo(err); }
  };
  // Doble clic (o Enter con la fila enfocada) abre el detalle completo de la fila. Solo lectura.
  const detalle = i => {
    const f = d.filas[i]; if (!f) return;
    const campos = Object.entries(f).filter(([, v]) => String(v ?? "").trim() !== "");
    const vacios = Object.keys(f).length - campos.length;
    modal(`<h3>Detalle de la fila${f[d.columnas[0]] ? " · " + esc(f[d.columnas[0]]) : ""}</h3>
      <dl class="detalleFila">${campos.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
      ${vacios ? `<p class="suave">${vacios} campo(s) sin dato no se muestran.</p>` : ""}
      <div class="pie"><button class="btn primario" data-cerrar>Cerrar</button></div>`);
  };
  $$("#vista tbody tr").forEach(tr => {
    tr.tabIndex = 0;
    tr.title = "Doble clic para ver el detalle";
    tr.ondblclick = () => detalle(+tr.dataset.id);
    // preventDefault: sin esto, el mismo Enter "aprieta" el botón Cerrar que recibe el foco
    tr.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); detalle(+tr.dataset.id); } };
  });
  enlazarPaginador(recargar);
  $("#fDesde").onchange = e => { F.fdesde = e.target.value; S.pagina = 0; recargar(); };
  $("#fHasta").onchange = e => { F.fhasta = e.target.value; S.pagina = 0; recargar(); };
  enlazarBusqueda(F, () => VISTAS.evweb());
};

/* ───────────── líneas (pre-facturación y facturación) ───────────── */

const COLS_LINEA = [
  { k: "cruce", t: "Cruce", f: f => `<span class="et ${f.cruce === "OK" || f.cruce === "GRILLA" ? "ok" : f.cruce === "MANUAL" ? "avi" : "mal"}">${esc(f.cruce)}</span>` },
  { k: "periodo", t: "Período" }, { k: "nro_transaccion", t: "N° transacción" }, { k: "fecha_prestacion", t: "Fecha" },
  { k: "afiliado_numero", t: "N° afiliado" }, { k: "afiliado_nombre", t: "Afiliado" },
  { k: "cod_practica", t: "Cód. archivo" },
  { k: "cod_propuesto", t: "Cód. propuesto", f: f => f.codigos === "Difieren cód." ? `<b title="${esc(f.desc_propuesta || "")}">${esc(f.cod_propuesto)}</b>` : esc(f.cod_propuesto || f.cod_practica) },
  { k: "codigos", t: "Códigos", f: f => `<span class="et ${f.codigos === "Difieren cód." ? "avi" : "ok"}">${esc(f.codigos || "")}</span>` },
  { k: "descripcion", t: "Prestación" }, { k: "cantidad", t: "Cant.", num: true },
  { k: "cuenta", t: "Cuenta" }, { k: "matricula", t: "Matrícula" }, { k: "profesional", t: "Profesional" },
  { k: "especialidad", t: "Especialidad" }, { k: "categoria", t: "Cat." },
  { k: "valor_unit", t: "Valor unit.", num: true, f: f => f.valor_unit ? pesos(f.valor_unit) : `<span class="et mal">sin valor</span>` },
  { k: "total", t: "Total", num: true, f: f => pesos(f.total) },
  { k: "valor_archivo", t: "Total archivo", num: true, f: f => f.valor_archivo ? pesos(f.valor_archivo * (f.cantidad || 1)) : `<span class="suave">—</span>` },
  { k: "valor_grilla", t: "Valor grilla", num: true, f: f => {
    if (!f.valor_grilla) return `<span class="suave">sin grilla</span>`;
    const tg = f.valor_grilla * (f.cantidad || 1), dif = Math.abs(tg - (f.total || 0)) > Math.max(1, tg * 0.001);
    return dif ? `<span class="et avi" title="Difiere del total de la línea">${pesos(tg)}</span>` : pesos(tg);
  } },
  { k: "origen_valor", t: "Origen valor" }, { k: "observacion", t: "Observación" },
];

function editarLinea(f, recargar) {
  const campos = [["nro_transaccion", "N° transacción"], ["fecha_prestacion", "Fecha prestación (dd/mm/aaaa)"], ["periodo", "Período (MMAAAA)"],
    ["afiliado_numero", "N° afiliado"], ["afiliado_nombre", "Afiliado"], ["cod_practica", "Código de prestación"],
    ["descripcion", "Descripción"], ["cantidad", "Cantidad"], ["valor_unit", "Valor unitario"],
    ["cuenta", "Cuenta"], ["matricula", "Matrícula"], ["profesional", "Profesional"], ["cuit", "CUIT"],
    ["especialidad", "Especialidad"], ["categoria", "Categoría"], ["observacion", "Observación"]];
  modal(`<h3>Modificar línea · transacción ${esc(f.nro_transaccion)}</h3>
    <form id="fl"><div class="rejilla">${campos.map(([k, t]) => `<label>${t}<input name="${k}" value="${esc(f[k])}"></label>`).join("")}
      <label>Incremento % sobre el valor unitario<input name="incremento" id="lInc" inputmode="decimal" placeholder="Ej: 20 (negativo = descuento)"></label></div>
    <p class="suave" id="lIncVista"></p>
    <p><label class="enLinea"><input type="checkbox" id="auto" checked>
      Al cambiar cuenta o matrícula, completar el profesional desde el padrón; al cambiar código o categoría, tomar el valor de la grilla</label></p>
    <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Guardar</button></div></form>`);
  // Vista previa del incremento: valor actual → valor con el porcentaje aplicado
  const fl = $("#fl");
  const vistaInc = () => {
    const p = Number(String($("#lInc").value).trim().replace(",", ".")), base = Number(String(fl.elements.valor_unit.value).replace(",", "."));
    $("#lIncVista").textContent = p && base ? `Valor unitario ${pesos(base)} ${p > 0 ? "+" : "−"} ${Math.abs(p)} % = ${pesos(Math.round(base * (1 + p / 100) * 100) / 100)}. Queda anotado en la línea y en la auditoría.` : "";
  };
  $("#lInc").oninput = vistaInc; fl.elements.valor_unit.oninput = vistaInc;
  $("#fl").onsubmit = async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target)), cambios = {};
    for (const [k] of campos) if (String(d[k]).trim() !== String(f[k] ?? "").trim()) cambios[k] = d[k];
    if (String(d.incremento || "").trim()) cambios.incremento = String(d.incremento).trim().replace(",", ".");
    if (!Object.keys(cambios).length) return cerrarModal();
    try { await api("/api/lineas/" + f.id, { method: "PUT", json: { cambios, autocompletar: $("#auto").checked } }); cerrarModal(); toast("Línea actualizada"); recargar(); } catch (err) { fallo(err); }
  };
}

function edicionMasiva(recargar) {
  const campos = [["cuenta", "Cuenta"], ["matricula", "Matrícula"], ["cod_practica", "Código de prestación"], ["valor_unit", "Valor unitario"], ["incremento", "Incremento % sobre el valor (ej: 20)"], ["categoria", "Categoría"], ["periodo", "Período (MMAAAA)"]];
  modal(`<h3>Modificar ${S.sel.size} línea(s) seleccionada(s)</h3><p class="suave">Completá solo lo que quieras cambiar; lo vacío no se toca.</p>
    <form id="fm"><div class="rejilla">${campos.map(([k, t]) => `<label>${t}<input name="${k}"></label>`).join("")}</div>
    <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Aplicar</button></div></form>`);
  $("#fm").onsubmit = async e => {
    e.preventDefault();
    const cambios = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => String(v).trim() !== ""));
    if (!Object.keys(cambios).length) return cerrarModal();
    try { const r = await api("/api/lineas/accion", { json: { os: S.os, accion: "editar", ids: [...S.sel], cambios } }); cerrarModal(); informe(r, "modificada(s)"); recargar(); } catch (err) { fallo(err); }
  };
}

function informe(r, verbo) {
  if (!r.n_omitidas) return toast(`${miles(r.hechas)} línea(s) ${verbo}`);
  modal(`<h3>${miles(r.hechas)} línea(s) ${verbo} · ${miles(r.n_omitidas)} omitida(s)</h3>
    <div class="tabla tablaCorta"><table><thead><tr><th>Transacción</th><th>Motivo</th></tr></thead><tbody>
    ${r.omitidas.map(o => `<tr><td>${esc(o.nro)}</td><td>Falta: ${esc(o.faltan.join(", "))}</td></tr>`).join("")}</tbody></table></div>
    <div class="pie"><button class="btn primario" data-cerrar>Entendido</button></div>`);
}

async function accion(nombre, ids, recargar, verbo, extra = {}) {
  try {
    const r = await api("/api/lineas/accion", { json: { os: S.os, accion: nombre, ids, ...extra } });
    ids.forEach(i => S.sel.delete(i));
    if (r.fuente && !r.n_omitidas) toast(`${miles(r.hechas)} línea(s) enviada(s) a Facturación · ${miles(r.con_fuente)} con el valor ${r.fuente === "grilla" ? "de la grilla" : "del archivo"}${r.sin_fuente ? ` · ${miles(r.sin_fuente)} conservaron su valor` : ""}`);
    else informe(r, verbo);
    contadores(); recargar();
  } catch (err) { fallo(err); }
}

/* Al procesar se pregunta qué valor total queda: el del archivo validado o el de la grilla. */
function procesarConFuente(ids, recargar) {
  const sel = S.filas.filter(f => ids.includes(f.id));
  const suma = k => sel.reduce((t, f) => t + (f[k] ? f[k] * (f.cantidad || 1) : 0), 0);
  const cuenta = k => sel.filter(f => f[k] > 0).length;
  const fuera = ids.length - sel.length;
  modal(`<h3>Procesar ${miles(ids.length)} línea(s): ¿qué valor total tomar?</h3>
    <div class="opciones">
      <button class="opcion" data-fuente="archivo" ${cuenta("valor_archivo") || fuera ? "" : "disabled"}>
        <b>Valor total del archivo</b><span>${pesos(suma("valor_archivo"))}</span>
        <small>${miles(cuenta("valor_archivo"))} de ${miles(sel.length)} línea(s) en pantalla traen valor en el archivo validado</small></button>
      <button class="opcion" data-fuente="grilla" ${cuenta("valor_grilla") || fuera ? "" : "disabled"}>
        <b>Valor total de la grilla</b><span>${pesos(suma("valor_grilla"))}</span>
        <small>${miles(cuenta("valor_grilla"))} de ${miles(sel.length)} línea(s) en pantalla tienen valor en la grilla</small></button>
      <button class="opcion" data-fuente="actual">
        <b>Valor actual de la línea</b><span>${pesos(sel.reduce((t, f) => t + (f.total || 0), 0))}</span>
        <small>Procesa cada línea con el total que muestra ahora, sin cambiarlo</small></button>
    </div>
    <p class="suave">Las líneas que no tengan valor en la fuente elegida, y las que tienen un valor cargado a mano, conservan el valor que muestran ahora.${fuera ? ` Hay ${miles(fuera)} línea(s) seleccionada(s) en otras páginas: los totales de arriba son solo de las que están en pantalla.` : ""}</p>
    <div class="pie"><button class="btn" data-cerrar>Cancelar</button></div>`);
  $$(".opcion").forEach(b => b.onclick = async () => {
    cerrarModal();
    const fuente = b.dataset.fuente;
    // Si alguna línea tiene código propuesto distinto del archivo, se pregunta cuál queda
    let r = { difieren: 0, cambios: [] };
    try { r = await api("/api/lineas/resumen", { json: { os: S.os, ids } }); } catch (err) { return fallo(err); }
    if (!r.difieren) return accion("procesar", ids, recargar, "enviada(s) a Facturación", { fuente, codigo: "archivo" });
    modal(`<h3>¿Qué código de prestación dejar?</h3>
      <p>En ${miles(r.difieren)} de las ${miles(ids.length)} línea(s) el código propuesto difiere del código del archivo validado.</p>
      <div class="opciones">
        <button class="opcion" data-codigo="archivo"><b>Código del archivo</b><small>Deja el código tal como vino en el archivo validado</small></button>
        <button class="opcion" data-codigo="propuesto"><b>Código propuesto</b><small>Reemplaza el código por el propuesto en esas ${miles(r.difieren)} línea(s)</small></button>
      </div>
      <p class="suave">Cambios propuestos: ${esc(r.cambios.map(([k, n]) => `${k} (${miles(n)})`).join(" · "))}. El valor de la línea no cambia con esta elección.</p>
      <div class="pie"><button class="btn" data-cerrar>Cancelar</button></div>`);
    $$("[data-codigo]").forEach(c => c.onclick = () => { cerrarModal(); accion("procesar", ids, recargar, "enviada(s) a Facturación", { fuente, codigo: c.dataset.codigo }); });
  });
}

async function vistaLineas(estado, cfg) {
  const F = S.filtros;
  const par = { os: S.os, estado, periodo: F.periodo || "", q: F.q || "", cruce: F.cruce || "", prof: F.prof || "", nro: F.nro || "", rf: F.rf || "", afil: F.afil || "", cods: F.cods || "", valor: F.valor || "" };
  const conIva = estado !== "template";
  const opcCond = (lista, sel) => lista.map(c => `<option value="${esc(c)}" ${c === sel ? "selected" : ""}>${c === "-" ? "Sin dato" : esc(c)}</option>`).join("");
  const d = await api("/api/lineas?" + qs({ ...par, limite: S.limite, desde: S.pagina * S.limite }));
  S.filas = d.filas;
  const colsLineas = ordenarCols([...COLS_LINEA.slice(0, -1),
    { k: "resp_fiscal", t: "Cond. profesional" },
    ...(d.cond_afil.some(c => c !== "-") ? [{ k: "cond_afiliado", t: "Cond. afiliado" }] : []),
    { k: "iva", t: "IVA", f: f => f.iva === null || f.iva === undefined ? "" : `<span class="et ${f.iva ? "ok" : ""}">${esc(f.iva)}</span>` },
    COLS_LINEA[COLS_LINEA.length - 1]], "lineas");
  const recargar = () => vistaLineas(estado, cfg).catch(fallo);
  $("#lista").innerHTML = `
    <div class="banda"><div class="kpis"><div class="kpi"><span>Líneas</span><b>${miles(d.total)}</b></div>
      <div class="kpi"><span>Importe</span><b>${pesos(d.importe)}</b></div>
      ${estado === "prefact" ? `<div class="kpi"><span>Listas para procesar</span><b>${miles(d.listas)}</b></div><div class="kpi"><span>A revisar</span><b>${miles(d.total - d.listas)}</b></div>` : ""}
      <div class="kpi"><span>Seleccionadas</span><b id="nSel">0</b></div></div>
      <div class="acciones">${cfg.masivas}${conIva ? `<button class="btn" data-masiva id="mReval">Revalorizar seleccionadas</button><button class="btn" data-masiva id="mIva">Asignar IVA</button>` : ""}</div></div>
    <div class="filtros">
      <label>Período<select id="fPer"><option value="">Todos</option>${d.periodos.map(p => `<option ${p === F.periodo ? "selected" : ""}>${p}</option>`).join("")}</select></label>
      ${estado === "prefact" ? `<label>Cruce<select id="fCru"><option value="">Todos</option>${["OK", ...(S.os === "SWISS" ? ["GRILLA"] : []), "MANUAL", "SIN EVWEB", "SIN PADRON"].map(c => `<option ${c === F.cruce ? "selected" : ""}>${c}</option>`).join("")}</select></label>` : ""}
      ${d.cond_prof.some(c => c !== "-") ? `<label>Condición del profesional<select id="fRf"><option value="">Todas</option>${opcCond(d.cond_prof, F.rf)}</select></label>` : ""}
      ${d.cond_afil.some(c => c !== "-") ? `<label>Condición del afiliado<select id="fAfil"><option value="">Todas</option>${opcCond(d.cond_afil, F.afil)}</select></label>` : ""}
      <label>Valor unitario<select id="fValor"><option value="">Todos</option><option value="sin" ${F.valor === "sin" ? "selected" : ""}>Sin valor (${miles(d.sin_valor)})</option><option value="con" ${F.valor === "con" ? "selected" : ""}>Con valor</option></select></label>
      ${d.difieren || F.cods ? `<label>Códigos<select id="fCods"><option value="">Todos</option><option value="difieren" ${F.cods === "difieren" ? "selected" : ""}>Difieren cód. (${miles(d.difieren)})</option><option value="coinciden" ${F.cods === "coinciden" ? "selected" : ""}>Coinciden códigos</option></select></label>` : ""}
      ${filtrosBusqueda(F, d.profesionales)}
      ${paginador(d.total)}<span class="sep"></span>
      ${conIva && d.total ? `<button class="btn" id="selFiltradas">Seleccionar las ${miles(d.total)} filtradas</button>` : ""}
      <a class="btn" href="/api/lineas/exportar?${qs(par)}">Exportar Excel</a>
      ${ordenGuardado("lineas").length ? `<button class="btn" id="colsReset">Restablecer columnas</button>` : ""}
    </div>
    <p class="suave sinMargen">Para cambiar el orden de las columnas, arrastrá el encabezado de una columna hasta el lugar donde la querés. El orden queda guardado en este navegador.</p>
    ${tabla(colsLineas, d.filas, { sel: true, mover: true, vacio: (F.prof || F.nro || F.q || F.periodo || F.cruce || F.rf || F.afil) ? "Ninguna línea coincide con los filtros." : cfg.vacio, acciones: cfg.acciones })}`;
  enlazarPaginador(recargar);
  enlazarColumnas("lineas", colsLineas, recargar);
  if ($("#fRf")) $("#fRf").onchange = e => { F.rf = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  if ($("#fAfil")) $("#fAfil").onchange = e => { F.afil = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  if ($("#fCods")) $("#fCods").onchange = e => { F.cods = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  $("#fValor").onchange = e => { F.valor = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  // Selección masiva: todas las líneas que cumplen los filtros, no solo las de la página
  if ($("#selFiltradas")) $("#selFiltradas").onclick = async () => {
    try {
      const ids = await traerIds();
      S.sel.clear(); ids.forEach(i => S.sel.add(i));
      toast(`${miles(ids.length)} línea(s) seleccionada(s)`); repintarSeleccion();   // sin volver a dibujar la tabla
    } catch (err) { fallo(err); }
  };
  // Revalorización en bloque: volver a valorizar, asignar un valor o aplicar un incremento
  if ($("#mReval")) $("#mReval").onclick = () => {
    const n = S.sel.size;
    modal(`<h3>Revalorizar ${miles(n)} línea(s) seleccionada(s)</h3>
      <h4 class="sinMargen">1 · Revalorizar automáticamente</h4>
      <p class="suave">Recalcula cada línea con lo que está cargado ahora y reemplaza también los valores puestos a mano.</p>
      <div class="fila">
        <button type="button" class="btn primario" data-rv="grilla">Revalorizar según grilla</button>
        <button type="button" class="btn primario" data-rv="evweb">Revalorizar según EVWEB</button>
      </div>
      <p class="suave"><b>Según grilla</b>: toma categoría y especialidad del padrón y el valor de la grilla y de «Otros». <b>Según EVWEB</b>: además vuelve a buscar cada transacción en los datos extraídos de EVWEB, toma de ahí el profesional (cuenta, matrícula, especialidad y categoría del padrón) y actualiza el cruce.</p>
      <h4>2 · O asignar un valor a mano</h4>
      <form id="frv"><div class="rejilla">
        <label>Asignar este valor unitario a todas<input name="valor_unit" inputmode="decimal" placeholder="Ej: 42680,25"></label>
        <label>O aplicar un incremento % sobre el valor de cada una<input name="incremento" inputmode="decimal" placeholder="Ej: 20 (negativo = descuento)"></label></div>
        <p class="suave">Completá uno solo de los dos campos. El total de cada línea se recalcula con su cantidad. Queda registrado en la auditoría.</p>
        <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Aplicar valor</button></div></form>`);
    $$("[data-rv]").forEach(b => b.onclick = async () => {
      const modo = b.dataset.rv;
      cerrarModal();
      try {
        const r = await api("/api/lineas/accion", { json: { os: S.os, accion: "revalorizar", modo, ids: [...S.sel] } });
        contadores(); recargar();
        modal(`<h3>Revalorización ${modo === "evweb" ? "según EVWEB" : "según grilla"} terminada</h3>
          <dl class="detalleFila">
            ${modo === "evweb" ? `<div><dt>Resultado del cruce</dt><dd>${esc(Object.entries(r.por_cruce).map(([k, v]) => `${k}: ${miles(v)}`).join(" · "))}</dd></div>` : ""}
            <div><dt>Revalorizadas</dt><dd>${miles(r.hechas)}</dd></div><div><dt>Con cambios</dt><dd>${miles(r.cambiaron)}</dd></div>
            <div><dt>Sin cambios</dt><dd>${miles(r.sin_cambio)}</dd></div><div><dt>Sin valor (no se tocaron)</dt><dd>${miles(r.n_omitidas)}</dd></div>
            <div><dt>Importe de las que cambiaron</dt><dd>${pesos(r.importe_antes)} → ${pesos(r.importe_despues)}</dd></div>
          </dl>
          <div class="pie"><button class="btn primario" data-cerrar>Cerrar</button></div>`);
      } catch (err) { fallo(err); }
    });
    $("#frv").onsubmit = async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target)), v = String(d.valor_unit).trim(), inc = String(d.incremento).trim();
      if (!v && !inc) return toast("Completá el valor o el incremento", true);
      if (v && inc) return toast("Completá solo uno: valor o incremento", true);
      const cambios = v ? { valor_unit: v } : { incremento: inc.replace(",", ".") };
      try { const r = await api("/api/lineas/accion", { json: { os: S.os, accion: "editar", ids: [...S.sel], cambios } }); cerrarModal(); informe(r, v ? "con el valor asignado" : "con el incremento aplicado"); contadores(); recargar(); } catch (err) { fallo(err); }
    };
  };
  // IVA en bloque: 1 = calcula IVA, 0 = no calcula IVA
  if ($("#mIva")) $("#mIva").onclick = () => {
    modal(`<h3>Asignar IVA a ${miles(S.sel.size)} línea(s)</h3>
      <p class="suave">Se cambia solo el IVA de las líneas seleccionadas. Queda registrado en la auditoría.</p>
      <div class="opciones">
        <button class="opcion" data-iva="1"><b>1 · Calcula IVA</b><span>El template lleva IVA en estas líneas.</span></button>
        <button class="opcion" data-iva="0"><b>0 · No calcula IVA</b><span>El template va sin IVA en estas líneas.</span></button>
      </div>
      <div class="pie"><button class="btn" data-cerrar>Cancelar</button></div>`);
    $$("[data-iva]").forEach(b => b.onclick = () => { cerrarModal(); accion("iva", [...S.sel], recargar, "con IVA " + b.dataset.iva, { iva: +b.dataset.iva }); });
  };
  $("#fPer").onchange = e => { F.periodo = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  if ($("#fCru")) $("#fCru").onchange = e => { F.cruce = e.target.value; S.pagina = 0; S.sel.clear(); recargar(); };
  enlazarBusqueda(F, () => vistaLineas(estado, cfg));
  const traerIds = async () => (await api("/api/lineas?" + qs({ ...par, solo_ids: 1 }))).ids;
  const repintarSeleccion = enlazarSeleccion(() => { $("#nSel").textContent = miles(S.sel.size); $$("[data-masiva]").forEach(b => b.disabled = S.sel.size === 0); },
    { total: d.total, traerIds });
  const fila = id => d.filas.find(f => f.id === +id);
  $$("[data-editar]").forEach(b => b.onclick = () => editarLinea(fila(b.dataset.editar), recargar));
  $$("[data-eliminar]").forEach(b => b.onclick = async () => { if (await confirmar("¿Eliminar esta línea?", "Eliminar", "peligro")) accion("eliminar", [+b.dataset.eliminar], recargar, "eliminada(s)"); });
  $$("[data-procesar]").forEach(b => b.onclick = () => procesarConFuente([+b.dataset.procesar], recargar));
  $$("[data-rechazar]").forEach(b => b.onclick = () => accion("rechazar", [+b.dataset.rechazar], recargar, "devuelta(s) a Pre-facturación"));
  cfg.enlazar(recargar, d);
}

VISTAS.prefact = async () => {
  $("#subtitulo").textContent = "Cruza el archivo de prestaciones validadas con lo extraído de EVWEB por número de transacción.";
  $("#vista").innerHTML = `
    <div class="tarjeta bloque"><h3>Nueva pre-facturación · ${NOMBRES[S.os]}</h3>
      <div class="fila">
        <label>Archivo de prestaciones validadas<input type="file" id="pArch" accept=".xlsx,.xls,.csv"></label>
        <label>Período de pre-facturación (MMAAAA)<input id="pPer" value="${periodoPorDefecto()}" maxlength="6" size="8"></label>
        ${S.os === "SWISS"
          ? `<button class="btn primario" id="pIniciar" data-modo="grilla">Cruzar y valorizar según grilla</button>
             <button class="btn primario" id="pIniciar2" data-modo="evweb">Cruzar y validar según EVWEB</button>`
          : `<button class="btn primario" id="pIniciar" data-modo="evweb">Comenzar a prefacturar</button>`}
        <span class="sep"></span>
        <button class="btn peligro" id="pReiniciar">Reiniciar</button>
      </div>
      ${S.os === "SWISS" ? `<p class="suave sinMargen">El reporte de SWISS MEDICAL no viene valorizado. <b>Según grilla</b>: toma el profesional por el CUIT del efector y valoriza con la grilla de valores cargada en «Valores», sin usar EVWEB. <b>Según EVWEB</b>: además cruza cada transacción con lo extraído de EVWEB (códigos 11062 y 11060) y marca las que no estén; el valor sale igual de la base.</p>` : ""}
      <div id="pRes"></div>
    </div><div id="lista"></div>`;
  const etiquetas = {};
  $$("#pIniciar, #pIniciar2").forEach(b => { etiquetas[b.id] = b.textContent; });
  const importar = async (a, periodo, soloNuevas, modo) => {
    const botones = $$("#pIniciar, #pIniciar2");
    const b = botones.find(x => x.dataset.modo === modo) || botones[0];
    botones.forEach(x => { x.disabled = true; });
    b.setAttribute("aria-busy", "true"); b.textContent = "Cruzando…";
    try {
      const r = await subir("/api/prefacturar", { os: S.os, periodo, solo_nuevas: soloNuevas ? "1" : "", modo }, a);
      $("#pRes").innerHTML = `<div class="aviso sinMargen ${r.sin_evweb || r.sin_padron ? "" : "ok"}">
        ${r.modo ? (r.modo === "grilla" ? "Cruce y valorización según grilla · " : "Cruce y validación según EVWEB · ") : ""}${miles(r.insertadas)} línea(s) incorporadas de ${miles(r.total)} del archivo · ${r.modo === "grilla" ? "con profesional" : "cruce OK"}: ${miles(r.ok)}${r.modo === "grilla" ? "" : ` · sin EVWEB: ${miles(r.sin_evweb)}`} · sin padrón: ${miles(r.sin_padron)} · sin valor${r.modo ? " (a revisar)" : ""}: ${miles(r.sin_valor)}
        ${r.duplicadas ? ` · ya cargadas antes (omitidas): ${miles(r.duplicadas)}` : ""}${r.anuladas ? ` · anuladas (omitidas): ${miles(r.anuladas)}` : ""}
        ${r.grilla_periodo ? ` · grilla usada: ${r.grilla_periodo}` : " · sin grilla de valores cargada"}
        · ahora hay ${miles(r.en_prefacturacion)} línea(s) acumuladas en pre-facturación</div>`;
      contadores(); cargar();
    } catch (err) {
      const dup = err.estado === 409 && err.datos && err.datos.duplicado;
      if (!dup) fallo(err);
      else {
        // El archivo trae transacciones ya cargadas: no se importó nada
        $("#pRes").innerHTML = `<div class="aviso mal sinMargen" role="alert">${esc(err.message)}</div>`;
        modal(`<h3>Importación frenada: hay transacciones repetidas</h3>
          <p>${esc(err.message)}</p>
          <dl class="detalleFila">
            <div><dt>Filas del archivo</dt><dd>${miles(dup.total)}</dd></div>
            <div><dt>Ya cargadas</dt><dd>${miles(dup.duplicadas)}</dd></div>
            <div><dt>Nuevas</dt><dd>${miles(dup.nuevas)}</dd></div>
            <div><dt>Dónde están las repetidas</dt><dd>${esc(Object.entries(dup.donde).map(([k, v]) => `${miles(v)} en ${k}`).join(" · "))}</dd></div>
            <div><dt>Ejemplos de transacciones</dt><dd>${esc(dup.ejemplos.join(", "))}</dd></div>
          </dl>
          <p class="suave">${dup.nuevas ? "Si es un archivo distinto que se superpone con uno anterior, podés importar solo las transacciones nuevas; las repetidas se dejan como están." : "Todas las transacciones del archivo ya estaban cargadas: no hay nada nuevo para importar."}</p>
          <div class="pie"><button class="btn" data-cerrar>Cerrar</button>
            ${dup.nuevas ? `<button class="btn primario" id="soloNuevas">Importar solo las ${miles(dup.nuevas)} nuevas</button>` : ""}</div>`);
        if ($("#soloNuevas")) $("#soloNuevas").onclick = () => { cerrarModal(); importar(a, periodo, true, modo); };
      }
    }
    botones.forEach(x => { x.disabled = false; x.textContent = etiquetas[x.id]; });
    b.removeAttribute("aria-busy");
  };
  $$("#pIniciar, #pIniciar2").forEach(b => b.onclick = () => {
    const a = $("#pArch").files[0]; if (!a) return toast("Elegí el archivo de prestaciones validadas", true);
    importar(a, $("#pPer").value, false, b.dataset.modo);
  });
  // Reiniciar: borra lo que está en pre-facturación para empezar de nuevo
  $("#pReiniciar").onclick = async () => {
    const ok = await confirmar(`ATENCIÓN: se van a borrar TODAS las líneas que están en Pre-facturación de ${NOMBRES[S.os]}, `
      + "incluidas las correcciones hechas a mano. Lo que ya está en Facturación o en templates no se toca. ¿Reiniciar?", "Reiniciar", "peligro");
    if (!ok) return;
    try {
      const r = await api("/api/prefacturar/reiniciar", { json: { os: S.os } });
      S.sel.clear(); S.filtros = {}; S.pagina = 0;
      $("#pRes").innerHTML = `<div class="aviso info sinMargen" role="status">Pre-facturación reiniciada: se borraron ${miles(r.lineas)} línea(s) por ${pesos(r.importe)}. Podés volver a subir los archivos.</div>`;
      contadores(); cargar();
    } catch (err) { fallo(err); }
  };
  const cargar = () => vistaLineas("prefact", {
    vacio: "No hay líneas en pre-facturación. Subí el archivo de prestaciones validadas y presioná «Comenzar a prefacturar».",
    masivas: `<button class="btn ok" data-masiva id="mProc">Procesar seleccionadas</button>
      <button class="btn" data-masiva id="mEdit">Modificar seleccionadas</button>
      <button class="btn peligro" data-masiva id="mElim">Eliminar seleccionadas</button>`,
    acciones: f => `<button class="btn mini" data-editar="${f.id}">Modificar</button>
      <button class="btn mini peligro" data-eliminar="${f.id}">Eliminar</button>
      <button class="btn mini ok" data-procesar="${f.id}">Procesar</button>`,
    enlazar: recargar => {
      $("#mProc").onclick = () => procesarConFuente([...S.sel], recargar);
      $("#mEdit").onclick = () => edicionMasiva(recargar);
      $("#mElim").onclick = async () => { if (await confirmar(`¿Eliminar ${S.sel.size} línea(s)?`, "Eliminar", "peligro")) accion("eliminar", [...S.sel], recargar, "eliminada(s)"); };
    },
  });
  await cargar();
};

VISTAS.fact = async () => {
  $("#subtitulo").textContent = "Líneas procesadas desde Pre-facturación. Seleccioná y generá el template.";
  $("#vista").innerHTML = `<div id="lista"></div>`;
  await vistaLineas("facturacion", {
    vacio: "No hay líneas en facturación. Procesalas desde Pre-facturación.",
    masivas: `<button class="btn primario" data-masiva id="mTpl">Generar template</button>
      <button class="btn" data-masiva id="mEdit">Modificar seleccionadas</button>
      <button class="btn peligro" data-masiva id="mRech">Rechazar seleccionadas</button>`,
    acciones: f => `<button class="btn mini" data-editar="${f.id}">Modificar</button>
      <button class="btn mini peligro" data-rechazar="${f.id}">Rechazar</button>`,
    enlazar: recargar => {
      $("#mEdit").onclick = () => edicionMasiva(recargar);
      $("#mRech").onclick = () => accion("rechazar", [...S.sel], recargar, "devuelta(s) a Pre-facturación");
      $("#mTpl").onclick = async () => {
        if (!await confirmar(`¿Generar el template con ${S.sel.size} línea(s)?`, "Generar template")) return;
        try {
          const r = await api("/api/templates", { json: { os: S.os, ids: [...S.sel] } });
          S.sel.clear(); contadores();
          modal(`<h3>Template generado</h3><p><b>${esc(r.nombre)}</b> · ${miles(r.filas)} filas</p>
            <div class="pie"><button class="btn" data-cerrar>Seguir acá</button><a class="btn" href="/api/templates/${r.id}/descargar">Descargar</a>
            <button class="btn primario" id="irTpl">Ir a Templates</button></div>`);
          $("#irTpl").onclick = () => { cerrarModal(); ir("templates"); };
          recargar();
        } catch (err) { fallo(err); }
      };
    },
  });
};

/* ───────────── Templates ───────────── */

VISTAS.templates = async () => {
  $("#subtitulo").textContent = "Templates de importación generados desde Facturación.";
  const { filas } = await api("/api/templates?os=" + S.os);
  const cols = [{ k: "nombre", t: "Template", f: f => `<b>${esc(f.nombre)}</b>` }, { k: "periodo", t: "Período" }, { k: "fecha", t: "Generado" },
    { k: "filas", t: "Filas", num: true, f: f => miles(f.filas) }, { k: "total", t: "Importe", num: true, f: f => pesos(f.total) }];
  $("#vista").innerHTML = tabla(cols, filas, { vacio: "Todavía no se generaron templates para esta obra social.",
    acciones: f => `<a class="btn mini primario" href="/api/templates/${f.id}/descargar">Descargar</a>
      <button class="btn mini peligro" data-deshacer="${f.id}">Deshacer</button>` });
  $$("[data-deshacer]").forEach(b => b.onclick = async () => {
    const t = filas.find(f => f.id === +b.dataset.deshacer);
    if (!await confirmar(`¿Deshacer ${t.nombre}? Sus ${t.filas} líneas vuelven a Facturación y el template se elimina.`, "Deshacer", "peligro")) return;
    try { await api("/api/templates/" + t.id, { method: "DELETE" }); ir("templates"); } catch (err) { fallo(err); }
  });
};

/* ───────────── Presentaciones ───────────── */

VISTAS.present = async () => {
  const link = S.me.links[S.os];
  if (S.os === "AVALIAN") {
    $("#subtitulo").textContent = "AVALIAN no requiere conversión: la presentación se hace directamente en el portal.";
    $("#vista").innerHTML = `<div class="tarjeta"><h3>Portal de prestadores AVALIAN</h3>
      <p><a class="enlace" href="${esc(link)}" target="_blank" rel="noopener noreferrer">${esc(link)}</a></p>
      <a class="btn primario" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Ir a AVALIAN</a></div>`;
    return;
  }
  const galeno = S.os === "GALENO", swiss = S.os === "SWISS", conVal = galeno || swiss;
  $("#subtitulo").textContent = galeno
    ? "Convierte el archivo de facturación «PrestacionesExport» al formato PlanillaPrestaciones de GALENO."
    : swiss ? "Agrega al «PrestacionesExport» la matrícula (MP) y la columna Total: honorario menos coseguro, con IVA cuando corresponde."
    : "Agrega al «PrestacionesExport» la columna MP (matrícula del padrón) a continuación de Matricula.";
  $("#vista").innerHTML = `
    <div class="tarjeta bloque"><h3>1 · Conversor ${NOMBRES[S.os]}</h3>
      <div class="fila">
        <label>Archivo «PrestacionesExport»<input type="file" id="cArch" accept=".xlsx,.xls,.csv"></label>
        <label>Período (MMAAAA)<input id="cPer" value="${periodoPorDefecto()}" maxlength="6" size="8"></label>
        <label>N° de factura (opcional)<input id="cFac" placeholder="0005-00004519" size="16"></label>
        ${conVal ? `<label>${galeno ? "Archivo validado de Galeno (coseguros, opcional)" : "Archivo de Swiss Medical tal como sale de la obra social (coseguros)"}<input type="file" id="cVal" accept=".xlsx,.xls,.csv"></label>` : ""}
        <button class="btn primario" id="cIniciar">Iniciar conversor</button>
      </div>
      <p class="suave">Si el export trae varias obras sociales, indicá el N° de factura de ${NOMBRES[S.os]} para convertir solo esas filas.${galeno ? " El importe del anexo es el total menos el coseguro de cada transacción; los coseguros se toman del archivo validado cargado en Pre-facturación, o del que subas acá." : ""}${swiss ? " Al archivo de facturación se le agregan dos columnas: MP (matrícula del padrón) al lado de Matricula, y Total a continuación de IVA = Honorarios + IVA − Coseguro. El IVA es el 10,5 % del honorario cuando la columna IVA vale 1. El coseguro se busca por número de transacción en el archivo de Swiss: el que subas acá o, si no subís ninguno, el que ya esté cargado en Pre-facturación." : ""}</p>
      <div id="cRes"></div>
    </div>
    <div class="tarjeta"><h3>${swiss ? "2 · Descargar el archivo de facturación modificado" : "2 · Descargar y presentar"}</h3>
      <div class="fila"><button class="btn ok" id="cDesc" disabled>${galeno ? "Descargar Anexo de prestaciones" : "Descargar archivo convertido"}</button>
      ${link ? `<a class="enlace" href="${esc(link)}" target="_blank" rel="noopener noreferrer">${esc(link)}</a>` : ""}</div>
      ${link ? `<p class="suave">Al descargar se abre el portal de ${NOMBRES[S.os]} en otra pestaña.</p>` : ""}
    </div>`;
  let listo = null;
  $("#cIniciar").onclick = async () => {
    const a = $("#cArch").files[0]; if (!a) return toast("Elegí el archivo PrestacionesExport", true);
    const b = $("#cIniciar"); b.disabled = true; b.textContent = "Convirtiendo…";
    try {
      const fd = new FormData(); fd.append("periodo", $("#cPer").value); fd.append("factura", $("#cFac").value); fd.append("archivo", a);
      if ($("#cVal") && $("#cVal").files[0]) fd.append("validado", $("#cVal").files[0]);
      const r = await api("/api/presentaciones/" + S.os, { method: "POST", body: fd, crudo: true });
      const nombre = decodeURIComponent((r.headers.get("Content-Disposition") || "").split("''")[1] || "convertido.xlsx");
      listo = { blob: await r.blob(), nombre };
      const sinN = +r.headers.get("X-Sin-MP-N") || 0, sin = decodeURIComponent(r.headers.get("X-Sin-MP") || "");
      $("#cRes").innerHTML = `<div class="aviso ok sinMargen" role="status">${ICO.ok}${miles(r.headers.get("X-Filas"))} filas convertidas → <b>${esc(nombre)}</b></div>
        ${conVal ? `<div class="aviso info">Coseguros descontados: ${pesos(r.headers.get("X-Coseguro-Total"))} en ${miles(r.headers.get("X-Coseguro-Filas"))} fila(s).</div>` : ""}
        ${swiss ? `<div class="aviso info">Honorarios ${pesos(r.headers.get("X-Honorarios"))} + IVA ${pesos(r.headers.get("X-Iva-Total"))} (${miles(r.headers.get("X-Con-Iva"))} filas con IVA 1) − coseguros ${pesos(r.headers.get("X-Coseguro-Total"))} = <b>Total ${pesos(r.headers.get("X-Total"))}</b></div>` : ""}
        ${conVal && +r.headers.get("X-Sin-Cruce-N") ? `<div class="aviso">${miles(r.headers.get("X-Sin-Cruce-N"))} transacción(es) del export no están en el archivo validado (ej: ${esc(decodeURIComponent(r.headers.get("X-Sin-Cruce") || ""))}): en esas filas no se descontó coseguro. Subí el archivo validado de ese período y volvé a convertir.</div>` : ""}
        ${conVal && r.headers.get("X-Excedidos") ? `<div class="aviso mal">El coseguro supera al importe en: ${esc(decodeURIComponent(r.headers.get("X-Excedidos")))}. Esas filas quedaron en 0; revisalas.</div>` : ""}
        ${+r.headers.get("X-Sin-Esp-N") ? `<div class="aviso">${r.headers.get("X-Sin-Esp-N")} cuenta(s) sin especialidad en el padrón: ${esc(decodeURIComponent(r.headers.get("X-Sin-Esp") || ""))}. La columna Especialidad queda vacía en esas filas.</div>` : ""}
        ${sinN ? `<div class="aviso">${sinN} cuenta(s) sin matrícula (MP) en el padrón: ${esc(sin)}${sinN > 60 ? "…" : ""}. Cargalas en Padrón y volvé a convertir.</div>` : ""}`;
      $("#cDesc").disabled = false;
      $("#cDesc").textContent = `Descargar ${nombre}`;
    } catch (err) { fallo(err); }
    b.disabled = false; b.textContent = "Iniciar conversor";
  };
  $("#cDesc").onclick = () => { if (!listo) return; descargarBlob(listo.blob, listo.nombre); if (link) window.open(link, "_blank", "noopener"); };
};

/* ───────────── Administración: auditoría, copias y usuarios ───────────── */

VISTAS.auditoria = async () => {
  $("#subtitulo").textContent = "Registro de todo lo que se hace en la aplicación. No se puede modificar ni borrar.";
  const F = S.filtros, lim = 500;
  const d = await api("/api/auditoria?" + qs({ q: F.q || "", usuario: F.usuario || "", accion: F.accion || "", desde: F.desde || "", hasta: F.hasta || "", limite: lim, inicio: S.pagina * lim }));
  const det = f => { if (!f.detalle) return ""; const t = f.detalle.length > 400 ? f.detalle.slice(0, 400) + "…" : f.detalle; return esc(t); };
  const pags = Math.max(1, Math.ceil(d.total / lim));
  $("#vista").innerHTML = `
    <div class="barra">
      <label>Desde<input type="date" id="aDesde" value="${esc(F.desde || "")}"></label>
      <label>Hasta<input type="date" id="aHasta" value="${esc(F.hasta || "")}"></label>
      <label>Usuario<select id="aUsu"><option value="">Todos</option>${d.usuarios.map(x => `<option ${x === F.usuario ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
      <label>Tipo<select id="aAcc"><option value="">Todos</option>${d.acciones.map(x => `<option ${x === F.accion ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
      <label>Buscar<input id="q" value="${esc(F.q || "")}" placeholder="Transacción, cuenta, archivo…"></label>
      <button class="btn" id="aAnt" ${S.pagina === 0 ? "disabled" : ""} aria-label="Página anterior">${ICO.izq}</button><span class="suave">${miles(d.total)} registros · pág. ${S.pagina + 1}/${pags}</span>
      <button class="btn" id="aSig" ${S.pagina >= pags - 1 ? "disabled" : ""} aria-label="Página siguiente">${ICO.der}</button><span class="sep"></span>
      <a class="btn" href="/api/auditoria/exportar?${qs({ q: F.q || "", usuario: F.usuario || "", accion: F.accion || "", desde: F.desde || "", hasta: F.hasta || "" })}">Exportar Excel</a>
    </div>
    ${tabla([{ k: "fecha", t: "Fecha" }, { k: "usuario", t: "Usuario" }, { k: "ip", t: "IP" }, { k: "accion", t: "Acción" }, { k: "os", t: "Obra social" },
      { k: "entidad_id", t: "Ref." }, { k: "detalle", t: "Detalle", f: f => `<div class="detalle">${det(f)}</div>` }], d.filas,
      { vacio: "Sin registros para ese filtro.", acciones: f => f.detalle ? `<button class="btn mini" data-ver="${f.id}">Ver</button>` : "" })}`;
  const recargar = () => VISTAS.auditoria().catch(fallo);
  [["aDesde", "desde"], ["aHasta", "hasta"], ["aUsu", "usuario"], ["aAcc", "accion"]].forEach(([id, k]) => $("#" + id).onchange = e => { F[k] = e.target.value; S.pagina = 0; recargar(); });
  $("#q").oninput = conDemora(e => { F.q = e.target.value; S.pagina = 0; VISTAS.auditoria().then(() => { const i = $("#q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }).catch(fallo); });
  $("#aAnt").onclick = () => { S.pagina--; recargar(); };
  $("#aSig").onclick = () => { S.pagina++; recargar(); };
  $$("[data-ver]").forEach(b => b.onclick = () => {
    const f = d.filas.find(x => x.id === +b.dataset.ver);
    let txt = f.detalle; try { txt = JSON.stringify(JSON.parse(f.detalle), null, 2); } catch (e) { /* texto plano */ }
    modal(`<h3>${esc(f.accion)} · ${esc(f.fecha)} · ${esc(f.usuario)}</h3><pre class="log">${esc(txt)}</pre><div class="pie"><button class="btn primario" data-cerrar>Cerrar</button></div>`);
  });
};

VISTAS.backups = async () => {
  const d = await api("/api/backups");
  $("#subtitulo").textContent = `Copia automática cada ${d.cada_horas} h; se conservan las últimas ${d.conservar}.`;
  const mb = n => (n / 1048576).toLocaleString("es-AR", { maximumFractionDigits: 2 }) + " MB";
  $("#vista").innerHTML = `
    <div class="aviso info">Las copias quedan en el mismo servidor. Descargá una periódicamente y guardala fuera del servidor (contiene datos personales: en un lugar con acceso restringido).</div>
    <div class="barra"><button class="btn primario" id="kCrear">Crear copia ahora</button></div>
    ${tabla([{ k: "nombre", t: "Copia" }, { k: "fecha", t: "Fecha" }, { k: "bytes", t: "Tamaño", num: true, f: f => mb(f.bytes) }], d.filas.map((f, i) => ({ ...f, id: i })),
      { vacio: "Todavía no hay copias de seguridad.", acciones: f => `<a class="btn mini primario" href="/api/backups/${encodeURIComponent(f.nombre)}">Descargar</a>` })}`;
  $("#kCrear").onclick = async () => {
    $("#kCrear").disabled = true;
    try { const r = await api("/api/backups", { method: "POST" }); toast("Copia creada: " + r.nombre); VISTAS.backups(); } catch (err) { fallo(err); $("#kCrear").disabled = false; }
  };
};

VISTAS.archivo = async () => {
  const d = await api("/api/archivo");
  $("#subtitulo").textContent = `El día ${d.dia} de cada mes se copian a un Excel y se quitan de la vista los datos del período ya presentado.`;
  const mb = n => (n / 1048576).toLocaleString("es-AR", { maximumFractionDigits: 2 }) + " MB";
  const pend = Object.entries(d.pendiente).filter(([, p]) => p.evweb || p.lineas);
  $("#vista").innerHTML = `
    <div class="aviso info">Se archivan los datos extraídos de EVWEB y las líneas ya emitidas en templates, del período ${esc(d.periodo)} y anteriores. Lo que sigue pendiente en Pre-facturación y Facturación no se toca. Antes de quitar nada se hace una copia de seguridad completa. Los archivos quedan en el servidor: descargalos y guardalos fuera.</div>
    <div class="tarjeta bloque"><h3>Archivar ahora</h3>
      <form id="fAr" class="fila">
        <label>Obra social<select name="os">${Object.keys(NOMBRES).map(o => `<option value="${o}">${NOMBRES[o]}</option>`).join("")}</select></label>
        <label>Hasta el período (MMAAAA)<input name="periodo" value="${esc(d.periodo)}" maxlength="6" size="8" required></label>
        <button class="btn primario">Archivar</button>
      </form>
      <p class="suave">${pend.length ? "Pendiente de archivar hasta " + esc(d.periodo) + ": " + pend.map(([o, p]) => `${o} (${miles(p.evweb)} filas de EVWEB, ${miles(p.lineas)} líneas emitidas)`).join(" · ") : "No hay nada pendiente de archivar hasta " + esc(d.periodo) + "."}</p>
    </div>
    ${tabla([{ k: "nombre", t: "Archivo" }, { k: "os", t: "Obra social" }, { k: "hasta_periodo", t: "Hasta período" }, { k: "fecha", t: "Archivado" },
      { k: "bytes", t: "Tamaño", num: true, f: f => mb(f.bytes) }], d.filas.map((f, i) => ({ ...f, id: i })),
      { vacio: "Todavía no hay archivos.", acciones: f => `<a class="btn mini primario" href="/api/archivo/${encodeURIComponent(f.nombre)}">Descargar</a>` })}`;
  $("#fAr").onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    if (!await confirmar(`¿Archivar los datos de ${f.os} hasta el período ${f.periodo}? Se copian a un Excel y se quitan de la vista.`, "Archivar")) return;
    try { const r = await api("/api/archivo", { json: f }); toast(`Archivado: ${miles(r.evweb)} filas de EVWEB y ${miles(r.lineas)} líneas`); VISTAS.archivo(); } catch (err) { fallo(err); }
  };
};

VISTAS.usuarios = async () => {
  $("#subtitulo").textContent = "Cada persona debe tener su propio usuario: la auditoría registra quién hizo cada cosa.";
  const { filas } = await api("/api/usuarios");
  $("#vista").innerHTML = `<div class="barra"><button class="btn primario" id="uNuevo">+ Nuevo usuario</button></div>
    ${tabla([{ k: "usuario", t: "Usuario" }, { k: "nombre", t: "Nombre" }, { k: "rol", t: "Rol", f: f => f.rol === "admin" ? "Administrador" : "Operador" },
      { k: "activo", t: "Estado", f: f => f.activo ? `<span class="et ok">Activo</span>` : `<span class="et mal">Inactivo</span>` },
      { k: "ultimo_ingreso", t: "Último ingreso" }, { k: "creado", t: "Creado" }], filas,
      { acciones: f => `<button class="btn mini" data-ed="${f.id}">Editar</button>` })}`;
  const form = f => {
    modal(`<h3>${f ? "Editar usuario " + esc(f.usuario) : "Nuevo usuario"}</h3><form id="fu"><div class="rejilla">
      ${f ? "" : `<label>Usuario<input name="usuario" required autocomplete="off"></label>`}
      <label>Nombre<input name="nombre" value="${esc(f ? f.nombre : "")}"></label>
      <label>Rol<select name="rol"><option value="operador">Operador</option><option value="admin" ${f && f.rol === "admin" ? "selected" : ""}>Administrador</option></select></label>
      ${f ? `<label>Estado<select name="activo"><option value="1">Activo</option><option value="" ${f.activo ? "" : "selected"}>Inactivo</option></select></label>` : ""}
      <label>${f ? "Nueva contraseña (vacío = no cambiar)" : "Contraseña inicial"}<input name="clave" type="password" autocomplete="new-password" ${f ? "" : "required"}></label></div>
      <p class="suave">Mínimo 10 caracteres con letras y números. La persona deberá cambiarla en su primer ingreso.</p>
      <div class="pie"><button type="button" class="btn" data-cerrar>Cancelar</button><button class="btn primario">Guardar</button></div></form>`);
    $("#fu").onsubmit = async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      if (f) d.activo = !!d.activo;
      try { await api(f ? "/api/usuarios/" + f.id : "/api/usuarios", { method: f ? "PUT" : "POST", json: d }); cerrarModal(); toast("Guardado"); VISTAS.usuarios(); } catch (err) { fallo(err); }
    };
  };
  $("#uNuevo").onclick = () => form(null);
  $$("[data-ed]").forEach(b => b.onclick = () => form(filas.find(f => f.id === +b.dataset.ed)));
};

iniciar();
