/* Native loaders, real React, native authenticated Python API, fictional bank.
 * SDK host state/IPC/UI-kit boundaries are doubles; this is NOT Electron QA.
 */
import {build} from 'esbuild';
import {mkdtemp, readFile, rm, mkdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createServer} from 'node:net';
import {chromium,expect} from '@playwright/test';

const root=resolve('.');
const source=process.env.HERMES_SOURCE||join(process.env.HOME,'.hermes/hermes-agent');
const proof=process.env.SAVED_PROOF_DIR||join(process.env.TMPDIR||tmpdir(),'saved-ui-proof');
await mkdir(proof,{recursive:true});
const peer=process.env.SAVED_PEER_REPO||resolve(root,'..',root.endsWith('bookmarks')?'hermes-delivery-shelf':'hermes-conversation-bookmarks');
// Fail before starting a browser/server, rather than silently testing old or absent UI.
for(const repo of [root,peer]){
 try{for(const file of ['ui/Saved.jsx','desktop/plugin.js','dashboard/dist/index.js','tests/saved-browser.mjs'])await readFile(join(repo,file));}
 catch{throw new Error('Paired Saved verification requires both built local repositories. Set SAVED_PEER_REPO; see docs/SAVED_UI.md. Missing inputs in '+repo);}
}
for(const file of ['ui/Saved.jsx','ui/saved-coordinator.js','tests/saved-browser.mjs','tests/saved_browser_server.py']){
 if(!(await readFile(join(root,file))).equals(await readFile(join(peer,file))))throw new Error('Paired Saved revisions differ: '+file+'. Build matching local changes; CI does not fetch an unpublished companion. See docs/SAVED_UI.md.');
}
const scratch=await mkdtemp(join(process.env.TMPDIR||tmpdir(),'q-'));
const port=await new Promise(r=>{const s=createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
const common=`import React from 'react';import {createRoot} from 'react-dom/client';
window.__QA_REACT__=React;
const root=createRoot(document.getElementById('root'));
window.__QA_REQUESTS__=[];
async function fetchJSON(path,opts={}) {
 window.__QA_REQUESTS__.push({path,method:opts.method||'GET'});
 const response=await fetch(path,{...opts,headers:{...opts.headers,'X-Hermes-Session-Token':'fictional-test-session'}});
 const data=await response.json();if(!response.ok){
  if(location.pathname.startsWith('/qa/desktop'))throw new Error("Error invoking remote method 'hermes:api': Error: "+response.status+': '+JSON.stringify(data));
  throw Object.assign(new Error(typeof data.detail==='string'?data.detail:'Request refused'),{status:response.status});
 }return data;
}
window.__QA_FETCH__=fetchJSON;
`;
const apiStub=`export const HERMES_BASE_PATH='';export const fetchJSON=(...a)=>window.__QA_FETCH__(...a);export const authedFetch=fetchJSON;export const buildWsUrl=()=>'';export const buildWsAuthParam=()=>'';export const api={getPlugins:async(profile)=>(await fetchJSON('/api/dashboard/plugins?profile='+profile))};`;
const uiStub=`export const Badge=()=>null,Button=()=>null,Checkbox=()=>null,ConfirmDialog=()=>null,Dialog=()=>null,DialogClose=()=>null,DialogContent=()=>null,DialogDescription=()=>null,DialogFooter=()=>null,DialogHeader=()=>null,DialogTitle=()=>null,Toast=()=>null,useConfirmDelete=()=>null,useToast=()=>null,Select=()=>null,SelectOption=()=>null,Card=()=>null,CardHeader=()=>null,CardTitle=()=>null,CardContent=()=>null,Input=()=>null,Label=()=>null,Separator=()=>null,Tabs=()=>null,TabsList=()=>null,TabsTrigger=()=>null;`;
const dashEntry=common+`
import {exposePluginSDK,getPluginComponent,onPluginRegistered} from '${source}/web/src/plugins/registry.ts';
import {PluginSlot} from '${source}/web/src/plugins/slots.ts';
import {usePlugins} from '${source}/web/src/plugins/usePlugins.ts';
exposePluginSDK();
function App(){
 const [profile,setProfile]=React.useState('default');window.__QA_PROFILE__=setProfile;
 const [collapsed,setCollapsed]=React.useState(false);window.__QA_COLLAPSE__=setCollapsed;
 const {manifests,loading}=usePlugins(profile);window.__QA_MANIFESTS__=manifests;window.__QA_READY__=!loading;
 const name=manifests.find(m=>m.tab.path===location.pathname)?.name||manifests[0]?.name;
 const Component=React.useSyncExternalStore(onPluginRegistered,()=>getPluginComponent(name)||null);
 // Official App.tsx:577 banner is outside sidebar; :612-618 hides header-left.
 return <><nav aria-label="Native banner slot"><PluginSlot name="header-banner"/></nav><aside><div style={{display:collapsed?'none':'flex'}}><PluginSlot name="header-left"/></div></aside>{Component?<Component/>:<p>Native Dashboard loader…</p>}</>;
}
root.render(<App/>);
window.__QA_UNMOUNT__=()=>root.unmount();
`;
const sdkStub=`import React from 'react';import {atom} from 'nanostores';
export const host={state:{profile:atom('default'),connectionId:atom('fixture')},navigate:path=>{window.__QA_NAVIGATED__=path;},openSession:async(id,options)=>{window.__QA_OPENED__={id,options};}};
export const useValue=a=>React.useSyncExternalStore(a.subscribe,a.get,a.get);
export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav';
window.__QA_SDK__={host,useValue,ROUTES_AREA,SIDEBAR_NAV_AREA};
export function installPluginSdk(){}
const blob=s=>URL.createObjectURL(new Blob([s],{type:'text/javascript'}));
export const sdkImportMap=()=>({
 'react':blob('export default window.__QA_REACT__;export const {useState,useEffect,useRef,useId,useMemo}=window.__QA_REACT__;'),
 '@hermes/plugin-sdk':blob('export const {host,useValue,ROUTES_AREA,SIDEBAR_NAV_AREA}=window.__QA_SDK__;')
});`;
const contextStub=`import {registry} from '${source}/apps/desktop/src/contrib/registry.ts';
export function createPluginContext(id,track){return {registerMany(items){const dispose=registry.registerMany(items.map(c=>({...c,id:id+':'+c.id,source:'plugin:'+id})));track(dispose);return dispose;},onDispose:track,os:{writeClipboard:async(text)=>{window.__QA_CLIPBOARD__=text;return true;}},rest:(path,opts={})=>window.__QA_FETCH__('/api/plugins/'+id+path,{method:opts.method||'GET',headers:opts.body?{'Content-Type':'application/json'}:undefined,body:opts.body?JSON.stringify(opts.body):undefined})};}`;
const desktopEntry=common+`
import {loadRuntimePlugin,unloadRuntimePlugin} from '${source}/apps/desktop/src/contrib/runtime-loader.ts';
import {registry,$registryVersion} from '${source}/apps/desktop/src/contrib/registry.ts';
import {setPluginEnabled,$pluginRecords} from '${source}/apps/desktop/src/contrib/plugins-store.ts';
window.__QA_REGISTRY__=registry;
window.__QA_HISTORY__=[];
registry.subscribe(()=>{window.__QA_HISTORY__.push({routes:registry.getArea('routes').length,nav:registry.getArea('sidebar.nav').length});});
const fixture=await fetchJSON('/api/qa/fixture');
const ids=new URLSearchParams(location.search).get('order')==='reverse'?[...fixture.installed].reverse():fixture.installed;
const codes={};
window.__QA_LOAD__=async(id)=>loadRuntimePlugin(codes[id],id,{file:'fixture/'+id+'/plugin.js',defaultEnabled:fixture.frontend.includes(id)});
window.__QA_UNLOAD__=unloadRuntimePlugin;
window.__QA_TOGGLE__=setPluginEnabled;
window.__QA_RECORDS__=$pluginRecords;
function App(){
 React.useSyncExternalStore($registryVersion.subscribe,$registryVersion.get,$registryVersion.get);
 const routes=registry.getArea('routes'),nav=registry.getArea('sidebar.nav');
 return <><nav aria-label="Native contributions">{nav.map(c=><a key={c.id} href={c.data.path}>{c.data.label}</a>)}</nav>{routes[0]?React.createElement(routes[0].render):<p>No active Saved plugins.</p>}</>;
}
root.render(<App/>);
for(const id of ids){codes[id]=await (await fetch('/api/qa/desktop/'+id,{headers:{'X-Hermes-Session-Token':'fictional-test-session'}})).text();await window.__QA_LOAD__(id);}
window.__QA_READY__=true;
`;
const stubPlugin={name:'host-boundary-doubles',setup(b){
 b.onResolve({filter:/^(react|react-dom|nanostores)(\/.*)?$/},args=>({path:resolve(root,'node_modules',args.path==='react'?'react/index.js':args.path==='react-dom'?'react-dom/index.js':args.path==='react-dom/client'?'react-dom/client.js':args.path==='nanostores'?'nanostores/index.js':args.path)}));
 b.onResolve({filter:/^(@\/|@nous-research\/)/},args=>{
  if(args.path==='@/lib/api')return {path:'api',namespace:'qa'};
  if(args.path==='@/lib/profile-bootstrap')return {path:'profile',namespace:'qa'};
  if(args.path==='@/lib/utils')return {path:'utils',namespace:'qa'};
  if(args.path==='@/i18n')return {path:'i18n',namespace:'qa'};
  if(args.path.startsWith('@nous-research/'))return {path:'ui',namespace:'qa'};
  if(args.path==='@/sdk/runtime')return {path:'sdk',namespace:'qa'};
  if(args.path==='@/lib/desktop-fs')return {path:'fs',namespace:'qa'};
  if(args.path==='@/store/notifications')return {path:'notifications',namespace:'qa'};
  throw new Error('Unexpected host import '+args.path);
 });
 b.onResolve({filter:/^\.\/(events|plugin)$/},args=>{
  if(args.importer.endsWith('/contrib/runtime-loader.ts'))return {path:args.path.slice(2),namespace:'qa'};
 });
 b.onLoad({filter:/.*/,namespace:'qa'},args=>({contents:({api:apiStub,profile:'export const dashboardServingProfile=()=>"default";',utils:'export const cn=(...a)=>a.join(" "),timeAgo=()=>"",isoTimeAgo=()=>"";',i18n:'export const useI18n=()=>({t:{}});',ui:uiStub,sdk:sdkStub,fs:'export const isReadFileErrorResult=()=>false;',notifications:'export const notifyError=(e)=>{throw e;};',events:'export const trackGatewayEventDisposers=(track,fn)=>fn();',plugin:contextStub})[args.path],loader:'js',resolveDir:root}));
}};
const pins={};
for(const repo of [root,peer])for(const file of ['desktop/plugin.js','dashboard/dist/index.js','dashboard/manifest.json','ui/Saved.jsx','ui/saved-coordinator.js','ui/saved.css','ui/desktop.jsx','ui/dashboard.jsx',repo.endsWith('bookmarks')?'ui/Bookmarks.jsx':'ui/Shelf.jsx','tests/saved-browser.mjs','tests/saved_browser_server.py','docs/SAVED_UI.md'])pins[join(repo,file)]=createHash('sha256').update(await readFile(join(repo,file))).digest('hex');
async function independentState(page,fixture,api,base,auth,scenario,order){
 await page.waitForFunction(()=>window.__QA_READY__);
 await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
 const available=fixture.frontend.filter(id=>fixture.enabled.includes(id));
 await expect(page.getByRole('tab')).toHaveCount(available.length);
 if(available.length)await expect(page.getByRole('button',{name:'Saved '+available[0],exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:/Install or enable/})).toHaveCount(2-available.length);
 await expect(page.getByText(/Could not open your shelf|Could not load bookmarks|Plugin not found/)).toHaveCount(0);
 expect(await page.evaluate(()=>window.__QA_REQUESTS__.every(r=>r.method==='GET'))).toBe(true);
 for(const width of [360,768,1440]){
  await page.setViewportSize({width,height:1000});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await page.locator('.hs-saved-tabs button,.hs-saved-missing button,.hs-saved-link').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().height>0).every(n=>n.getBoundingClientRect().height>=44))).toBe(true);
  await page.screenshot({path:join(proof,`${scenario}-desktop-${order}-${width}.png`),fullPage:true});
 }
 const changed=[];
 try{
  for(const id of fixture.frontend.filter(id=>!fixture.enabled.includes(id))){
   const label=id==='delivery-shelf'?'deliverables':'bookmarks';
   await page.getByRole('button',{name:'Install or enable '+label}).click();
   expect(await page.evaluate(()=>window.__QA_NAVIGATED__)).toBe('/capabilities?tab=plugins');
   const result=await fetch(base+'/api/qa/backend/'+id+'/true',{method:'POST',headers:auth});expect(result.ok).toBe(true);changed.push(id);
   expect((await api(id,'/status')).profile).toBe('default');
   await page.getByRole('button',{name:'Retry '+label,exact:true}).click();
   await expect(page.getByRole('tab')).toHaveCount(available.length+changed.length);
   await expect(page.getByRole('button',{name:'Install or enable '+label})).toHaveCount(0);
  }
  expect(await page.evaluate(()=>window.__QA_HISTORY__.every(x=>x.routes<=1&&x.nav<=1))).toBe(true);
 }finally{
  for(const id of changed){
   expect((await fetch(base+'/api/qa/backend/'+id+'/false',{method:'POST',headers:auth})).ok).toBe(true);
   expect((await fetch(base+'/api/plugins/'+id+'/status',{headers:auth})).status).toBe(404);
  }
 }
}
async function availabilityFailures(page,adapter){
 const pattern='**/api/plugins/delivery-shelf/status*';
 for(const failure of [401,403,503,'network']){
  await page.route(pattern,route=>failure==='network'?route.abort('failed'):route.fulfill({status:failure,contentType:'application/json',body:JSON.stringify({detail:'Fictional status failure'})}));
  await page.reload();
  const availability=page.locator('[aria-label="Deliverables availability"]');
  await expect(availability).toContainText(failure===401||failure===403?'Access could not be verified':'Could not check availability');
  await expect(page.getByRole('button',{name:/Install or enable/})).toHaveCount(0);
  await expect(page.getByRole('tab',{name:'Deliverables',exact:true})).toHaveCount(0);
  await page.unroute(pattern);
  await availability.getByRole('button',{name:'Retry deliverables',exact:true}).click();
  await expect(page.getByRole('tab')).toHaveCount(2);
  await page.getByRole('tab',{name:'Deliverables',exact:true}).click();
  await expect(page.getByRole('button',{name:'Saved delivery-shelf',exact:true})).toBeVisible();
 }
 if(adapter==='desktop'){
  let release,seen;
  const entered=new Promise(r=>seen=r),blocked=new Promise(r=>release=r);
  let first=true;
  await page.route(pattern,async route=>{if(!first){await route.continue();return;}first=false;seen();await blocked;await route.fulfill({status:404,contentType:'application/json',body:'{"detail":"Plugin not found"}'});});
  await page.evaluate(()=>window.__QA_SDK__.host.state.connectionId.set('held-connection'));
  await entered;
  await expect(page.getByRole('tab',{name:'Deliverables',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Saved delivery-shelf',exact:true})).toHaveCount(0);
  await page.evaluate(()=>window.__QA_SDK__.host.state.connectionId.set('recovered-connection'));
  await expect(page.getByRole('tab')).toHaveCount(2);
  release();await page.unroute(pattern,{behavior:'wait'});
  await expect(page.getByRole('button',{name:/Install or enable/})).toHaveCount(0);
  await expect(page.getByRole('tab')).toHaveCount(2);
 }
}
let server,browser;
const rows=[];
const auth={'X-Hermes-Session-Token':'fictional-test-session','Content-Type':'application/json'};
async function stop(){if(server&&server.exitCode===null){server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));}server=null;}
try{
 for(const [name,contents] of [['dashboard',dashEntry],['desktop',desktopEntry]])await build({stdin:{contents,resolveDir:root,loader:'jsx'},outfile:join(scratch,name+'.js'),bundle:true,format:'esm',target:'es2022',nodePaths:[join(root,'node_modules')],define:{'import.meta.env.DEV':'false','process.env.NODE_ENV':'"production"'},plugins:[stubPlugin]});
 browser=await chromium.launch({headless:true});
 const base=`http://127.0.0.1:${port}`;
 for(const scenario of ['both','conversation-bookmarks-only','delivery-shelf-only','conversation-bookmarks-disabled','delivery-shelf-disabled','both-disabled','ui-both--conversation-bookmarks-disabled','ui-both--delivery-shelf-disabled','ui-both--both-disabled','ui-bookmarks--both','ui-shelf--both']){
  server=spawn(process.env.PYTHON||'python',['tests/saved_browser_server.py',String(port),scratch,scenario],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',HERMES_SOURCE:source},stdio:['ignore','pipe','pipe']});
  let logs='';server.stderr.on('data',b=>logs+=b);
  for(let n=0;n<150;n++){try{if((await fetch(base+'/qa/dashboard')).ok)break;}catch{}if(server.exitCode!==null)throw new Error(logs);await new Promise(r=>setTimeout(r,100));if(n===149)throw new Error('Server failed: '+logs);}
  const fixture=await (await fetch(base+'/api/qa/fixture',{headers:auth})).json();
  const api=async(id,path,opts={})=>{const response=await fetch(base+'/api/plugins/'+id+path,{...opts,headers:auth});if(!response.ok)throw new Error(await response.text());return response.json();};
  for(const id of ['conversation-bookmarks','delivery-shelf']){
   expect((await fetch(base+'/api/plugins/'+id+'/status')).status).toBe(401);
   if(!fixture.enabled.includes(id)){expect((await fetch(base+'/api/plugins/'+id+'/status',{headers:auth})).status).toBe(404);continue;}
   const fields=id==='conversation-bookmarks'?{session_id:'fictional-session-01',note:'Fictional bookmark, independently stored.'}:{description:'Fictional deliverable, independently stored.',file:{root:'workspaces',path:'example.md'}};
   const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Saved '+id,...fields})});
   expect((await api(id,'/entries/'+entry.id)).title).toBe('Saved '+id);
  }
  for(const adapter of (scenario.startsWith('ui-')?['desktop']:['dashboard','desktop']))for(const order of ['forward','reverse']){
   const context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   // Delay one real script response, not data substitution, to force both load orders.
   if(adapter==='dashboard'&&fixture.enabled.length===2){const delayed=order==='forward'?'delivery-shelf':'conversation-bookmarks';await page.route('**/dashboard-plugins/**/'+delayed+'/dist/index.js',async route=>{await new Promise(r=>setTimeout(r,350));await route.continue();});}
   await page.goto(base+'/qa/'+adapter+'?order='+order);
   try{
    if(scenario.startsWith('ui-')){
     await independentState(page,fixture,api,base,auth,scenario,order);
     expect(errors).toEqual([]);rows.push({scenario,adapter,order,passed:true});console.log('PASS',scenario,adapter,order);continue;
    }
    if(!fixture.enabled.length){
     await page.waitForFunction(()=>window.__QA_READY__);
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(0);
     await expect(page.getByRole('heading',{name:'Saved',exact:true})).toHaveCount(0);
     expect(errors).toEqual([]);rows.push({scenario,adapter,order,passed:true});console.log('PASS',scenario,adapter,order);continue;
    }
    await expect(page.getByRole('heading',{name:'Saved',exact:true})).toBeVisible();
    await expect(page.getByRole('tab')).toHaveCount(fixture.enabled.length);
    if(adapter==='desktop')await page.waitForFunction(()=>window.__QA_READY__);
    await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
    if(adapter==='dashboard'){
     await page.evaluate(()=>window.__QA_COLLAPSE__(true));
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toBeVisible();
     await page.evaluate(()=>window.__QA_COLLAPSE__(false));
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toBeVisible();
     expect(await page.evaluate(()=>window.__QA_MANIFESTS__.filter(m=>['delivery-shelf','conversation-bookmarks'].includes(m.name)).every(m=>m.tab.hidden))).toBe(true);
     const href=await page.getByRole('link',{name:'Saved',exact:true}).getAttribute('href');
     expect(fixture.enabled.map(id=>'/'+id)).toContain(href);
     await page.getByRole('link',{name:'Saved',exact:true}).click();await expect(page).toHaveURL(base+href);
     await expect(page.getByRole('heading',{name:'Saved',exact:true})).toBeVisible();await expect(page.getByRole('tab')).toHaveCount(fixture.enabled.length);await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
    }else{
     expect(await page.getByRole('link',{name:'Saved',exact:true}).getAttribute('href')).toBe('/saved');
     expect(await page.evaluate(()=>window.__QA_HISTORY__.every(x=>x.routes<=1&&x.nav<=1))).toBe(true);
    }
    for(const id of fixture.enabled){
     const label=id==='conversation-bookmarks'?'Bookmarks':'Deliverables';
     await page.getByRole('tab',{name:label,exact:true}).click();
     await expect(page.getByRole('button',{name:'Saved '+id,exact:true})).toBeVisible();
     // Edit through each independently scoped UI transport; verify actual backend.
     await page.getByRole('button',{name:'Saved '+id,exact:true}).click();
     const dialog=page.getByRole('dialog');
     await dialog.getByRole('button',{name:id==='conversation-bookmarks'?'Edit bookmark':'Edit metadata'}).click();
     const field=id==='conversation-bookmarks'?dialog.getByLabel('Note',{exact:false}):dialog.getByLabel('Description',{exact:false});
     const value=adapter+' '+order+' verified';await field.fill(value);
     await dialog.getByRole('button',{name:'Save changes'}).click();await expect(dialog).not.toBeVisible();
     const list=await api(id,'/entries');expect(list.total).toBe(1);expect(list.items[0][id==='conversation-bookmarks'?'note':'description']).toBe(value);
    }
    await expect(page.getByRole('button',{name:'Saved '+fixture.enabled[fixture.enabled.length-1],exact:true})).toBeVisible();
    await expect(page.getByText(/Loading (your shelf|registered deliveries|bookmarks)/)).toHaveCount(0);
    for(const width of [360,768,1440]){
     await page.setViewportSize({width,height:1000});
     expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
     expect(await page.locator('.hs-saved-tabs button,.hs-saved-missing button,.hs-saved-link').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().height>0).every(n=>n.getBoundingClientRect().height>=44))).toBe(true);
     await page.screenshot({path:join(proof,`${scenario}-${adapter}-${order}-${width}.png`),fullPage:true});
    }
    if(scenario==='both')await availabilityFailures(page,adapter);
    if(fixture.enabled.length===2){
     await page.getByRole('tab',{name:'Bookmarks',exact:true}).focus();await page.keyboard.press('ArrowRight');await expect(page.getByRole('tab',{name:'Deliverables',exact:true})).toBeFocused();await expect(page.getByRole('tab',{name:'Deliverables',exact:true})).toHaveAttribute('aria-selected','true');
     if(adapter==='desktop'){
      for(const id of ['conversation-bookmarks','delivery-shelf']){
       await page.evaluate(id=>window.__QA_TOGGLE__(id,false),id);
       await expect(page.getByRole('tab')).toHaveCount(1);await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
       await expect(page.getByRole('button',{name:/Install or enable/})).toHaveCount(1);
       await page.evaluate(id=>window.__QA_TOGGLE__(id,true),id);
       await expect(page.getByRole('tab')).toHaveCount(2);await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
       // Native file reload and permanent unload, not only the toggle double.
       await page.evaluate(id=>window.__QA_LOAD__(id),id);await expect(page.getByRole('tab')).toHaveCount(2);
      }
      expect(await page.evaluate(()=>window.__QA_HISTORY__.every(x=>x.routes<=1&&x.nav<=1))).toBe(true);
     }
    }else{
     const missing=fixture.enabled[0]==='conversation-bookmarks'?'deliverables':'bookmarks';
     await expect(page.getByRole('button',{name:'Install or enable '+missing})).toBeVisible();
     const writesBefore=await page.evaluate(()=>window.__QA_REQUESTS__.filter(x=>x.method!=='GET').length);
     if(adapter==='desktop'){
      await page.getByRole('button',{name:'Install or enable '+missing}).click();expect(await page.evaluate(()=>window.__QA_NAVIGATED__)).toBe('/capabilities?tab=plugins');
      expect(await page.evaluate(()=>window.__QA_REQUESTS__.filter(x=>x.method!=='GET').length)).toBe(writesBefore);
     }else{
      // Host management navigation only; never call install/enable APIs.
      await page.route('**/plugins',route=>route.fulfill({contentType:'text/html',body:'<h1>Host plugins management navigation reached</h1>'}));
      await page.getByRole('button',{name:'Install or enable '+missing}).click();await expect(page).toHaveURL(base+'/plugins');
      await page.goto(base+'/qa/dashboard');await expect(page.getByRole('heading',{name:'Saved',exact:true})).toBeVisible();
     }
    }
    // Profile switches clear old records immediately, never reuse a previous view.
    if(adapter==='desktop'){
     await page.evaluate(()=>window.__QA_SDK__.host.state.profile.set('foreign'));
     await expect(page.getByRole('tab')).toHaveCount(0);
     await expect(page.getByRole('button',{name:/^Saved (conversation-bookmarks|delivery-shelf)$/})).toHaveCount(0);
     await page.evaluate(()=>window.__QA_SDK__.host.state.profile.set('default'));
     await expect(page.getByRole('button',{name:/^Saved (conversation-bookmarks|delivery-shelf)$/})).toBeVisible();
     await page.evaluate(()=>{for(const id of ['conversation-bookmarks','delivery-shelf'])window.__QA_UNLOAD__(id);});
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(0);await expect(page.getByRole('heading',{name:'Saved',exact:true})).toHaveCount(0);
    }else{
     await page.evaluate(()=>window.__QA_PROFILE__('foreign'));
     await expect(page.getByRole('button',{name:/^Saved (conversation-bookmarks|delivery-shelf)$/})).toHaveCount(0);
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(0);
     await page.evaluate(()=>window.__QA_PROFILE__('default'));
     await expect(page.getByRole('link',{name:'Saved',exact:true})).toHaveCount(1);
     await expect(page.getByRole('button',{name:/^Saved (conversation-bookmarks|delivery-shelf)$/})).toBeVisible();
    }
    expect(errors).toEqual([]);
    rows.push({scenario,adapter,order,passed:true});console.log('PASS',scenario,adapter,order);
   }catch(error){console.error({scenario,adapter,order,errors,body:await page.locator('body').innerText(),logs});throw error;}
   finally{await context.close();}
  }
  await stop();
 }
 expect(rows).toHaveLength(34);
 for(const [file,hash] of Object.entries(pins))expect(createHash('sha256').update(await readFile(file)).digest('hex')).toBe(hash);
 await writeFile(join(proof,'results.json'),JSON.stringify({hostSource:source,hostCommit:execFileSync('git',['-C',source,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),browser:browser.version(),completedAt:new Date().toISOString(),pins,cases:rows,scope:'Native loaders, Dashboard slots, Desktop registry and lifecycle; real authenticated backend. SDK host state/IPC boundaries are doubles; not full Electron or secondary-profile transport QA.'},null,2));
 console.log(`Saved matrix: ${rows.length}/34 passed. Proof: ${proof}`);
}finally{await browser?.close();await stop();await rm(scratch,{recursive:true,force:true});}
