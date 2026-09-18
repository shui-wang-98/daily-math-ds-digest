import {build} from 'esbuild';
import {mkdir, copyFile, writeFile, readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const destination = '../../src/vendor/mathjax';
await mkdir(destination,{recursive:true});
const result=await build({entryPoints:['renderer.mjs'], bundle:true, platform:'node',
  target:'node18',format:'esm',minify:true,legalComments:'eof',metafile:true,
  outfile:destination+'/renderer.mjs'});
await copyFile('node_modules/@mathjax/src/LICENSE',destination+'/LICENSE-mathjax');
// Both packages declare Apache-2.0; the font package omits a LICENSE file.
await copyFile('node_modules/@mathjax/src/LICENSE',destination+'/LICENSE-font');
const bytes=await readFile(destination+'/renderer.mjs');
await writeFile(destination+'/manifest.json',JSON.stringify({
  mathjax:'4.1.3',font:'@mathjax/mathjax-tex-font@4.1.3',esbuild:'0.28.2',
  sha256:createHash('sha256').update(bytes).digest('hex'),
  bytes:bytes.length,
  externalImports:result.metafile.outputs[destination+'/renderer.mjs'].imports
},null,2)+'\n');
