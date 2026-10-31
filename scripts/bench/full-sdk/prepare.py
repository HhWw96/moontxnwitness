"""Prepare the Linux job's actual SDK subjects, outside every timed worker."""
from __future__ import annotations
import argparse,gzip,hashlib,json,os,posixpath,re,shutil,subprocess,sys,tempfile,time,urllib.request,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
VERSION='v0.10.16+b1a0e846e'
BASE_CORE='5b004a504ef787bb806899cd1fa243ed9db02ad68c0276599c9aad5821719cb9'
BASE_SDK='534b4c0a2767aee02a7d090c4ce51d49a67f05ccde18424d2a2944df559f407d'
ARCHIVE='05ce492f51c75f99dc49a1d95658d0d128102913cab6c806956493f1b79b2597'
BASE_URL='https://github.com/HhWw96/moontxnwitness/releases/download/v0.3.1/MoonTxnWitness-v0.3.1-portable.zip'
BASE_BYTES=83038095
IMPORT=re.compile(r"(?:\b(?:import|export)\s+(?:[^;\n]*?\s+from\s*)?)[\"'](\.[^\"']+)[\"']")

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')

def command(args,root,out,name,env):
    start=time.monotonic()
    result=subprocess.run(list(map(str,args)),cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600,check=False)
    log=out/'setup'/f'{name}.log';log.write_bytes(result.stdout)
    save(out/'setup'/f'{name}.json',{'args':list(map(str,args)),'exitCode':result.returncode,'seconds':time.monotonic()-start,'logSha256':sha(log)})
    if result.returncode:
        raise RuntimeError('Pre-measurement command failed: '+name)
    return result.stdout.decode('utf-8',errors='strict')

def fixed_archive(path,provider):
    if path.exists():
        if not path.is_file() or path.stat().st_size!=provider['bytes'] or sha(path)!=provider['sha256']:
            raise ValueError('Existing download cache differs; retain it and stop')
        return {'cachePreExisted':True,'downloadPerformed':False}
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temp=tempfile.mkstemp(prefix='portable031-',suffix='.partial',dir=path.parent)
    size=0;digest=hashlib.sha256()
    try:
        request=urllib.request.Request(provider['url'],headers={'User-Agent':'MoonTxnWitness-fixed-baseline-benchmark'})
        with os.fdopen(descriptor,'wb') as stream,urllib.request.urlopen(request,timeout=120) as response:
            while True:
                block=response.read(1024*1024)
                if not block:break
                size+=len(block)
                if size>provider['bytes']:raise ValueError('Pinned download exceeds expected length')
                digest.update(block);stream.write(block)
            stream.flush();os.fsync(stream.fileno())
        if size!=provider['bytes'] or digest.hexdigest()!=provider['sha256']:
            raise ValueError('Pinned download byte count/digest differs')
        if path.exists():raise ValueError('Download cache changed concurrently')
        os.replace(temp,path)
        return {'cachePreExisted':False,'downloadPerformed':True}
    finally:
        if os.path.exists(temp):os.unlink(temp)

def refs(data,name):
    found=[]
    for relative in IMPORT.findall(data.decode('utf-8')):
        target=posixpath.normpath(posixpath.join(posixpath.dirname(name),relative))
        if target.startswith('../') or target.startswith('/') or '\\' in target:
            raise ValueError('Static SDK import escaped its staged root')
        found.append(target)
    return found

def prepare_baseline(root,out,cache):
    binding=root/'cmd/legacy-v031-binding.mjs'
    match=re.search(r'export const PUBLIC031=Object.freeze\((\{.*\})\);',binding.read_text(encoding='utf-8'))
    if not match:raise ValueError('PUBLIC031 source binding missing')
    pin=json.loads(match.group(1));header_path=root/'scripts/frozen-inputs.json'
    header=json.loads(header_path.read_bytes())
    if not re.fullmatch(r'[\w.-]+',header['index']):raise ValueError('Unsafe frozen index filename')
    index_path=root/'scripts'/header['index']
    if sha(index_path)!=header['indexSha256']:raise ValueError('Frozen source index differs')
    index=json.loads(gzip.decompress(index_path.read_bytes()))
    if len(index)!=header['fileCount']:raise ValueError('Frozen source index count differs')
    provider=header['providers']['portable031']
    if pin['version']!='0.3.1' or pin['sourceCommit']!='44e768d0bdd4a51b2c41179494798ea89f4cc57f' or pin['archiveSha256']!=ARCHIVE or provider['sha256']!=ARCHIVE or provider['url']!=BASE_URL or provider['bytes']!=BASE_BYTES:
        raise ValueError('Wrong public baseline archive')
    if pin['files']['core.mjs']['sha256']!=BASE_CORE or pin['files']['sdk.mjs']['sha256']!=BASE_SDK:
        raise ValueError('Wrong published baseline SDK/core')
    download=fixed_archive(cache,provider)
    stage=out/'runtime/baseline';stage.mkdir(parents=True)
    todo=['sdk.mjs','build-manifest.json','LICENSE','THIRD_PARTY_NOTICES.txt'];done={}
    with zipfile.ZipFile(cache) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or len(names)>20000:raise ValueError('Duplicate/oversized fixed ZIP inventory')
        while todo:
            name=todo.pop()
            if name in done:continue
            expected=pin['files'][name];row=index['artifacts/compat-v031/runtime/'+name]
            if row['sha256']!=expected['sha256'] or row['bytes']!=expected['bytes'] or row['provider']!='portable031' or row['member']!='MoonTxnWitness-v0.3.1/dist/'+name:
                raise ValueError('Public031/index binding differs: '+name)
            data=archive.read(row['member'])  # Also checks selected member CRC.
            if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:
                raise ValueError('Actual public031 member differs: '+name)
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            done[name]={'sha256':sha(target),'bytes':len(data),'publicFileKey':name,'indexKey':'artifacts/compat-v031/runtime/'+name,'archiveMember':row['member']}
            if name.endswith('.mjs'):todo.extend(refs(data,name))
    manifest_path=stage/'build-manifest.json';manifest=json.loads(manifest_path.read_bytes())
    if manifest['version']!='0.3.1' or manifest['coreSha256']!=BASE_CORE or manifest['toolchain']['compiler']!=VERSION:
        raise ValueError('Published compiler/version manifest differs')
    result={'root':str(stage),'entry':str(stage/'sdk.mjs'),'version':'0.3.1','publicFiles':done,
            'buildManifest':{'path':str(manifest_path),'sha256':sha(manifest_path),'value':manifest},
            'public031Binding':{'path':str(binding),'sha256':sha(binding),'archiveSha256':ARCHIVE},
            'frozenIndex':{'headerPath':str(header_path),'headerSha256':sha(header_path),'indexPath':str(index_path),'indexSha256':sha(index_path)}}
    save(out/'setup/baseline-download.json',{**download,'archiveSha256':sha(cache),'archiveBytes':cache.stat().st_size,'sourceURL':provider['url'],'selectedStagedFiles':len(done),'allSelectedCRCAndDigestsVerified':True,'legacyPayloadsExtracted':False})
    return result

def prepare_candidate(root,out):
    home=Path(os.environ['MOON_HOME']);moon=home/'bin/moon';moonc=home/'bin/moonc'
    temp=Path(tempfile.mkdtemp(prefix='full-sdk-compiler-',dir=os.environ['RUNNER_TEMP']))
    env={**os.environ,'TEMP':str(temp),'TMP':str(temp),'TMPDIR':str(temp),'PYTHONDONTWRITEBYTECODE':'1'}
    compiler=command([moonc,'-v'],root,out,'compiler-version',env)
    if not re.match(r'^'+re.escape(VERSION)+r'(?:\s|$)',compiler.strip()):
        raise ValueError('Require actual compiler '+VERSION)
    moon_version=command([moon,'version'],root,out,'moon-version',env)
    command([moon,'info','--target','js','src'],root,out,'moon-info',env)
    command(['git','diff','--exit-code','--','src','cmd','moon.mod'],root,out,'tracked-source-clean-after-info',env)
    command([moon,'check','src','--target','js','--deny-warn','--jobs','1'],root,out,'moon-check-js',env)
    command([moon,'build','src/bridge','--target','js','--release','--deny-warn','--jobs','1'],root,out,'main-bridge-build',env)
    command([moon,'build','src/capture_bridge','--target','js','--release','--deny-warn','--jobs','1'],root,out,'capture-bridge-build',env)
    command(['git','diff','--exit-code','--','src','cmd','moon.mod'],root,out,'tracked-source-clean-after-build',env)
    stage=out/'runtime/candidate';stage.mkdir(parents=True)
    for name in ('LICENSE','THIRD_PARTY_NOTICES.txt'):
        shutil.copyfile(root/name,stage/name)
    for file in (root/'cmd').glob('*.mjs'):
        if file.name not in ('core.mjs','capture-core.mjs'):shutil.copyfile(file,stage/file.name)
    main=root/'_build/js/release/build/bridge/bridge.js'
    capture=root/'_build/js/release/build/capture_bridge/capture_bridge.js'
    shutil.copyfile(main,stage/'core.mjs');shutil.copyfile(capture,stage/'capture-core.mjs')
    names=subprocess.check_output(['git','ls-files','-z','--','src','cmd','moon.mod'],cwd=root).decode('utf-8').split('\0')
    files={n:{'path':str(root/n),'sha256':sha(root/n),'bytes':(root/n).stat().st_size} for n in sorted(n for n in names if n)}
    digest=hashlib.sha256(''.join(n+'\0'+files[n]['sha256']+'\n' for n in files).encode()).hexdigest()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    version=re.search(r'^version\s*=\s*"([^"]+)"',(root/'moon.mod').read_text(encoding='utf-8'),re.M).group(1)
    fingerprint_helper=root/'scripts/build-fingerprint.mjs'
    fingerprint_script='import {pathToFileURL} from "node:url"; const {sourceFingerprint}=await import(pathToFileURL(process.argv[1])); console.log(sourceFingerprint(process.argv[2]));'
    repository_fingerprint=command(['node','--input-type=module','-e',fingerprint_script,fingerprint_helper,root],root,out,'repository-source-fingerprint',env).strip()
    if not re.fullmatch('[0-9a-f]{64}',repository_fingerprint):raise ValueError('Repository sourceFingerprint returned invalid digest')
    result={'root':str(stage),'entry':str(stage/'sdk.mjs'),'version':version,'sourceCommit':commit,
            'sourceFingerprint':repository_fingerprint,'sourceFingerprintContract':'scripts/build-fingerprint.mjs raw moon.mod/src-mbt/moon.pkg bytes with path-NUL framing','sourceFingerprintHelperSha256':sha(fingerprint_helper),
            'trackedSourceClosureSha256':digest,'trackedSourceClosureContract':'sha256 of sorted tracked src/cmd/moon.mod path-NUL-content-SHA256-LF entries','allSourceFiles':files,'actualMainCoreSha256':sha(main),
            'actualCaptureCoreSha256':sha(capture),
            'toolchain':{'compiler':VERSION,'compilerOutput':compiler.strip(),'compilerBinarySha256':sha(moonc),'moonOutput':moon_version.strip()},
            'sourceState':'actual tracked source unchanged after info/check/build',
            'windowsC7HashAssumed':False,'legacyRuntimeRestored':False}
    installer=Path(os.environ['RUNNER_TEMP'])/'moon-install.sh'
    if installer.is_file():result['officialInstallerScriptSha256']=sha(installer)
    save(out/'setup/candidate-build.json',result)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['init','prepare'])
    parser.add_argument('--candidate-root',required=True);parser.add_argument('--output',required=True);parser.add_argument('--baseline-cache',required=True)
    a=parser.parse_args();root=Path(a.candidate_root).resolve();out=Path(a.output).resolve()
    out.mkdir(parents=True,exist_ok=True);(out/'setup').mkdir(exist_ok=True)
    if a.mode=='init':
        save(out/'setup/job-intent.json',{'format':'full-sdk-linux-job-intent/v1',
             'hostScope':'GitHub-hosted Ubuntu job; paired same-job comparison, no physical dedicated-host guarantee',
             'candidateRoot':str(root),'github':{k:os.environ.get(k) for k in ['GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_SHA','GITHUB_REF','GITHUB_JOB','RUNNER_OS','RUNNER_ARCH','RUNNER_ENVIRONMENT']},
             'compilerRequired':VERSION,'nodeRequired':'v24.13.0','runReason':os.environ.get('MTW_PERF_REASON'),'formalMeasurementExecuted':False})
        return 0
    if sys.platform!='linux' or os.environ.get('GITHUB_ACTIONS')!='true':
        raise RuntimeError('Build/download preparation requires registered Linux CI; local execution disabled')
    try:
        if shutil.disk_usage(out).free<2*1024**3:raise RuntimeError('At least 2GiB free workspace required before preparation')
        baseline=prepare_baseline(root,out,Path(a.baseline_cache).resolve())
        candidate=prepare_candidate(root,out)
        if baseline['buildManifest']['value']['toolchain']['compiler']!=candidate['toolchain']['compiler']:
            raise ValueError('Compiler version differs from published baseline')
        for file in HERE.glob('*.mjs'):
            target=out/'runner'/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,target)
        index=json.loads((HERE/'fixtures/index.json').read_bytes());cases=[]
        for case in index['scenarios']:
            source=HERE/case['path']
            if sha(source)!=case['sha256']:raise ValueError('Pre-registered input differs')
            target=out/'inputs'/source.name;target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
            cases.append({**case,'path':'inputs/'+source.name})
        save(out/'input-manifest.json',{'format':index['format'],'scenarios':cases,'windowsSamplesInherited':False,'normalizationAndInputSemanticsChanged':False})
        save(out/'subjects.json',{'format':'full-sdk-linux-actual-subjects/v1','baseline':baseline,'candidate':candidate,
             'windowsPartialSamplesUsed':False,'compilerVersionsEqual':True,'allPreparationBeforeTiming':True})
        return 0
    except BaseException as error:
        save(out/'setup/preparation-failure.json',{'format':'full-sdk-linux-preparation-failure/v1','errorClass':type(error).__name__,'message':str(error),
             'formalMeasurementExecuted':False,'noAutomaticMeasurementRetry':True})
        raise

if __name__=='__main__':raise SystemExit(main())
