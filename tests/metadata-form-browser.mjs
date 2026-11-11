/* Real ReactDOM + repository presentation adapters + installed host UI controls.
 * Fictional transport only; not host loader, Electron, authenticated API or model QA.
 */
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir,mkdtemp,rm,stat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {execFileSync,spawn} from 'node:child_process';
import {realUI} from './native-components.mjs';
const root=resolve('.'),source=process.env.HERMES_UI_SOURCE||join(process.env.HOME,'.hermes/hermes-agent');
const requireHost=createRequire(join(source,'package.json'));
const {build}=requireHost('esbuild'),{chromium,expect}=requireHost('@playwright/test');
const proof=process.env.METADATA_FORM_PROOF||resolve(root,'../evidence/shelf-metadata-form-build/browser');
await mkdir(proof,{recursive:true});
const scratch=await mkdtemp(join(process.env.TMPDIR,'metadata-form-'));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const dependencies=['ui/metadata-errors.js','ui/metadata-draft.js','tests/metadata-draft.test.mjs','tests/metadata-errors.test.mjs','ui/presentation.desktop.jsx','ui/presentation.dashboard.jsx','ui/ShelfEditor.jsx','ui/saved.css','ui/style.css','tests/native-components.mjs','tests/saved-browser.mjs','scripts/build.mjs','package.json','CONTRIBUTING.md','desktop/plugin.js','dashboard/dist/index.js'];
const owned=['ui/MetadataForm.jsx','tests/metadata-form-browser.mjs','tests/fixtures/metadata-form/mount.jsx','tests/fixtures/metadata-form/README.md'];
const inputs={};for(const path of [...dependencies,...owned,'../evidence/shelf-metadata-form-build/scope.md','docs/egm/reviews/feature-01/integrated-revision-09-ux/desktop-api.md','docs/egm/reviews/feature-01/ux-qol-03-resolution/metadata-user-override.md'])inputs[path]=sha(await readFile(join(root,path)));
await writeFile(join(proof,'inputs.json'),JSON.stringify({head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),inputs,source},null,2));
let server,browser,xvfb;
const rows=[],hostInputs={},bundles={},themeReceipts=[],titleReceipts=[],correctnessReceipts=[];
let browserIdentity=null;
try{
 const ui=await realUI(source);
 const plugin={name:'fixture-host-controls',setup(b){
  // Test-only prop/transport controls; the actual component remains unmodified.
  b.onLoad({filter:/tests\/fixtures\/metadata-form\/mount\.jsx$/},async a=>({contents:(await readFile(a.path,'utf8')).replace('generationAllowed={true} adapter={adapter}','generationAllowed={props.generationAllowed??true} adapter={props.adapter||adapter}').replace('window.fixture={calls,','window.fixture={adapter,calls,').replace('<MetadataForm {...props}', '<MetadataForm key={props.fixtureKey} {...props}'),loader:'jsx',resolveDir:join(root,'tests/fixtures/metadata-form')}));
  b.onResolve({filter:/^(react|react-dom|nanostores)(\/.*)?$/},a=>({path:requireHost.resolve(a.path)}));
  b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'fixture'}));
  b.onLoad({filter:/^sdk$/,namespace:'fixture'},()=>({contents:ui.imports+'\nexport {'+ui.names.join(',')+'};',loader:'js',resolveDir:source}));
  b.onResolve({filter:/^@\//},a=>{
   const stubs={'@/lib/keybinds/use-keybind-hint':'export const useKeybindHint=()=>null;','@/hermes':'export const getHermesConfigRecord=async()=>({}),retainConfigReadOrigin=x=>x,saveHermesConfig=async()=>({ok:true});','@/store/notifications':'export const notifyError=()=>{};'};
   if(stubs[a.path])return {path:a.path,namespace:'stub',pluginData:stubs[a.path]};
   return b.resolve(join(source,'apps/desktop/src',a.path.slice(2)),{kind:a.kind,resolveDir:source});
  });
  b.onLoad({filter:/.*/,namespace:'stub'},a=>({contents:a.pluginData,loader:'js'}));
 }};
 for(const surface of ['desktop','dashboard']){
  const dashboard=`import {Button} from '@nous-research/ui/ui/components/button';import {Input} from '@nous-research/ui/ui/components/input';import {DialogFooter} from '@nous-research/ui/ui/components/dialog';window.__HERMES_PLUGIN_SDK__={components:{Button,Input,DialogFooter}};`;
  const compiled=await build({metafile:true,stdin:{contents:(surface==='desktop'?ui.nativeBootstrap:ui.dashboardBootstrap+dashboard)+`\nimport('./tests/fixtures/metadata-form/mount.jsx');`,loader:'jsx',resolveDir:root},outfile:join(scratch,surface+'.js'),bundle:true,format:'esm',jsx:'automatic',target:'es2022',nodePaths:[join(source,'node_modules')],alias:{'@saved/presentation':join(root,'ui/presentation.'+surface+'.jsx')},loader:{'.css':'text','.woff2':'dataurl','.woff':'dataurl','.ttf':'dataurl','.svg':'dataurl'},define:{'process.env.NODE_ENV':'"production"','import.meta.env.DEV':'false'},plugins:[plugin]});
  for(const path of Object.keys(compiled.metafile.inputs))if(!path.includes(':')&&path!=='<stdin>')hostInputs[resolve(root,path)]=sha(await readFile(resolve(root,path)));
  bundles[surface]={bundle:sha(await readFile(join(scratch,surface+'.js'))),stylesheetBootstrap:sha(surface==='desktop'?ui.nativeBootstrap:ui.dashboardBootstrap)};
 }
 await writeFile(join(proof,'host-inputs.json'),JSON.stringify({source,hostCommit:execFileSync('git',['-C',source,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),hostInputs,bundles,react:requireHost('react/package.json').version,reactDOM:requireHost('react-dom/package.json').version,playwright:requireHost('@playwright/test/package.json').version},null,2));
 server=createServer(async(req,res)=>{
  if(req.url==='/desktop.js'||req.url==='/dashboard.js'){res.setHeader('Content-Type','text/javascript');res.end(await readFile(join(scratch,req.url.slice(1))));return;}
  if(req.url==='/favicon.ico'){res.writeHead(204);res.end();return;}
  const surface=req.url.startsWith('/dashboard')?'dashboard':'desktop';res.setHeader('Content-Type','text/html');res.end(`<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module" src="/${surface}.js"></script></body></html>`);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 // An owned headful browser, not the user's browser; real X11, no OS signals fabricated.
 let display=process.env.DISPLAY||':99';
 if(!process.env.DISPLAY){try{await stat('/tmp/.X11-unix/X99');}catch(e){if(e.code!=='ENOENT')throw e;
  xvfb=spawn('Xvfb',['-displayfd','1','-screen','0','1440x1100x24'],{stdio:['ignore','pipe','ignore']});
  display=':'+await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Owned Xvfb readiness timeout')),5000);xvfb.once('error',reject);xvfb.once('exit',()=>reject(Error('Owned Xvfb exited')));xvfb.stdout.on('data',chunk=>{text+=chunk;if(text.includes('\n')){clearTimeout(timer);resolve(text.trim());}});});
 }}
 browser=await chromium.launch({headless:false,args:['--enable-automation'],env:{...process.env,DISPLAY:display}});
 const browserCDP=await browser.newBrowserCDPSession();
 browserIdentity={version:await browserCDP.send('Browser.getVersion'),commandLine:(await browserCDP.send('Browser.getBrowserCommandLine')).arguments,display,ownedDisplayPid:xvfb?.pid||null,processes:(await browserCDP.send('SystemInfo.getProcessInfo')).processInfo};
 browserIdentity.pid=browserIdentity.processes.find(p=>p.type==='browser').id;
 browserIdentity.liveArgv=(await readFile('/proc/'+browserIdentity.pid+'/cmdline','utf8')).split('\0').filter(Boolean);
 browserIdentity.profile=browserIdentity.commandLine.find(arg=>arg.startsWith('--user-data-dir=')).slice('--user-data-dir='.length);
 expect(browserIdentity.liveArgv.some(arg=>arg.startsWith('--headless'))).toBe(false);expect(browserIdentity.liveArgv).toContain('--user-data-dir='+browserIdentity.profile);
 expect(browserIdentity.commandLine.some(arg=>arg.startsWith('--headless'))).toBe(false);await browserCDP.detach();
 async function scenario(surface,name,run){
  if(process.env.METADATA_FORM_CASE&&!name.includes(process.env.METADATA_FORM_CASE))return;
  const context=await browser.newContext({viewport:{width:1000,height:900}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('requestfailed',r=>errors.push(r.url()));
  try{await page.goto(base+'/'+surface);await expect(page.getByLabel('Title',{exact:true})).toBeVisible();await run(page);expect(errors).toEqual([]);rows.push({surface,name,passed:true});console.log('PASS',surface,name);}
  catch(error){await page.screenshot({path:join(proof,surface+'-failure.png'),fullPage:true});rows.push({surface,name,passed:false,error:error.message});throw error;}finally{await context.close();}
 }
 async function addTags(page,tags){
  for(const tag of tags){
   await page.getByLabel('Tags',{exact:true}).fill(tag===''?'temporary':tag);
   await page.getByLabel('Tags',{exact:true}).press('Enter');
   if(tag==='')await page.getByRole('textbox',{name:/^Tag \d+$/}).last().fill('');
  }
 }
 async function expectTags(page,tags){
  const controls=page.getByRole('textbox',{name:/^Tag \d+$/});await expect(controls).toHaveCount(tags.length);
  for(let i=0;i<tags.length;i++)await expect(controls.nth(i)).toHaveValue(tags[i]);
 }
 async function removeTags(page){while(await page.getByRole('button',{name:/^Remove tag \d+$/}).count())await page.getByRole('button',{name:'Remove tag 1',exact:true}).click();}
 for(const surface of ['desktop','dashboard']){
  await scenario(surface,'indexed tag correction focuses exact existing or pending row on click and Enter',async page=>{
   await page.setViewportSize({width:320,height:650});
   await page.getByLabel('Title',{exact:true}).fill('Valid');await addTags(page,[' first ','second\nline']);
   await page.getByLabel('Tags',{exact:true}).fill(' pending ');
   const metadata={title:'Valid',description:'',tags:[' first ','second\nline',' pending ']};
   await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves[0].metadata)).toEqual(metadata);
   for(const index of [0,1,2]){
    const target=page.getByLabel(index===2?'Tags':'Tag '+(index+1),{exact:true});
    await page.evaluate(index=>window.fixture.saveError({code:'metadata_invalid',message:`Invalid metadata: tags[${index}]/control`}),index);
    for(const method of ['click','Enter']){
     if(method==='click')await page.getByRole('button',{name:'Save',exact:true}).click();else{await page.getByLabel('Title',{exact:true}).focus();await page.keyboard.press('Enter');}
     await expect(page.getByRole('alert')).toHaveText(`Delete and retype the affected text in Tag ${index+1}.`);await expect(target).toBeFocused();
     await expect(target).toHaveAttribute('aria-invalid','true');await expect(target).toHaveAttribute('aria-describedby',await page.getByRole('alert').getAttribute('id'));
     for(const label of ['Tags','Tag 1','Tag 2'].filter(label=>label!==(index===2?'Tags':'Tag '+(index+1))))await expect(page.getByLabel(label,{exact:true})).not.toHaveAttribute('aria-describedby');
     expect(await page.evaluate(()=>window.fixture.saves.at(-1).metadata)).toEqual(metadata);
     correctnessReceipts.push({surface,finding:'F1',index,method,focused:await target.evaluate(n=>document.activeElement===n),describedBy:await target.getAttribute('aria-describedby'),message:await page.getByRole('alert').innerText(),request:await page.evaluate(()=>window.fixture.saves.at(-1))});
     expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
     if(method==='Enter'&&index>0)await page.screenshot({path:join(proof,surface+'-indexed-tag-'+index+'-320.png'),fullPage:true});
    }
   }
   await page.getByLabel('Tag 1',{exact:true}).fill('corrected');await expect(page.getByRole('alert')).toHaveCount(0);
   await page.getByRole('button',{name:'Remove tag 1',exact:true}).click();await expectTags(page,['second\nline']);
   await page.evaluate(()=>window.fixture.saveError({code:'metadata_invalid',message:'Invalid metadata: tags[0]/control'}));
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByLabel('Tag 1',{exact:true})).toBeFocused();
   expect(await page.evaluate(()=>window.fixture.saves.at(-1).metadata)).toEqual({title:'Valid',description:'',tags:['second\nline',' pending ']});
   for(const field of ['tags','tags[19]']){
    await page.evaluate(field=>window.fixture.saveError({code:'metadata_invalid',message:`Invalid metadata: ${field}/scalar_limit`}),field);
    await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByLabel('Tags',{exact:true})).toBeFocused();
   }
   await page.evaluate(()=>window.fixture.reset({ownerKey:'next-owner',initialValues:{title:'Next',description:'',tags:['Next row']}}));
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Next');await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByLabel('Tag 1',{exact:true})).not.toHaveAttribute('aria-describedby');
   await page.evaluate(()=>window.fixture.saveError(null));await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves.at(-1))).toEqual({ownerKey:'next-owner',sourceKey:'fixture-file',metadata:{title:'Next',description:'',tags:['Next row']},generation_policy:'never'});
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(0);
   await page.evaluate(()=>{window.fixture.adapter.save=()=>new Promise((_,reject)=>{window.fixture.lateSaveError=reject;});});
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.evaluate(()=>window.fixture.reset({ownerKey:'final-owner',initialValues:{title:'Final',description:'',tags:['Final row']}}));
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Final');await page.getByLabel('Title',{exact:true}).focus();
   await page.evaluate(()=>window.fixture.lateSaveError({code:'metadata_invalid',message:'Invalid metadata: tags[0]/control'}));
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByLabel('Title',{exact:true})).toBeFocused();await expect(page.getByLabel('Tag 1',{exact:true})).not.toHaveAttribute('aria-describedby');
  });
  await scenario(surface,'same-draft permit recovery requires explicit status then a separate Generate',async page=>{
   await page.getByLabel('Title',{exact:true}).fill(' Keep ');await page.getByLabel('Tags',{exact:true}).fill(' pending ');
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[0].request.supplied_metadata)).toEqual({title:' Keep ',tags:[' pending ']});
   await page.evaluate(()=>window.fixture.cancel({state:'quarantined',safeToSave:true,canGenerate:false}));
   await page.getByRole('button',{name:'Stop generating',exact:true}).click();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();
   await page.screenshot({path:join(proof,surface+'-safe-quarantine-recovery.png'),fullPage:true});
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Fenced output'}));await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');
   await page.evaluate(()=>window.fixture.reset({generationAllowed:false}));
   await page.evaluate(()=>window.fixture.reset({generationAllowed:true}));
   expect(await page.evaluate(()=>window.fixture.checks.length)).toBe(0);expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);
   for(const status of [{state:'quarantined',safeToSave:true,canGenerate:false},{state:'unknown'},{state:'stopped',safeToSave:false,canGenerate:true},{state:'stopped',safeToSave:true,canGenerate:'true'},'hang']){
    await page.evaluate(status=>window.fixture.status(status),status);await page.getByRole('button',{name:'Check generation status',exact:true}).click();
    await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled({timeout:4000});
   }
   await page.evaluate(()=>{window.fixture.adapter.status=request=>{window.fixture.checks.push(request);return Promise.reject(Error('PRIVATE'));};});
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[0].metadata)).toEqual({title:' Keep ',description:'',tags:[' pending ']});
   await page.evaluate(()=>{const original=window.fixture.adapter;original.status=request=>{window.fixture.checks.push(request);return Promise.resolve({state:'stopped',safeToSave:true,canGenerate:true});};window.fixture.replacementChecks=[];window.fixture.reset({generationAllowed:false,adapter:{...original,status:request=>{window.fixture.replacementChecks.push(request);return Promise.resolve({state:'unknown'});}}});});
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();
   expect(await page.evaluate(()=>window.fixture.replacementChecks)).toEqual([]);
   expect(await page.evaluate(()=>window.fixture.checks.length)).toBe(7);expect(await page.locator('body').innerText()).not.toContain('PRIVATE');
   expect(await page.evaluate(()=>window.fixture.checks.every(r=>r===window.fixture.calls[0].request))).toBe(true);
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);expect(await page.evaluate(()=>window.fixture.saves.length)).toBe(1);
   await page.evaluate(()=>window.fixture.reset({generationAllowed:true}));await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(2);expect(await page.evaluate(()=>window.fixture.calls[1].request.requestId)).not.toBe(await page.evaluate(()=>window.fixture.calls[0].request.requestId));
   await page.evaluate(()=>window.fixture.resolve(1,{description:'New suggestion'}));await expect(page.getByLabel('Description',{exact:true})).toHaveValue('New suggestion');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue(' Keep ');await expect(page.getByLabel('Tags',{exact:true})).toHaveValue(' pending ');
   correctnessReceipts.push({surface,finding:'F2',calls:await page.evaluate(()=>window.fixture.calls.map(({request})=>request)),checks:await page.evaluate(()=>window.fixture.checks),saves:await page.evaluate(()=>window.fixture.saves),replacementChecks:await page.evaluate(()=>window.fixture.replacementChecks)});
  });
  for(const identity of ['ownerKey','sourceKey','fixtureKey'])await scenario(surface,identity+' late permit status cannot transfer permission or notice to a new draft',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.cancel({state:'quarantined',safeToSave:true,canGenerate:false}));
   await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await page.evaluate(()=>{window.fixture.adapter.status=request=>{window.fixture.checks.push(request);return new Promise(resolve=>{window.fixture.lateStatus=resolve;});};});
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Checking generation status',exact:true})).toBeDisabled();
   await page.evaluate(identity=>window.fixture.reset({[identity]:'next',initialValues:{title:'New draft',description:'',tags:[]}}),identity);
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New draft');await expect(page.getByRole('alert')).toHaveCount(0);
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();
   await page.evaluate(identity=>window.fixture.lateStatus(identity==='ownerKey'?{state:'unknown'}:{state:'stopped',safeToSave:true,canGenerate:true}),identity);
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Generate',exact:true})).toHaveCount(0);
   await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByRole('status')).toHaveCount(0);await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await page.evaluate(()=>{window.fixture.resolve(0,{title:'Old',description:'Old',tags:['old']});window.fixture.resolve(1,{description:'Cancelled',tags:['cancelled']});});
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New draft');await expect(page.getByRole('status')).toHaveCount(0);
   expect(await page.evaluate(()=>({calls:window.fixture.calls.length,saves:window.fixture.saves.length,checks:window.fixture.checks.length}))).toEqual({calls:2,saves:0,checks:1});
  });
  await scenario(surface,'timed-out permit status cannot unlock a later check or operation',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.cancel({state:'stopped',safeToSave:true,canGenerate:false}));await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await page.evaluate(()=>{window.fixture.statusReplies=[];window.fixture.adapter.status=request=>{window.fixture.checks.push(request);return new Promise(resolve=>window.fixture.statusReplies.push(resolve));};});
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled({timeout:4000});
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();
   await page.evaluate(()=>window.fixture.statusReplies[0]({state:'stopped',safeToSave:true,canGenerate:true}));
   await expect(page.getByRole('button',{name:'Checking generation status',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);
   await page.evaluate(()=>window.fixture.statusReplies[1]({state:'stopped',safeToSave:true,canGenerate:true}));await page.getByRole('button',{name:'Generate',exact:true}).click();
   await expect(page.getByRole('button',{name:'Stop generating',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.evaluate(()=>window.fixture.resolve(1,{title:'New',description:'New',tags:['new']}));await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New');await expect(page.getByRole('status')).toHaveCount(0);
   expect(await page.evaluate(()=>({calls:window.fixture.calls.length,saves:window.fixture.saves.length,checks:window.fixture.checks.length}))).toEqual({calls:2,saves:0,checks:2});
  });
  await scenario(surface,'stale malformed generation is an error not an edits-kept announcement',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByLabel('Title',{exact:true}).fill('Keep');await page.evaluate(()=>window.fixture.resolve(0,{description:'Missing requested fields'}));
   await expect(page.getByRole('alert')).toHaveText('Could not generate details. Try again or edit your entries.');await expect(page.getByRole('status')).toHaveCount(0);await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Keep');await expect(page.getByLabel('Title',{exact:true})).toBeFocused();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();await page.getByLabel('Title',{exact:true}).fill('Corrected');await expect(page.getByRole('alert')).toHaveCount(0);
  });
  await scenario(surface,'ordinary tag entry uses Enter without submitting or syntax',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Ordinary tags');
   await page.getByLabel('Tags',{exact:true}).fill('  Exact, tag  ');
   await page.getByLabel('Tags',{exact:true}).press('Enter');
   await expect(page.getByLabel('Tag 1',{exact:true})).toHaveValue('  Exact, tag  ');
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('');
   expect(await page.evaluate(()=>window.fixture.saves.length)).toBe(0);
   expect(await page.getByRole('form').innerText()).not.toMatch(/JSON|array|split/i);
  });
  await scenario(surface,'pending exact tag is included once on explicit Save without Enter',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Pending Save');await addTags(page,['Existing']);
   await page.getByLabel('Tags',{exact:true}).pressSequentially('  Exact, "tag"  ');
   await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves[0])).toEqual({ownerKey:'fixture-owner',sourceKey:'fixture-file',metadata:{title:'Pending Save',description:'',tags:['Existing','  Exact, "tag"  ']},generation_policy:'never'});
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('  Exact, "tag"  ');await expectTags(page,['Existing']);
   await page.getByLabel('Tags',{exact:true}).fill('literal\nnewline,not split');await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves[1].metadata.tags)).toEqual(['Existing','literal\nnewline,not split']);
   await page.getByRole('button',{name:'Remove tag 1',exact:true}).click();await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('literal\nnewline,not split');
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[2].metadata.tags)).toEqual(['literal\nnewline,not split']);
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(0);
  });
  await scenario(surface,'pending tag protects exact supplied metadata and survives generation then Add',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Held');await page.getByLabel('Tags',{exact:true}).fill('  pending, tag  ');
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[0].request.requested_fields)).toEqual(['description']);
   expect(await page.evaluate(()=>window.fixture.calls[0].request.supplied_metadata)).toEqual({title:'Held',tags:['  pending, tag  ']});
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Suggested'}));await expect(page.getByLabel('Description',{exact:true})).toHaveValue('Suggested');
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('  pending, tag  ');await expectTags(page,[]);
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.resolve(1,{description:'Must not apply',tags:['Must not overwrite pending']}));
   await expect(page.getByRole('alert')).toHaveText('Could not generate details. Try again or edit your entries.');
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('  pending, tag  ');await expect(page.getByLabel('Description',{exact:true})).toHaveValue('Suggested');
   await page.getByLabel('Description',{exact:true}).fill('Manual');
   await page.getByRole('button',{name:'Add tag',exact:true}).click();await expectTags(page,['  pending, tag  ']);await expect(page.getByLabel('Tags',{exact:true})).toBeFocused();
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[0].metadata.tags)).toEqual(['  pending, tag  ']);
  });
  await scenario(surface,'whitespace pending tag is user-authored; clearing all tags restores eligibility',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Held');await page.getByLabel('Description',{exact:true}).fill('Held');await page.getByLabel('Tags',{exact:true}).fill('   ');
   await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves[0].metadata.tags)).toEqual(['   ']);
   await page.getByLabel('Tags',{exact:true}).fill('');await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[0].request.requested_fields)).toEqual(['tags']);
   await page.evaluate(()=>window.fixture.resolve(0,{tags:['Generated']}));await expectTags(page,['Generated']);
   await page.getByLabel('Tag 1',{exact:true}).fill('x');await page.getByLabel('Tag 1',{exact:true}).fill('Generated');await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();
   await removeTags(page);await page.getByRole('button',{name:'Generate',exact:true}).click();expect(await page.evaluate(()=>window.fixture.calls[1].request.requested_fields)).toEqual(['tags']);
  });
  await scenario(surface,'ordinary tag edits and removal preserve order case duplicates and explicit empty strings',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Edit tags');await addTags(page,['Alpha','alpha','Alpha','']);
   await page.getByLabel('Tag 2',{exact:true}).fill('  alpha, beta  ');await expectTags(page,['Alpha','  alpha, beta  ','Alpha','']);
   await page.getByRole('button',{name:'Remove tag 2',exact:true}).click();await expectTags(page,['Alpha','Alpha','']);await expect(page.getByLabel('Tags',{exact:true})).toBeFocused();
   await page.getByLabel('Tag 1',{exact:true}).press('Enter');expect(await page.evaluate(()=>window.fixture.saves.length)).toBe(0);
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[0].metadata.tags)).toEqual(['Alpha','Alpha','']);
   await removeTags(page);await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[1].metadata.tags)).toEqual([]);
  });
  await scenario(surface,'initial invalid tags remain exact through rejected Saves until explicit correction',async page=>{
   const tags=['a\r\nb','a\rb','a\nb','\t','', ' x ','x','x'];
   await page.evaluate(tags=>window.fixture.reset({sourceKey:'invalid-tags',initialValues:{title:'Existing',description:'',tags},initialProvenance:{title:'user',tags:'user'}}),tags);
   await expect(page.getByLabel('Tag 8',{exact:true})).toHaveValue('x');
   await page.evaluate(()=>window.fixture.saveError({code:'metadata_invalid',message:'Invalid metadata: tags[0]/control'}));
   for(let attempt=0;attempt<2;attempt++){
    await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();await expect(page.getByLabel('Tag 1',{exact:true})).toBeFocused();
    expect(await page.evaluate(attempt=>window.fixture.saves[attempt].metadata.tags,attempt)).toEqual(tags);
   }
   await page.getByLabel('Tag 1',{exact:true}).fill('corrected');await page.evaluate(()=>window.fixture.saveError(null));
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[2].metadata.tags)).toEqual(['corrected','a\rb','a\nb','\t','', ' x ','x','x']);
  });
  for(const action of ['pending change-back','listed change-back','removal'])await scenario(surface,action+' fences every generated field',async page=>{
   const tags=action==='pending change-back'?[]:['Original'];
   await page.evaluate(tags=>window.fixture.reset({sourceKey:'tag-fencing',initialValues:{title:'Held',description:'',tags},initialProvenance:{title:'user'}}),tags);
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Held');await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[0].request.requested_fields)).toEqual(['description','tags']);
   if(action==='pending change-back'){await page.getByLabel('Tags',{exact:true}).fill('temporary');await page.getByLabel('Tags',{exact:true}).fill('');}
   else if(action==='listed change-back'){await page.getByLabel('Tag 1',{exact:true}).fill('temporary');await page.getByLabel('Tag 1',{exact:true}).fill('Original');}
   else await page.getByRole('button',{name:'Remove tag 1',exact:true}).click();
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Must not apply',tags:['Must not apply']}));
   await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');
   await expectTags(page,action==='listed change-back'?['Original']:[]);await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await expect(page.getByRole('status')).toHaveText('Your edits were kept.');
  });
  await scenario(surface,'typed fields protected and generation draft only',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Typed title');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await expect.poll(()=>page.evaluate(()=>window.fixture.calls.length)).toBe(1);
   expect(await page.evaluate(()=>window.fixture.calls[0].request.requested_fields)).toEqual(['description','tags']);
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Suggested',tags:[' tag ','tag','a\nb','']}));
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('Suggested');await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Typed title');
   expect(await page.evaluate(()=>window.fixture.saves)).toEqual([]);
  });
  await scenario(surface,'explicit Save submits complete exact values and never generates',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Typed title');
   await page.getByLabel('Description',{exact:true}).fill('  exact\ntext  ');
   await addTags(page,[' x ','x','x','a\nb','']);
   await page.getByRole('button',{name:'Save',exact:true}).click();
   await expect.poll(()=>page.evaluate(()=>window.fixture.saves.length)).toBe(1);
   expect(await page.evaluate(()=>window.fixture.saves[0])).toEqual({ownerKey:'fixture-owner',sourceKey:'fixture-file',metadata:{title:'Typed title',description:'  exact\ntext  ',tags:[' x ','x','x','a\nb','']},generation_policy:'never'});
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(0);
  });
  await scenario(surface,'typed default-looking text protected; clear eligible; whitespace protected',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.resolve(0,{title:'Default title',description:'Default description',tags:['default']}));
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Default title');
   await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByRole('status')).toHaveCount(0);
   await page.getByLabel('Title',{exact:true}).fill('x');await page.getByLabel('Title',{exact:true}).fill('Default title');
   await page.getByLabel('Description',{exact:true}).fill('   ');await removeTags(page);
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[1].request.requested_fields)).toEqual(['tags']);
   expect(await page.evaluate(()=>window.fixture.calls[1].request.supplied_metadata)).toEqual({description:'   ',title:'Default title'});
   await page.evaluate(()=>window.fixture.resolve(1,{tags:['new']}));await expectTags(page,['new']);
   await page.getByLabel('Tag 1',{exact:true}).fill('typed');await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();
   await page.getByLabel('Description',{exact:true}).fill('');await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[2].request.requested_fields)).toEqual(['description']);
   expect(await page.evaluate(()=>window.fixture.saves.length)).toBe(0);
  });
  await scenario(surface,'all-field edit including change-back discards response atomically',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Held');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.getByLabel('Title',{exact:true}).fill('Changed');await page.getByLabel('Title',{exact:true}).fill('Held');
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Must not apply',tags:['must not apply']}));
   await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');await expectTags(page,[]);
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Held');
   await expect(page.getByRole('status')).toHaveText('Your edits were kept.');await expect(page.getByRole('status')).toHaveAttribute('aria-live','polite');await expect(page.getByRole('status')).toHaveCount(1);
   await expect(page.getByLabel('Title',{exact:true})).toBeFocused();await expect(page.getByRole('alert')).toHaveCount(0);
   correctnessReceipts.push({surface,finding:'F3',message:await page.getByRole('status').innerText(),live:await page.getByRole('status').getAttribute('aria-live'),focused:await page.getByLabel('Title',{exact:true}).evaluate(n=>document.activeElement===n),values:{title:await page.getByLabel('Title',{exact:true}).inputValue(),description:await page.getByLabel('Description',{exact:true}).inputValue(),tags:await page.getByRole('textbox',{name:/^Tag \d+$/}).evaluateAll(nodes=>nodes.map(n=>n.value))}});
   await page.screenshot({path:join(proof,surface+'-edits-kept-status.png'),fullPage:true});
   for(const label of ['Title','Description','Tags']){await expect(page.getByLabel(label,{exact:true})).not.toHaveAttribute('aria-describedby');await expect(page.getByLabel(label,{exact:true})).not.toHaveAttribute('aria-invalid','true');}
   await page.getByLabel('Description',{exact:true}).fill('Manual');await expect(page.getByRole('status')).toHaveCount(0);
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('status')).toHaveCount(0);
   expect(await page.evaluate(()=>window.fixture.saves[0].metadata)).toEqual({title:'Held',description:'Manual',tags:[]});
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByLabel('Title',{exact:true}).fill('Newest');await page.evaluate(()=>window.fixture.resolve(1,{tags:['Discard']}));
   await expect(page.getByRole('status')).toHaveText('Your edits were kept.');
   const notice=await page.getByRole('status').elementHandle();await page.evaluate(()=>window.fixture.reset({generationAllowed:false}));expect(await notice.evaluate(n=>n.isConnected)).toBe(true);
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('status')).toHaveCount(0);
   await page.evaluate(()=>window.fixture.reset({generationAllowed:true}));await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByLabel('Title',{exact:true}).fill('Final');await page.evaluate(()=>window.fixture.resolve(2,{tags:['Discard']}));
   await expect(page.getByRole('status')).toHaveText('Your edits were kept.');await page.getByRole('button',{name:'Generate',exact:true}).click();await expect(page.getByRole('status')).toHaveCount(0);
   await page.evaluate(()=>window.fixture.resolve(3,{tags:['Fresh']}));await expectTags(page,['Fresh']);await expect(page.getByRole('status')).toHaveCount(0);
  });
  await scenario(surface,'generated defaults replace until user edits',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.resolve(0,{title:'First',description:'First',tags:['first']}));
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('First');
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.calls[1].request.requested_fields)).toEqual(['description','tags','title']);
   await page.evaluate(()=>window.fixture.resolve(1,{title:'Second',description:'Second',tags:['second']}));await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Second');
  });
  await scenario(surface,'Stop fences immediately; unknown completion cannot authorize Save',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Keep');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.cancel({state:'unknown'}));await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Late',tags:['late']}));
   await page.getByLabel('Description',{exact:true}).fill('Edited after stop');
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);expect(await page.evaluate(()=>window.fixture.checks.length)).toBe(1);
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('Edited after stop');await expectTags(page,[]);
   expect(await page.evaluate(()=>window.fixture.cancels[0].requestId===window.fixture.checks[0].requestId)).toBe(true);
  });
  await scenario(surface,'bounded status; quarantine does not release generation permit',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Keep');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.cancel('hang'));await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled({timeout:4000});
   await page.evaluate(()=>window.fixture.status({state:'quarantined',safeToSave:true,canGenerate:false}));
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Generate',exact:true})).toHaveCount(0);
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);
  });
  await scenario(surface,'stop then retry; old and duplicate results cannot replace newer result',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.resolve(1,{title:'New',description:'New',tags:['new']}));await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New');
   await page.evaluate(()=>{window.fixture.resolve(0,{title:'Old',description:'Old',tags:['old']});window.fixture.resolve(1,{title:'Duplicate',description:'Duplicate',tags:['duplicate']});});
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New');
   await expect(page.getByRole('status')).toHaveCount(0);
   expect(await page.evaluate(()=>window.fixture.calls[0].request.requestId!==window.fixture.calls[1].request.requestId)).toBe(true);
  });
  for(const identity of ['sourceKey','ownerKey'])await scenario(surface,identity+' reset fences old source and keeps Save blocked until safe',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.cancel({state:'unknown'}));
   await page.getByLabel('Tags',{exact:true}).fill('Old pending tag');
   await page.evaluate(identity=>window.fixture.reset({[identity]:'new-identity',initialValues:{title:'New source',description:'',tags:[]}}),identity);
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New source');
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('');await expectTags(page,[]);
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.evaluate(()=>window.fixture.resolve(0,{title:'Old identity',description:'Old identity',tags:['old']}));
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');await expect(page.getByLabel('Title',{exact:true})).toHaveValue('New source');
   await expect(page.getByRole('status')).toHaveCount(0);
  });
  await scenario(surface,'malformed result refuses atomic fill and Save; failures never leak backend text',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Keep');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Partial',tags:'not an array'}));
   await expect(page.getByRole('alert')).toHaveText('Could not generate details. Try again or edit your entries.');
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.getByLabel('Description',{exact:true}).fill('Manual');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
   await page.getByRole('button',{name:'Generate',exact:true}).click();await page.evaluate(()=>window.fixture.reject(1));
   await expect(page.getByRole('alert')).toHaveText('Could not confirm generation stopped. Check generation status.');
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();expect(await page.locator('body').innerText()).not.toContain('PRIVATE');
   await page.getByRole('button',{name:'Check generation status',exact:true}).click();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
  });
  // Replaces inherited local-rejection assertions: only the adapter may reject
  // title policy. These configured error responses are not a backend validator.
  for(const [name,title,rule,message] of [
   ['empty','', 'blank','Enter non-whitespace text for Title.'],
   ['whitespace','   ', 'blank','Enter non-whitespace text for Title.'],
   ['too long','a'.repeat(161),'scalar_limit','Use 1–160 characters for Title.'],
   ['leading space',' leading','edge_whitespace','Remove starting or ending whitespace from Title.'],
   ['trailing space','trailing ','edge_whitespace','Remove starting or ending whitespace from Title.']
  ])await scenario(surface,'explicit Save sends exact initial '+name+' title for authoritative rejection and keyboard retry',async page=>{
   const description='  exact\ntext  ',tags=['Alpha','Beta'],rejections=[];
   const request=(title,sourceKey='invalid-title-'+name)=>({ownerKey:'fixture-owner',sourceKey,metadata:{title,description,tags},generation_policy:'never'});
   // First establish successful explicit Save through the same adapter seam.
   await page.evaluate(({description,tags,sourceKey})=>window.fixture.reset({sourceKey,initialValues:{title:'Valid',description,tags}}),{description,tags,sourceKey:'valid-title-'+name});
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Valid');
   await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves)).toEqual([request('Valid','valid-title-'+name)]);await expect(page.getByRole('alert')).toHaveCount(0);
   await page.evaluate(({title,description,tags,sourceKey})=>window.fixture.reset({sourceKey,initialValues:{title,description,tags},initialProvenance:{title:'user',description:'user',tags:'user'}}),{title,description,tags,sourceKey:'invalid-title-'+name});
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue(title);await page.setViewportSize({width:320,height:650});
   await expect(page.getByLabel('Title',{exact:true})).not.toHaveAttribute('aria-invalid','true');await expect(page.getByRole('alert')).toHaveCount(0);
   await page.evaluate(rule=>window.fixture.saveError({code:'metadata_invalid',retryable:false,request_id:null,message:'Invalid metadata: title/'+rule}),rule);
   for(const method of ['click','Enter']){
    await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
    if(method==='click')await page.getByRole('button',{name:'Save',exact:true}).click();
    else{await page.getByLabel('Title',{exact:true}).focus();await page.keyboard.press('Enter');}
    const attempt=method==='click'?1:2;
    await expect.poll(()=>page.evaluate(()=>window.fixture.saves.length)).toBe(attempt+1);
    expect(await page.evaluate(attempt=>window.fixture.saves[attempt],attempt)).toEqual(request(title));
    await expect(page.getByRole('alert')).toHaveText(message);await expect(page.getByLabel('Title',{exact:true})).toBeFocused();
    await expect(page.getByLabel('Title',{exact:true})).toHaveAttribute('aria-invalid','true');
    await expect(page.getByLabel('Title',{exact:true})).toHaveAttribute('aria-describedby',await page.getByRole('alert').getAttribute('id'));
    for(const label of ['Description','Tags'])await expect(page.getByLabel(label,{exact:true})).not.toHaveAttribute('aria-describedby');
    await expect(page.getByLabel('Title',{exact:true})).toHaveValue(title);await expect(page.getByLabel('Description',{exact:true})).toHaveValue(description);await expectTags(page,tags);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    rejections.push({method,request:await page.evaluate(attempt=>window.fixture.saves[attempt],attempt),message:await page.getByRole('alert').innerText(),focused:await page.getByLabel('Title',{exact:true}).evaluate(n=>document.activeElement===n),associated:await page.getByLabel('Title',{exact:true}).getAttribute('aria-describedby')===await page.getByRole('alert').getAttribute('id')});
    if(name==='empty'&&method==='Enter')await page.screenshot({path:join(proof,surface+'-empty-title-error-320.png'),fullPage:true});
   }
   await page.getByLabel('Title',{exact:true}).fill('Corrected');await page.evaluate(()=>window.fixture.saveError(null));
   await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByLabel('Title',{exact:true})).not.toHaveAttribute('aria-invalid','true');
   await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves)).toEqual([request('Valid','valid-title-'+name),request(title),request(title),request('Corrected')]);
   expect(await page.evaluate(()=>({generation:window.fixture.calls.length,cancel:window.fixture.cancels.length,status:window.fixture.checks.length}))).toEqual({generation:0,cancel:0,status:0});
   titleReceipts.push({surface,name,configuredError:{code:'metadata_invalid',retryable:false,request_id:null,message:'Invalid metadata: title/'+rule},rejections,fixtureAttempts:await page.evaluate(()=>window.fixture.saves),generationCalls:await page.evaluate(()=>window.fixture.calls.length)});
  });
  await scenario(surface,'punctuation tags reach authoritative validation unchanged',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Valid');await addTags(page,['[bad']);
   await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();await expectTags(page,['[bad']);
   await page.getByRole('button',{name:'Save',exact:true}).click();expect(await page.evaluate(()=>window.fixture.saves[0].metadata.tags)).toEqual(['[bad']);
   await removeTags(page);await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
  });
  await scenario(surface,'structured validation errors use fixed copy, focus affected field, retain bytes',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Valid');await addTags(page,['x','X']);
   await page.evaluate(()=>window.fixture.saveError({code:'metadata_invalid',retryable:false,request_id:null,message:'Invalid metadata: tags[1]/duplicate'}));
   await page.getByRole('button',{name:'Save',exact:true}).click();
   await expect(page.getByRole('alert')).toHaveText('Remove repeated tags, including capitalization variants.');
   await expect(page.getByLabel('Tag 2',{exact:true})).toBeFocused();await expectTags(page,['x','X']);
   await expect(page.getByLabel('Tag 2',{exact:true})).toHaveAttribute('aria-describedby',await page.getByRole('alert').getAttribute('id'));
   await page.evaluate(()=>window.fixture.saveError({code:'metadata_invalid',message:'Invalid metadata: title/blank'}));
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('Enter non-whitespace text for Title.');await expect(page.getByLabel('Title',{exact:true})).toBeFocused();await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Valid');
   await page.evaluate(()=>window.fixture.saveError({code:'metadata_invalid',retryable:false,request_id:null,message:'Invalid metadata: description/edge_whitespace PRIVATE'}));
   await page.getByRole('button',{name:'Save',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('Details could not be validated. Review your entries and try again.');
   expect(await page.locator('body').innerText()).not.toContain('PRIVATE');
   await page.getByLabel('Title',{exact:true}).fill('\ufeffUnicode title');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
  });
  for(const edited of ['description','tags'])await scenario(surface,edited+' edit during generation discards every suggestion',async page=>{
   await page.getByRole('button',{name:'Generate',exact:true}).click();
   if(edited==='tags')await addTags(page,['typed']);else await page.getByLabel('Description',{exact:true}).fill('Typed');
   await page.evaluate(()=>window.fixture.resolve(0,{title:'Must not apply',description:'Must not apply',tags:['must not apply']}));
   await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('');
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue(edited==='description'?'Typed':'');
   await expectTags(page,edited==='tags'?['typed']:[]);
   await expect(page.getByRole('status')).toHaveText('Your edits were kept.');
  });
  await scenario(surface,'unfinished ordinary tag edit fences generation and remains visible',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Held');await page.getByRole('button',{name:'Generate',exact:true}).click();await page.getByLabel('Tags',{exact:true}).fill('[unfinished');
   await page.evaluate(()=>window.fixture.resolve(0,{description:'Discard',tags:['discard']}));
   await expect(page.getByLabel('Tags',{exact:true})).toHaveValue('[unfinished');await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Held');
   await expect(page.getByLabel('Description',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeEnabled();
  });
  await scenario(surface,'status timeout and non-durable stopped reply fail closed without retries',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Keep');await page.getByRole('button',{name:'Generate',exact:true}).click();
   await page.evaluate(()=>window.fixture.cancel({state:'stopped',safeToSave:false,canGenerate:true}));await page.getByRole('button',{name:'Stop generating',exact:true}).click();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
   await page.evaluate(()=>window.fixture.status('hang'));await page.getByRole('button',{name:'Check generation status',exact:true}).click();
   await expect(page.getByRole('button',{name:'Check generation status',exact:true})).toBeEnabled({timeout:4000});
   expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(1);expect(await page.evaluate(()=>window.fixture.checks.length)).toBe(1);await expect(page.getByRole('button',{name:'Save',exact:true})).toBeDisabled();
  });
  await scenario(surface,'complete explicit empty values and initial provenance survive Save',async page=>{
   await page.evaluate(()=>window.fixture.reset({sourceKey:'initialized',initialValues:{title:'Existing',description:'',tags:[]},initialProvenance:{title:'user'}}));
   await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Existing');
   await page.getByRole('button',{name:'Save',exact:true}).click();
   expect(await page.evaluate(()=>window.fixture.saves[0].metadata)).toEqual({title:'Existing',description:'',tags:[]});
   await page.getByRole('button',{name:'Generate',exact:true}).click();expect(await page.evaluate(()=>window.fixture.calls[0].request.requested_fields)).toEqual(['description','tags']);
  });
  await scenario(surface,'light/dark token fixtures, live 320px resize, visible keyboard focus and reachable actions',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Theme check');
   await addTags(page,['Project notes','Exact, punctuation','A-long-tag-that-must-not-make-the-form-overflow-at-320-pixels']);
   await page.getByLabel('Tags',{exact:true}).fill('Pending tag');
   const themes=[];
   for(const mode of ['light','dark']){
    await page.evaluate(mode=>{
     // Theme TOKEN fixture only, not the host settings controller or an OS signal.
     const dark=mode==='dark',root=document.documentElement,bg=dark?'#172127':'#f8faff',fg=dark?'#edf2f7':'#17171a';
     root.classList.toggle('dark',dark);root.style.colorScheme=mode;
     for(const [key,value] of Object.entries({'--theme-foreground':fg,'--theme-background-seed':bg,'--theme-card-seed':bg,'--theme-elevated-seed':bg,'--background':bg,'--background-base':bg,'--background-alpha':'1','--midground':fg,'--midground-base':fg,'--midground-alpha':'1','--foreground':fg,'--color-background':bg,'--color-foreground':fg}))root.style.setProperty(key,value);
     document.body.style.background=bg;document.body.style.color=fg;
    },mode);
    for(const width of [1000,320]){
     await page.setViewportSize({width,height:650});await expect(page.getByLabel('Title',{exact:true})).toHaveValue('Theme check');
     expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
     for(const label of ['Title','Description','Tags']){const bounds=await page.getByLabel(label,{exact:true}).boundingBox();expect(bounds.width).toBeGreaterThan(80);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);}
     const keyboard=[['textbox','Description'],['textbox','Tags'],['textbox','Tag 1'],['button','Remove tag 1'],['textbox','Tag 2'],['button','Remove tag 2'],['textbox','Tag 3'],['button','Remove tag 3'],['button','Add tag'],['button','Generate'],['button','Save']];
     await page.getByLabel('Title',{exact:true}).focus();
     for(const [role,name] of keyboard){
      await page.keyboard.press('Tab');const control=page.getByRole(role,{name,exact:true});await expect(control).toBeFocused();
      const focus=await control.evaluate(n=>{const s=getComputedStyle(n),r=n.getBoundingClientRect();return {visible:n.matches(':focus-visible'),outline:s.outlineStyle,width:parseFloat(s.outlineWidth),color:s.outlineColor,x:r.x,right:r.right};});
      expect(focus.visible).toBe(true);expect(focus.outline).toBe('solid');expect(focus.width).toBeGreaterThanOrEqual(2);expect(focus.color).not.toBe('rgba(0, 0, 0, 0)');expect(focus.x).toBeGreaterThanOrEqual(2);expect(focus.right).toBeLessThanOrEqual(width-2);
      if(width===320&&name==='Tag 1')await page.screenshot({path:join(proof,surface+'-'+mode+'-tag-focus-320.png'),fullPage:true});
      if(width===320&&name==='Tag 3'){
       await page.keyboard.press('Control+End');
       expect(await control.evaluate(n=>n.scrollLeft)).toBeGreaterThan(0);
       await expect(control).toHaveValue('A-long-tag-that-must-not-make-the-form-overflow-at-320-pixels');
      }
     }
     const appearance=await page.getByLabel('Description',{exact:true}).evaluate(n=>({color:getComputedStyle(n).color,background:getComputedStyle(n).backgroundColor,surface:getComputedStyle(document.body).backgroundColor}));
     themeReceipts.push({surface,mode,width,appearance,keyboardFocusChecked:keyboard.map(([,name])=>name)});if(width===320){themes.push(appearance);await page.screenshot({path:join(proof,surface+'-'+mode+'-320.png'),fullPage:true});}
    }
   }
   expect(themes[0].surface).not.toBe(themes[1].surface);expect(themes[0].color).not.toBe(themes[1].color);
  });
  await scenario(surface,'keyboard Enter saves not generates; textarea Enter edits',async page=>{
   await page.getByLabel('Title',{exact:true}).fill('Keyboard');await page.getByLabel('Description',{exact:true}).focus();
   await page.keyboard.press('Enter');await expect(page.getByLabel('Description',{exact:true})).toHaveValue('\n');
   await page.getByLabel('Title',{exact:true}).focus();await page.keyboard.press('Enter');
   await expect.poll(()=>page.evaluate(()=>window.fixture.saves.length)).toBe(1);expect(await page.evaluate(()=>window.fixture.calls.length)).toBe(0);
   await page.getByLabel('Title',{exact:true}).focus();await page.keyboard.press('Tab');await expect(page.getByLabel('Description',{exact:true})).toBeFocused();
   await page.keyboard.press('Tab');await expect(page.getByLabel('Tags',{exact:true})).toBeFocused();
   await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'Generate',exact:true})).toBeFocused();
   await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'Save',exact:true})).toBeFocused();
  });
 }
 const expectedCases=process.env.METADATA_FORM_CASE?2:82;
 expect(rows).toHaveLength(expectedCases);expect(new Set(rows.map(row=>row.surface+' / '+row.name)).size).toBe(expectedCases);expect(rows.every(row=>row.passed)).toBe(true);
 console.log(JSON.stringify({passed:rows.filter(r=>r.passed).length,total:rows.length,expectedCases}));
}finally{
 await browser?.close();if(server)await new Promise(r=>server.close(r));if(xvfb){xvfb.kill();await new Promise(r=>xvfb.once('exit',r));}await rm(scratch,{recursive:true,force:true});
 const changed=[];for(const [path,hash] of Object.entries(inputs))if(sha(await readFile(join(root,path)))!==hash)changed.push(path);
 for(const [path,hash] of Object.entries(hostInputs))if(sha(await readFile(path))!==hash)changed.push(path);
 const absent=path=>stat(path).then(()=>false,e=>e.code==='ENOENT');
 const cleanup={serverClosed:!server?.listening,browserClosed:!browser?.isConnected(),temporaryBuildRemoved:await absent(scratch),browserProcessGone:!browserIdentity||await absent('/proc/'+browserIdentity.pid),browserProfileRemoved:!browserIdentity||await absent(browserIdentity.profile),ownedDisplayStopped:!xvfb||xvfb.exitCode!==null||xvfb.signalCode!==null};
 await writeFile(join(proof,'results.json'),JSON.stringify({browser:browser?.version(),browserIdentity,headful:true,node:process.version,completedAt:new Date().toISOString(),scope:'Fixture adapter; actual ReactDOM and Desktop/Dashboard presentation components. Token fixtures for light/dark, not native host integration or OS signal verification.',filter:process.env.METADATA_FORM_CASE||null,rows,passed:rows.filter(r=>r.passed).length,total:rows.length,expectedCases:82,complete:!process.env.METADATA_FORM_CASE&&rows.length===82&&rows.every(r=>r.passed)&&changed.length===0&&Object.values(cleanup).every(Boolean),themeReceipts,titleReceipts,correctnessReceipts,changedInputs:changed,cleanup},null,2));
 if(changed.length)throw Error('Inputs changed during run: '+changed.join(', '));
 if(!Object.values(cleanup).every(Boolean))throw Error('Fixture cleanup incomplete');
}
