/* Native loaders, real React, native authenticated Python API, fictional bank.
 * SDK host state/IPC/UI-kit boundaries are doubles; this is NOT Electron QA.
 */
import {build} from 'esbuild';
import {mkdtemp, readFile, copyFile, rm, mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {chromium,expect} from '@playwright/test';

const root=resolve('.');
const source=process.env.HERMES_SOURCE||join(process.env.HOME,'.hermes/hermes-agent');
const scratch=await mkdtemp(join(process.env.TMPDIR||tmpdir(),'q-'));
const port=await new Promise(r=>{const s=createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
const common=`import React from 'react';import {createRoot} from 'react-dom/client';
window.__QA_REACT__=React;
const root=createRoot(document.getElementById('root'));
window.__QA_REQUESTS__=[];
async function fetchJSON(path,opts={}) {
 window.__QA_REQUESTS__.push({path,method:opts.method||'GET'});
 const response=await fetch(path,{...opts,headers:{...opts.headers,'X-Hermes-Session-Token':'fictional-test-session'}});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request refused');return data;
}
window.__QA_FETCH__=fetchJSON;
`;
const apiStub=`export const HERMES_BASE_PATH='';export const fetchJSON=(...a)=>window.__QA_FETCH__(...a);export const authedFetch=fetchJSON;export const buildWsUrl=()=>'';export const buildWsAuthParam=()=>'';export const api={getPlugins:async(profile)=>(await fetchJSON('/api/dashboard/plugins?profile='+profile))};`;
const uiStub=`export const Badge=()=>null,Button=()=>null,Checkbox=()=>null,ConfirmDialog=()=>null,Dialog=()=>null,DialogClose=()=>null,DialogContent=()=>null,DialogDescription=()=>null,DialogFooter=()=>null,DialogHeader=()=>null,DialogTitle=()=>null,Toast=()=>null,useConfirmDelete=()=>null,useToast=()=>null,Select=()=>null,SelectOption=()=>null,Card=()=>null,CardHeader=()=>null,CardTitle=()=>null,CardContent=()=>null,Input=()=>null,Label=()=>null,Separator=()=>null,Tabs=()=>null,TabsList=()=>null,TabsTrigger=()=>null;`;
const dashEntry=common+`
import {exposePluginSDK,getPluginComponent,onPluginRegistered,selectPluginProfile} from '${source}/web/src/plugins/registry.ts';
import {usePlugins} from '${source}/web/src/plugins/usePlugins.ts';
exposePluginSDK();
function App(){usePlugins('default');const Component=React.useSyncExternalStore(onPluginRegistered,()=>getPluginComponent('delivery-shelf')||null);return Component?React.createElement(Component):React.createElement('p',null,'Native Dashboard loader…');}
root.render(React.createElement(App));
window.__QA_UNMOUNT__=()=>root.unmount();
`;
const sdkStub=`import React from 'react';import {atom} from 'nanostores';
export const host={state:{profile:atom('default'),connectionId:atom('fixture')}};
export const useValue=a=>React.useSyncExternalStore(a.subscribe,a.get,a.get);
export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav';
window.__QA_SDK__={host,useValue,ROUTES_AREA,SIDEBAR_NAV_AREA};
export function installPluginSdk(){}
const blob=s=>URL.createObjectURL(new Blob([s],{type:'text/javascript'}));
export const sdkImportMap=()=>({
 'react':blob('export default window.__QA_REACT__;export const {useState,useEffect,useRef,useId,useMemo}=window.__QA_REACT__;'),
 '@hermes/plugin-sdk':blob('export const {host,useValue,ROUTES_AREA,SIDEBAR_NAV_AREA}=window.__QA_SDK__;')
});`;
const contextStub=`export function createPluginContext(id,track){return {registerMany(items){for(const c of items){window.__QA_CONTRIBUTIONS__.push(c);track(()=>{window.__QA_CONTRIBUTIONS__=window.__QA_CONTRIBUTIONS__.filter(x=>x!==c);});}},onDispose:track,os:{writeClipboard:async(text)=>{window.__QA_CLIPBOARD__=text;return true;}},rest:(path,opts={})=>window.__QA_FETCH__('/api/plugins/'+id+path,{method:opts.method||'GET',headers:opts.body?{'Content-Type':'application/json'}:undefined,body:opts.body?JSON.stringify(opts.body):undefined})};}`;
const recordsStub=`import {atom} from 'nanostores';export const $pluginRecords=atom({});export function publishPlugin(r){$pluginRecords.set({...$pluginRecords.get(),[r.id]:r});}export function dropPlugin(){}export function pluginActive(id,fallback){return fallback;}`;
const desktopEntry=common+`
import {loadRuntimePlugin,unloadRuntimePlugin} from '${source}/apps/desktop/src/contrib/runtime-loader.ts';
window.__QA_CONTRIBUTIONS__=[];
const code=await (await fetch('/qa-assets/plugin.js')).text();
const id=await loadRuntimePlugin(code,'delivery-shelf',{file:'fixture/plugin.js',defaultEnabled:true});
if(id!=='delivery-shelf')throw new Error('Native Desktop loader rejected plugin');
const page=window.__QA_CONTRIBUTIONS__.find(c=>c.area==='routes');
if(!page||!window.__QA_CONTRIBUTIONS__.some(c=>c.area==='sidebar.nav'))throw new Error('Missing native contributions');
root.render(React.createElement(page.render));
window.__QA_UNMOUNT__=()=>{unloadRuntimePlugin('delivery-shelf');root.unmount();};
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
 b.onResolve({filter:/^\.\/(events|plugin|plugins-store)$/},args=>{
  if(args.importer.endsWith('/contrib/runtime-loader.ts'))return {path:args.path.slice(2),namespace:'qa'};
 });
 b.onLoad({filter:/.*/,namespace:'qa'},args=>({contents:({api:apiStub,profile:'export const dashboardServingProfile=()=>"default";',utils:'export const cn=(...a)=>a.join(" "),timeAgo=()=>"",isoTimeAgo=()=>"";',i18n:'export const useI18n=()=>({t:{}});',ui:uiStub,sdk:sdkStub,fs:'export const isReadFileErrorResult=()=>false;',notifications:'export const notifyError=(e)=>{throw e;};',events:'export const trackGatewayEventDisposers=(track,fn)=>fn();',plugin:contextStub,'plugins-store':recordsStub})[args.path],loader:'js',resolveDir:root}));
}};
let server,browser;
try{
 for(const [name,contents] of [['dashboard',dashEntry],['desktop',desktopEntry]])await build({stdin:{contents,resolveDir:root,loader:'jsx'},outfile:join(scratch,name+'.js'),bundle:true,format:'esm',target:'es2022',nodePaths:[join(root,'node_modules')],define:{'import.meta.env.DEV':'false','process.env.NODE_ENV':'"production"'},plugins:[stubPlugin]});
 await copyFile('desktop/plugin.js',join(scratch,'plugin.js'));
 server=spawn(process.env.PYTHON||'python',['tests/browser_server.py',String(port),scratch],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',HERMES_SOURCE:source},stdio:['ignore','pipe','pipe']});
 let logs='';server.stderr.on('data',b=>logs+=b);
 const base=`http://127.0.0.1:${port}`;
 for(let n=0;n<100;n++){try{if((await fetch(base+'/qa/dashboard')).ok)break;}catch{}if(server.exitCode!==null)throw new Error(logs);await new Promise(r=>setTimeout(r,100));if(n===99)throw new Error('Server failed: '+logs);}
 browser=await chromium.launch({headless:true});
 const auth={'X-Hermes-Session-Token':'fictional-test-session','Content-Type':'application/json'};
 const api=async(path,opts={})=>{const r=await fetch(base+'/api/plugins/delivery-shelf'+path,{...opts,headers:auth});if(!r.ok)throw new Error(await r.text());return r.json();};
 const screenshots=join(root,'docs/assets');await mkdir(screenshots,{recursive:true});
 for(const adapter of ['dashboard','desktop']){
   const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/qa/'+adapter);try{await expect(page.getByRole('heading',{name:'Delivery Shelf',exact:true})).toBeVisible();}catch(e){console.error('QA diagnostics',errors,await page.locator('body').innerText(),await page.evaluate(()=>window.__QA_REQUESTS__),logs);throw e;}
   await expect(page.getByRole('heading',{name:'Make room for finished work'})).toBeVisible();
   await page.getByRole('button',{name:'Add delivery',exact:false}).first().focus();await page.keyboard.press('Enter');
   const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();await expect(dialog.getByLabel('Title',{exact:true})).toBeFocused();
   await dialog.getByLabel('Title',{exact:true}).fill('Field guide — handoff edition');
   await dialog.getByLabel('Description',{exact:true}).fill('The final guide, reviewed and ready for the next person.');
   await dialog.getByLabel('Project',{exact:true}).fill('North studio');
   await dialog.getByLabel('Tags',{exact:false}).fill('handoff, ready');
   await dialog.getByLabel('Session reference',{exact:false}).fill('fictional-session-01');
   await dialog.getByLabel('Relative file path').fill('example.md');
   await dialog.getByRole('button',{name:'Add delivery',exact:true}).click();await expect(dialog).not.toBeVisible();
   await expect(page.getByRole('button',{name:'Field guide — handoff edition',exact:true})).toBeVisible();
   let list=await api('/entries');expect(list.total).toBe(1);expect(list.items[0].session_id).toBe('fictional-session-01');
   await page.getByRole('button',{name:'Field guide — handoff edition',exact:true}).click();
   await dialog.getByRole('button',{name:'Preview text'}).click();await expect(dialog.locator('pre')).toContainText('<script>');expect(await page.evaluate(()=>window.evil)).toBeUndefined();
   const downloading=page.waitForEvent('download');await dialog.getByRole('button',{name:'Download file'}).click();const download=await downloading;expect(download.suggestedFilename()).toBe('example.md');
   if(adapter==='desktop'){await dialog.getByRole('button',{name:'Copy session ID'}).click();expect(await page.evaluate(()=>window.__QA_CLIPBOARD__)).toBe('fictional-session-01');}
   await dialog.getByRole('button',{name:'Edit metadata'}).click();await dialog.getByLabel('Title',{exact:true}).fill('Field guide — final edition');await dialog.getByRole('button',{name:'Save changes'}).click();await expect(dialog).not.toBeVisible();
   await page.getByRole('searchbox',{name:'Search'}).fill('unmatched');await expect(page.getByRole('heading',{name:'No matching deliveries'})).toBeVisible();await page.getByRole('button',{name:'Clear filters'}).click();
   await expect(page.getByRole('button',{name:'Field guide — final edition',exact:true})).toBeVisible();
   await api('/entries',{method:'POST',body:JSON.stringify({title:'A quieter onboarding',description:'Interface notes and the approved interaction sequence.',kind:'report',project:'North studio',tags:['design','reviewed']})});
   await api('/entries',{method:'POST',body:JSON.stringify({title:'Release checklist',description:'Everything needed to hand over the first release.',kind:'document',project:'Workshop',tags:['release']})});
   await page.getByRole('button',{name:'Refresh',exact:true}).click();await expect(page.locator('.ds-card')).toHaveCount(3);
   await page.screenshot({path:join(screenshots,adapter+'.png'),fullPage:true});
   for(const width of [360,768,1440]){
     await page.setViewportSize({width,height:1000});
     expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
     if(width===360)expect(await page.locator('.ds button,.ds input,.ds select').evaluateAll(nodes=>nodes.filter(n=>n.getBoundingClientRect().height>0).every(n=>n.getBoundingClientRect().height>=44))).toBe(true);
     if(adapter==='dashboard'&&width===360)await page.screenshot({path:join(screenshots,'mobile.png'),fullPage:true});
     await page.getByRole('button',{name:'Field guide — final edition',exact:true}).click();await expect(dialog).toBeVisible();
     expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
     await page.keyboard.press('Escape');await expect(dialog).not.toBeVisible();
   }
   async function contrast(){return page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=1;const ctx=c.getContext('2d');const rgb=color=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=color;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data].slice(0,3);};const lum=rgb=>rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);const a=lum(rgb(getComputedStyle(document.querySelector('.ds-card .ds-muted')).color)),b=lum(rgb(getComputedStyle(document.querySelector('.ds-card')).backgroundColor));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);});}
   const lightContrast=await contrast();expect(lightContrast).toBeGreaterThanOrEqual(4.5);
   const light=await page.locator('.ds-shelf').evaluate(el=>getComputedStyle(el).backgroundColor);
   await page.evaluate(()=>{document.body.style.setProperty('--ui-bg-editor','#162332');document.body.style.setProperty('--ui-text-primary','#e3edf3');document.body.style.setProperty('--ui-stroke-secondary','#435567');});
   const dark=await page.locator('.ds-shelf').evaluate(el=>getComputedStyle(el).backgroundColor);expect(dark).not.toBe(light);
   const darkContrast=await contrast();expect(darkContrast).toBeGreaterThanOrEqual(4.5);console.log(`${adapter}: muted/card contrast light ${lightContrast.toFixed(2)}:1, dark ${darkContrast.toFixed(2)}:1; mobile controls >=44px.`);
   await page.evaluate(()=>{document.body.style.setProperty('--ui-bg-editor','#edf2f7');document.body.style.setProperty('--ui-text-primary','#23384c');document.body.style.setProperty('--ui-stroke-secondary','#b7c7d3');});expect(await page.locator('.ds-shelf').evaluate(el=>getComputedStyle(el).backgroundColor)).toBe(light);
   // Genuine error state, then retry, against the real view.
   await page.route('**/api/plugins/delivery-shelf/entries?**',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"Fictional outage"}'}));
   await page.getByRole('button',{name:'Refresh',exact:true}).click();await expect(page.getByRole('heading',{name:'Could not open your shelf'})).toBeVisible();await page.unroute('**/api/plugins/delivery-shelf/entries?**');await page.getByRole('button',{name:'Try again'}).click();await expect(page.locator('.ds-card')).toHaveCount(3);
   await page.getByRole('button',{name:'Field guide — final edition',exact:true}).click();await dialog.getByRole('button',{name:'Remove from shelf'}).click();await dialog.getByRole('button',{name:'Keep delivery'}).click();await expect(page.locator('.ds-card')).toHaveCount(3);
   await page.getByRole('button',{name:'Field guide — final edition',exact:true}).click();await dialog.getByRole('button',{name:'Remove from shelf'}).click();await dialog.getByRole('button',{name:'Remove metadata'}).click();await expect(page.locator('.ds-card')).toHaveCount(2);
   // Teardown during an in-flight mutation must not dispatch a verification
   // request through a newly rebound Desktop ctx.rest (or retired Dashboard).
   await page.getByRole('button',{name:'Add delivery',exact:false}).first().click();await dialog.getByLabel('Title',{exact:true}).fill('In-flight fictional mutation');
   let release;const gate=new Promise(r=>release=r);let started;const arrived=new Promise(r=>started=r);
   await page.route('**/api/plugins/delivery-shelf/entries?**',async route=>{if(route.request().method()==='POST'){started();await gate;}await route.continue();});
   await dialog.getByRole('button',{name:'Add delivery',exact:true}).click();await arrived;
   const before=await page.evaluate(()=>window.__QA_REQUESTS__.length);await page.evaluate(()=>window.__QA_UNMOUNT__());release();await page.waitForTimeout(400);expect(await page.evaluate(()=>window.__QA_REQUESTS__.length)).toBe(before);
   expect(errors).toEqual([]);
   await context.close();
   list=await api('/entries');for(const item of list.items)await api(`/entries/${item.id}?revision=${item.revision}`,{method:'DELETE'});
   console.log(`${adapter}: native loader + CRUD/readback, safe preview/download, session reference, filters, 360/768/1440, light→dark→light, dialogs/keyboard, errors/retry, delete confirmation, disposal fence PASS`);
 }
 console.log('Screenshots: docs/assets/dashboard.png, desktop.png, mobile.png (fictional data; native loader DOM tests, NOT Electron).');
}finally{
 await browser?.close();
 if(server&&server.exitCode===null){server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));}
 await rm(scratch,{recursive:true,force:true});
}
