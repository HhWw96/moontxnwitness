// Setup-only module syntax inspection. Never link/evaluate SDK code or follow a dynamic import.
import vm from 'node:vm';
import {isBuiltin} from 'node:module';
import {posix,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';

export const STATIC_IMPORT_CONTRACT='node-vm-static-sdk-dependencies/v1';
const MAX_SOURCE_BYTES=16*1024*1024;

export function parseStaticImports(input,moduleName){
  if(typeof vm.SourceTextModule!=='function')throw new Error('Static SDK parsing requires --experimental-vm-modules during setup only');
  if(typeof moduleName!=='string'||!moduleName||posix.isAbsolute(moduleName)||
      /[\\\u0000-\u001f:%?#]/.test(moduleName)||moduleName.split('/').some(p=>!p||p==='.'||p==='..'))
    throw new Error('Unsafe static SDK module name');
  let source;
  if(Buffer.isBuffer(input)||input instanceof Uint8Array)source=new TextDecoder('utf-8',{fatal:true}).decode(input);
  else if(typeof input==='string'&&Buffer.from(input,'utf8').toString('utf8')===input)source=input;
  else throw new TypeError('Static SDK source must be valid UTF-8 text');
  if(Buffer.byteLength(source,'utf8')>MAX_SOURCE_BYTES)throw new Error('Static SDK source exceeds setup parser budget');
  const module=new vm.SourceTextModule(source,{identifier:moduleName,context:vm.createContext(Object.create(null))});
  const staticDependencies=[...module.dependencySpecifiers],relativeDependencies=[],builtinDependencies=[];
  for(const specifier of staticDependencies){
    if(specifier.startsWith('node:')){
      if(!isBuiltin(specifier))throw new Error('Unknown node: builtin static SDK dependency: '+specifier);
      builtinDependencies.push(specifier);continue;
    }
    if(!specifier.startsWith('./')&&!specifier.startsWith('../'))throw new Error('Bare or absolute static SDK dependency is unsupported: '+specifier);
    if(/[\\\u0000-\u001f:%?#]/.test(specifier))throw new Error('Encoded, URL-decorated or unsafe static SDK dependency: '+specifier);
    const target=posix.normalize(posix.join(posix.dirname(moduleName),specifier));
    if(target==='.'||target==='..'||target.startsWith('../')||target.endsWith('/')||posix.isAbsolute(target))throw new Error('Static SDK import escaped its staged root or names a directory');
    relativeDependencies.push({specifier,target});
  }
  return {format:STATIC_IMPORT_CONTRACT,moduleName,staticDependencies,relativeDependencies,builtinDependencies,
    parser:'node:vm SourceTextModule.dependencySpecifiers',linked:false,evaluated:false,
    dynamicImportsIncluded:false,dynamicImportBoundary:'Only static module requests are inventoried; lazy import() targets are not linked, evaluated, or claimed as part of this closure.'};
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  try{
    const raw=readFileSync(0);if(raw.length>2*MAX_SOURCE_BYTES)throw new Error('Static SDK parser request exceeds setup budget');
    const request=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
    if(request===null||typeof request!=='object'||Array.isArray(request)||Object.keys(request).sort().join(',')!=='moduleName,source')throw new Error('Expected exactly moduleName and source');
    process.stdout.write(JSON.stringify(parseStaticImports(request.source,request.moduleName))+'\n');
  }catch(error){process.stderr.write(error.name+': '+error.message+'\n');process.exitCode=1;}
}
