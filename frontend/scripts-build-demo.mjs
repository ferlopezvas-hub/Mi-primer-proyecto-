// Genera demo/sport-ai-predictor.html: la app completa en un solo archivo (código, estilos y datos).
// Uso: npm run build:demo   (requiere demo/demo-data.json, ver backend/scripts/export_demo.py)
import { readFileSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";

execSync("npx vite build --mode demo", { stdio: "inherit" });
const html = readFileSync("dist-demo/index.html", "utf8");
const js = html.match(/<script type="module" crossorigin src="\.\/(assets\/[^"]+\.js)"><\/script>/);
const css = html.match(/<link rel="stylesheet" crossorigin href="\.\/(assets\/[^"]+\.css)">/);
if (!js || !css) throw new Error("No se encontraron los recursos del build");
const esc = (s) => s.replace(/<\/(script)/gi, "<\\/$1").replace(/<!--/g, "<\\!--");
const data = readFileSync("demo/demo-data.json", "utf8");
const page = `<title>SPORT AI PREDICTOR</title>
<meta name="description" content="Demo de SPORT AI PREDICTOR con datos reales de fútbol">
<style>${readFileSync("dist-demo/" + css[1], "utf8")}</style>
<div id="root"></div>
<script>window.__SPORTAI_DEMO__ = ${esc(data)};</script>
<script type="module">${esc(readFileSync("dist-demo/" + js[1], "utf8"))}</script>
`;
writeFileSync("demo/sport-ai-predictor.html", page);
console.log(`demo/sport-ai-predictor.html: ${(page.length / 1e6).toFixed(2)} MB`);
