// Build-time entry point. Runtime bundle has no package or network loader.
import {mathjax} from '@mathjax/src/mjs/mathjax.js';
import {TeX} from '@mathjax/src/mjs/input/tex.js';
import {SVG} from '@mathjax/src/mjs/output/svg.js';
import {liteAdaptor} from '@mathjax/src/mjs/adaptors/liteAdaptor.js';
import {RegisterHTMLHandler} from '@mathjax/src/mjs/handlers/html.js';
import {MathJaxTexFont} from '@mathjax/mathjax-tex-font/mjs/svg.js';
import '@mathjax/src/mjs/input/tex/base/BaseConfiguration.js';
import '@mathjax/src/mjs/input/tex/ams/AmsConfiguration.js';
import '@mathjax/src/mjs/input/tex/amscd/AmsCdConfiguration.js';
import '@mathjax/src/mjs/input/tex/boldsymbol/BoldsymbolConfiguration.js';
import '@mathjax/src/mjs/input/tex/braket/BraketConfiguration.js';
import '@mathjax/src/mjs/input/tex/cancel/CancelConfiguration.js';
import '@mathjax/src/mjs/input/tex/cases/CasesConfiguration.js';
import '@mathjax/src/mjs/input/tex/centernot/CenternotConfiguration.js';
import '@mathjax/src/mjs/input/tex/color/ColorConfiguration.js';
import '@mathjax/src/mjs/input/tex/extpfeil/ExtpfeilConfiguration.js';
import '@mathjax/src/mjs/input/tex/gensymb/GensymbConfiguration.js';
import '@mathjax/src/mjs/input/tex/mathtools/MathtoolsConfiguration.js';
import '@mathjax/src/mjs/input/tex/newcommand/NewcommandConfiguration.js';
import '@mathjax/src/mjs/input/tex/textmacros/TextMacrosConfiguration.js';
import {Configuration} from '@mathjax/src/mjs/input/tex/Configuration.js';
import {OPTIONS} from '@mathjax/src/mjs/util/Options.js';
import {createInterface} from 'node:readline';
OPTIONS.invalidOption = 'fatal';
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const packages = ['base','ams','amscd','boldsymbol','braket','cancel','cases',
  'centernot','color','extpfeil','gensymb','mathtools','newcommand','textmacros','source-notation'];
Configuration.create('source-notation', {
  priority: 3,
  config(_config,jax) { jax.parseOptions.packageData.set('source-notation',new Set()); },
  fallback: {macro(parser,name) {
    const unknown=parser.configuration.packageData.get('source-notation');
    unknown.add(name);
    if (unknown.size > 32) throw Error('Too many unrecognized commands');
    // TeX eats whitespace after a control word. Preserve a visible boundary
    // when showing that word literally inside text.
    const space=('text' in parser && /\s/.test(parser.string[parser.i-1] || '')) ? '\u00a0' : '';
    parser.Push(parser.create('node','mtext',[],{},parser.create('text','\\'+name+space)));
  }}
});
const forbidden = /\\(?:require|input|include|includegraphics|href|url|htmlClass|htmlId|htmlStyle|htmlData|cssId|style|class)(?![A-Za-z])/;
function convert(source, display) {
  // Fresh input/output objects prevent definitions, labels and IDs leaking
  // across formulas. All fonts are compiled into this bundle.
  const tex = new TeX({packages, maxBuffer: 16384, maxMacros: 1000,
    maxTemplateSubtitutions: 1000, tags: 'none',
    formatError(_jax, error) { throw error; }});
  const output = new SVG({fontData: new MathJaxTexFont(), fontCache: 'none', linebreaks: {inline:false},
    mtextInheritFont: false, merrorInheritFont: false});
  const doc = mathjax.document('', {InputJax: tex, OutputJax: output});
  const container = doc.convert(source, {display, em:16, ex:8, containerWidth:1280});
  const svg = adaptor.firstChild(container);
  const serialized = adaptor.serializeXML(svg);
  if (/data-mml-node="merror"/.test(serialized)) throw Error('MathJax returned an error node');
  const viewBox = adaptor.getAttribute(svg,'viewBox').split(/\s+/).map(Number);
  if (viewBox.length !== 4 || !viewBox.every(Number.isFinite)) throw Error('Invalid SVG dimensions');
  if (viewBox[2] < 0 || viewBox[2] > 256000 || viewBox[3] < 0 || viewBox[3] > 128000 ||
      Math.abs(viewBox[1]) > 128000 || Math.abs(viewBox[1]+viewBox[3]) > 128000)
    throw Error('Formula exceeds layout dimension limits');
  return {svg: serialized, width: viewBox[2]/1000, depth: (viewBox[1]+viewBox[3])/1000,
    unknown: [...tex.parseOptions.packageData.get('source-notation')]};
}
function render(request) {
  const {source, display=false} = request;
  if (typeof source !== 'string' || source.length > 16384 || typeof display !== 'boolean')
    throw Error('Invalid or oversized formula');
  if (forbidden.test(source)) throw Error('External resources and HTML commands are not supported');
  return convert(source, display);
}
const lines=createInterface({input:process.stdin, crlfDelay:Infinity});
for await (const line of lines) {
  try {
    if (line.length > 131072) throw Error('Oversized renderer request');
    const result=render(JSON.parse(line));
    if (result.svg.length > 256000) throw Error('Oversized SVG');
    process.stdout.write(JSON.stringify({ok:true,...result})+'\n');
  } catch(error) {
    process.stdout.write(JSON.stringify({ok:false,error:String(error.message),code:error.id || 'RenderError'})+'\n');
  }
}
