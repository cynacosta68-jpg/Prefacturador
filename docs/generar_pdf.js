// Imprime a PDF (A4) el HTML generado por generar_pdf.py.
//   node docs/generar_pdf.js <entrada.html> <salida.pdf> "<texto del pie>"
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const [entrada, salida, pie] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage();
  await p.goto('file://' + path.resolve(entrada));
  await p.evaluate(() => document.fonts.ready);
  await p.pdf({
    path: salida, format: 'A4', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="width:100%;font-family:sans-serif;font-size:7px;color:#56617a;padding:0 18mm;display:flex;justify-content:space-between"><span>'
      + (pie || '') + '</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
  });
  await b.close();
  console.log('PDF:', salida);
})();
