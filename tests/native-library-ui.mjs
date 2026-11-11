// Native host controls are real; only transport is a fixture boundary.
import {test,after,afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,symlink,rm,readFile,mkdir} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {uiExports} from './native-components.mjs';
const root=resolve('.'),source=process.env.HERMES_UI_SOURCE||resolve('../shelf-native-host');
const requireHost=createRequire(join(source,'package.json'));
const {JSDOM}=requireHost('jsdom'),{build}=requireHost('esbuild');
const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Element','Node','MutationObserver','CustomEvent','Event','KeyboardEvent','MouseEvent','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
globalThis.getComputedStyle=dom.window.getComputedStyle.bind(dom.window);
for(const key of Object.getOwnPropertyNames(dom.window).filter(key=>/^(?:HTML|SVG|Node|Document|Event|FocusEvent|MutationObserver)/.test(key)))if(!(key in globalThis))Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
globalThis.requestAnimationFrame=dom.window.requestAnimationFrame.bind(dom.window);globalThis.cancelAnimationFrame=dom.window.cancelAnimationFrame.bind(dom.window);
window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}});
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};globalThis.PointerEvent=dom.window.MouseEvent;
HTMLElement.prototype.scrollIntoView=function(){};HTMLElement.prototype.hasPointerCapture=()=>false;HTMLElement.prototype.setPointerCapture=function(){};HTMLElement.prototype.releasePointerCapture=function(){};
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const scratch=await mkdtemp(join(process.env.TMPDIR,'native-library-'));await symlink(join(source,'node_modules'),join(scratch,'node_modules'),'dir');
const components=Object.entries({...uiExports,'components/ui/segmented-control':['SegmentedControl'],'components/ui/codicon':['Codicon']}).map(([file,names])=>`export {${names.join(',')}} from '${source}/apps/desktop/src/${file}';`).join('\n');
await build({stdin:{contents:`export {NativeShelf} from '${root}/ui/NativeShelf.jsx'; export {FileVisual} from '${root}/ui/NativeLibrary.jsx';`,resolveDir:root,loader:'jsx'},outfile:join(scratch,'library.mjs'),bundle:true,format:'esm',platform:'node',target:'es2022',packages:'external',jsx:'automatic',loader:{'.css':'text'},alias:{'@saved/presentation':join(root,'ui/presentation.desktop.jsx'),'@':join(source,'apps/desktop/src')},plugins:[{name:'real-sdk-controls',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'native-sdk'}));b.onLoad({filter:/.*/,namespace:'native-sdk'},()=>({contents:components,resolveDir:source,loader:'ts'}));}}]});
const React=requireHost('react'),{render,fireEvent,screen,waitFor,cleanup,act,within}=requireHost('@testing-library/react');
const {NativeShelf,FileVisual}=await import(pathToFileURL(join(scratch,'library.mjs')).href);
const calls=[],downloads=[];URL.createObjectURL=blob=>{downloads.push({media_type:blob.type,size:blob.size});return 'blob:preview';};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){downloads.at(-1).name=this.download;};
const files=[{id:'pdf',name:'plan.pdf',file:{root:'workspace',path:'plan.pdf'},source:{message_id:1,digest:'digest',artifact_id:'pdf'}},{id:'image',name:'cover.png',content_mode:'image',file:{root:'workspace',path:'cover.png'},source:{message_id:1,digest:'digest',artifact_id:'image'}}];
let entry={id:'delivery',title:'Launch materials',description:'Plan and artwork, delivered together.',tags:[' exact ',' exact '],kind:'report',project:'Website',revision:1,session_id:'chat-A',file:files[0].file,files:files.map(f=>f.file),current_version:'v1',versions:[{id:'v1',number:1,files:[{id:'managed-pdf',name:'plan.pdf',size:4,media_type:'application/pdf'},{id:'managed-image',name:'cover.png',size:4,media_type:'image/png'}]}]};
let generationResolve;
const api=async(url,options={})=>{calls.push({url,options});const u=new URL(url,'http://localhost');
 if(u.pathname==='/generation/settings')return {previous_exchanges:10};
 if(u.pathname==='/settings')return {enabled_views:['together','library','gallery'],default_view:'together',timezone:'auto',hour_cycle:'auto',context_messages:10};
 if(u.pathname==='/entries')return {items:[entry],total:61,has_more:Number(u.searchParams.get('offset'))<60};
 if(u.pathname==='/entries/delivery')return entry;
 if(u.pathname==='/sources/sessions')return {items:u.searchParams.get('q')?[{id:'chat-B',title:'Campaign work'}]:[{id:'chat-A',title:'Launch work'},{id:'chat-B',title:'Campaign work'}],has_more:true};
 if(u.pathname.endsWith('/artifacts'))return {items:Number(u.searchParams.get('offset'))?[{...files[0],id:'third',name:'notes.txt',file:{root:'workspace',path:'notes.txt'}}]:files,has_more:!Number(u.searchParams.get('offset'))};
 if(u.pathname==='/sources/thumbnail')return {base64:'dGVzdA==',media_type:'image/png'};
 if(u.pathname==='/entries/delivery/thumbnail')return {base64:'dGVzdA==',media_type:'image/png'};
 if(u.pathname.includes('/versions/v1/files/'))return {base64:'dGVzdA==',name:u.pathname.endsWith('managed-image')?'cover.png':'plan.pdf',media_type:u.pathname.endsWith('managed-image')?'image/png':'application/pdf'};
 if(u.pathname==='/sources/register-many'){entry={...entry,...options.body};return entry;}
 if(u.pathname==='/generation/draft')return new Promise(resolve=>{generationResolve=resolve;});
 if(u.pathname==='/entries/delivery/versions/v0/files/old-image')return {name:'earlier.png',base64:'dGVzdA==',media_type:'image/png'};
 if(u.pathname==='/entries/delivery/versions'){entry={...entry,revision:2,current_version:'v2',versions:[...entry.versions,{id:'v2',number:3,files:entry.versions[0].files}]};return entry;}
 if(u.pathname==='/entries/delivery/file')return {text:'<script>not executable</script>',truncated:true};
 throw Error('Unexpected endpoint '+url);
};
const click=async el=>act(async()=>fireEvent.click(el));
const type=async(el,value)=>act(async()=>fireEvent.change(el,{target:{value}}));
const choose=async(name,value)=>{const control=await screen.findByRole('combobox',{name});await act(async()=>fireEvent.pointerDown(control,{button:0,ctrlKey:false,pointerType:'mouse'}));await click(await screen.findByRole('option',{name:value,exact:true}));};
after(async()=>{cleanup();dom.window.close();await rm(scratch,{recursive:true,force:true});});
afterEach(()=>cleanup());

test('Library selects deliveries with empty row checkboxes, not a duplicate selection list',async()=>{
 render(React.createElement(NativeShelf,{api,ownerKey:'row-selection',modal:false}));
 await click(await screen.findByRole('button',{name:'Library',exact:true}));
 const list=await screen.findByRole('region',{name:'Saved file list'});
 assert.ok(!screen.queryByRole('region',{name:'Select deliveries'}),'duplicate selection list must be absent');
 const boxes=within(list).getAllByRole('checkbox');
 assert.equal(boxes.length,2);assert.ok(boxes.every(box=>box.getAttribute('aria-checked')==='false'));
 await click(within(list).getByRole('button',{name:'Inspect cover.png'}));
 assert.ok(boxes.every(box=>box.getAttribute('aria-checked')==='false'),'previewing never selects');
 await click(boxes[0]);
 assert.ok(within(list).getAllByRole('checkbox').every(box=>box.getAttribute('aria-checked')==='true'),'companion rows represent the same delivery');
 assert.ok(within(list).getAllByRole('checkbox').every(box=>box.getAttribute('data-state')==='checked'),'native checked painting must not be overwritten by tooltip state');
 assert.equal(within(list).getByRole('button',{name:'Inspect cover.png'}).getAttribute('aria-pressed'),'true','selecting never changes preview');
 assert.ok(screen.getByText('1 delivery selected'));
 await click(within(list).getAllByRole('checkbox')[1]);
 assert.ok(within(list).getAllByRole('checkbox').every(box=>box.getAttribute('aria-checked')==='false'));
 assert.equal(screen.getByRole('button',{name:'Archive selected'}).disabled,true);
});

test('Gallery selects on the actual file cards without a duplicate selection list',async()=>{
 render(React.createElement(NativeShelf,{api,ownerKey:'card-selection',modal:false}));
 await click(await screen.findByRole('button',{name:'Gallery',exact:true}));
 const gallery=await screen.findByRole('region',{name:'File gallery'});
 assert.ok(!screen.queryByRole('region',{name:'Select deliveries'}),'duplicate selection list must be absent');
 const boxes=within(gallery).getAllByRole('checkbox');
 assert.equal(boxes.length,2);assert.ok(boxes.every(box=>box.getAttribute('aria-checked')==='false'));
 assert.ok(boxes.every(box=>box.closest('article')));
 await click(boxes[0]);
 assert.ok(screen.getByText('1 delivery selected'));
 assert.ok(within(gallery).getAllByRole('checkbox').every(box=>box.getAttribute('data-state')==='checked'),'gallery checkmarks must retain native checked painting');
 assert.equal(screen.queryByRole('region',{name:'Delivery details'}),null);
 await click(screen.getByRole('button',{name:'Clear delivery selection'}));
 assert.ok(within(gallery).getAllByRole('checkbox').every(box=>box.getAttribute('aria-checked')==='false'));
});

test('delivery permission lives in inspector and details, only revokes existing consent with readback',async()=>{
 let always=true;const requests=[];
 const permissionApi=async(url,options={})=>{if(url==='/entries/delivery/version-permission'){requests.push(options.method||'GET');if(options.method==='DELETE')always=false;return {always,paused:false};}return api(url,options);};
 render(React.createElement(NativeShelf,{api:permissionApi,ownerKey:'permission',modal:false}));
 await click(await screen.findByRole('button',{name:'Library',exact:true}));
 const inspector=await screen.findByRole('complementary',{name:'File preview'});
 await within(inspector).findByText('New versions: Always for this delivery');
 await click(within(inspector).getByRole('button',{name:'Ask before next version'}));
 await within(inspector).findByText('New versions: Ask first');
 assert.deepEqual(requests,['GET','DELETE','GET']);
 assert.equal(screen.queryByRole('button',{name:'Ask before next version'}),null);
 assert.equal(screen.queryByRole('switch',{name:/always/i}),null);
 await click(within(inspector).getByRole('button',{name:'Open file & history'}));
 const detail=await screen.findByRole('region',{name:'Delivery details'});
 await within(detail).findByText('New versions: Ask first');
});

test('archived delivery permission is visibly paused and remains revocable',async()=>{
 const pausedApi=async(url,options)=>url==='/entries/delivery/version-permission'?{always:true,paused:true}:api(url,options);
 render(React.createElement(NativeShelf,{api:pausedApi,ownerKey:'paused-permission',modal:false}));
 await click(await screen.findByRole('button',{name:'Open delivery Launch materials'}));
 await screen.findByText('New versions: Always for this delivery · Paused');
 assert.ok(screen.getByRole('button',{name:'Ask before next version'}));
});

test('bulk selection spans matching filters, resets on filter change, archives once and offers Undo',async()=>{
 const requests=[];let state='active';
 const bulkApi=async(url,options={})=>{requests.push({url,options});const u=new URL(url,'http://localhost');
  if(u.pathname==='/settings')return {enabled_views:['together','library','gallery'],default_view:'together',timezone:'auto',hour_cycle:'auto',context_messages:10};
  if(u.pathname==='/entries/bulk-action'){state=options.body.action==='archive'?'archived':'active';return {items:[{...entry,state}],affected:1};}
  if(u.pathname==='/entries')return {items:state==='active'?[entry]:[],total:state==='active'?61:0};
  return api(url,options);
 };
 render(React.createElement(NativeShelf,{api:bulkApi,ownerKey:'bulk',modal:false}));
 await screen.findByRole('region',{name:'Launch materials'});
 await type(screen.getByRole('textbox',{name:'Search deliveries'}),' launch ');
 await screen.findByRole('region',{name:'Launch materials'});
 await click(screen.getByRole('checkbox',{name:'Select all 61 matching deliveries'}));
 assert.ok(screen.getByText('61 deliveries selected · all matching filters'));
 await click(screen.getByRole('button',{name:'Next deliveries'}));
 await waitFor(()=>assert.ok(requests.some(c=>c.url.includes('offset=30'))));
 await click(screen.getByRole('button',{name:'Archive selected'}));
 await screen.findByRole('button',{name:'Undo archive'});
 assert.deepEqual(requests.find(c=>c.url==='/entries/bulk-action').options.body,{action:'archive',filter:{q:' launch ',kind:'',project:'',state:'active'}});
 assert.equal(screen.queryByRole('dialog'),null,'no per-entry confirmations');
 await click(screen.getByRole('button',{name:'Undo archive'}));
 await waitFor(()=>assert.equal(requests.filter(c=>c.url==='/entries/bulk-action').length,2));
 assert.deepEqual(requests.filter(c=>c.url==='/entries/bulk-action')[1].options.body,{action:'restore',ids:['delivery']});
 await screen.findByRole('region',{name:'Launch materials'});
 await click(screen.getByRole('checkbox',{name:'Select delivery Launch materials'}));
 assert.ok(screen.getByText('1 delivery selected'));
 await type(screen.getByRole('textbox',{name:'Project filter'}),'Website');
 await waitFor(()=>assert.ok(screen.getByText('0 deliveries selected')));
});

test('empty Trash requires one explicit whole-trash confirmation; Pending deletion shows a timezone deadline and bulk Restore',async()=>{
 const requests=[];let current={...entry,state:'trash',created:0,delete_after:1767225600};
 const lifecycleApi=async(url,options={})=>{requests.push({url,options});const u=new URL(url,'http://localhost');
  if(u.pathname==='/settings')return {enabled_views:['together','library','gallery'],default_view:'together',timezone:'America/New_York',hour_cycle:'24',date_format:'iso',context_messages:10};
  if(u.pathname==='/entries')return {items:(u.searchParams.get('state')||'active')===current.state?[current]:[],total:1};
  if(u.pathname==='/entries/bulk-action'){current={...current,state:options.body.action==='empty_trash'?'pending_delete':'active'};return {items:[current],affected:1};}
  return api(url,options);
 };
 render(React.createElement(NativeShelf,{api:lifecycleApi,ownerKey:'trash',modal:false}));
 await choose('Delivery state','Trash');await screen.findByRole('region',{name:'Launch materials'});
 await click(screen.getByRole('button',{name:'Empty Trash',exact:true}));
 const dialog=screen.getByRole('dialog',{name:'Empty Trash?'});assert.match(dialog.textContent,/60 minutes/);assert.match(dialog.textContent,/Original working files are never deleted/);
 assert.equal(requests.filter(c=>c.url==='/entries/bulk-action').length,0);
 await click(within(dialog).getByRole('button',{name:'Cancel'}));assert.equal(screen.queryByRole('dialog'),null);
 await click(screen.getByRole('button',{name:'Empty Trash',exact:true}));
 await click(screen.getByRole('button',{name:'Empty Trash · start 60-minute recovery'}));
 await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));
 assert.deepEqual(requests.find(c=>c.url==='/entries/bulk-action').options.body,{action:'empty_trash',filter:{state:'trash'}});
 await choose('Delivery state','Pending deletion');
 await screen.findByText(/2025-12-31.*19:00.*America\/New_York/);
 await click(screen.getByRole('checkbox',{name:'Select all 1 matching deliveries'}));
 await click(screen.getByRole('button',{name:'Restore selected'}));
 await waitFor(()=>assert.equal(requests.filter(c=>c.url==='/entries/bulk-action').length,2));
 assert.deepEqual(requests.filter(c=>c.url==='/entries/bulk-action')[1].options.body,{action:'restore',filter:{q:'',kind:'',project:'',state:'pending_delete'}});
});

test('enabled views honor the configured default without flashing disabled modes',async()=>{
 const viewsApi=async(url,options)=>new URL(url,'http://localhost').pathname==='/settings'?{enabled_views:['library'],default_view:'library',timezone:'auto',hour_cycle:'auto',context_messages:20}:api(url,options);
 render(React.createElement(NativeShelf,{api:viewsApi,ownerKey:'enabled',modal:false}));
 await screen.findByRole('complementary',{name:'File preview'});
 assert.equal(screen.queryByRole('button',{name:'Together',exact:true}),null);
 assert.equal(screen.queryByRole('button',{name:'Gallery',exact:true}),null);
 assert.equal(screen.getByRole('button',{name:'Library',exact:true}).getAttribute('aria-pressed'),'true');
});

test('version-specific provenance opens only the recorded conversation, copies exact source/message, and labels legacy gaps',async()=>{
 const original=entry,opened=[],copied=[],warnings=[],originalError=console.error;
 console.error=(...args)=>{warnings.push(args.join(' '));originalError(...args);};
 entry={...entry,session_id:'latest-not-original',file:{root:'workspace',path:'newer.pdf'},versions:[{id:'v1',number:1,created:1767225600,provenance:{known:true,profile:'original-bot',session_id:'origin-chat',message_id:17},files:[{id:'managed-pdf',name:'plan.pdf',provenance:{known:true,original_root:'workspace',original_path:'/original/plan.pdf',profile:'original-bot',session_id:'origin-chat',message_id:17}}]},{id:'legacy',number:2,files:[{id:'legacy-file',name:'old.pdf',provenance:{known:false}}]}]};
 entry.versions.push({id:'v3',number:3,created:1767229200,files:[{id:'newer-file',name:'newer.pdf',provenance:{known:true,original_path:'/newer/plan.pdf',profile:'other-bot',session_id:'other-chat',message_id:29}}]});
 const provenanceApi=Object.assign((url,options)=>url==='/settings'?Promise.resolve({enabled_views:['together','library','gallery'],default_view:'together',timezone:'America/New_York',hour_cycle:'24',date_format:'iso'}):api(url,options),{openSession:(...args)=>opened.push(args),copyText:async text=>copied.push(text)});
 try{
  render(React.createElement(NativeShelf,{api:provenanceApi,ownerKey:'origins',modal:false}));
  await click(await screen.findByRole('button',{name:'Open delivery Launch materials'}));
  const preview=screen.getByRole('region',{name:'Delivery preview'});
  await within(preview).findByText('/original/plan.pdf');
  await click(within(preview).getByRole('button',{name:'Open original conversation'}));
  assert.deepEqual(opened,[['origin-chat','original-bot']]);
  await click(within(preview).getByRole('button',{name:'Copy original source path'}));
  await click(within(preview).getByRole('button',{name:'Copy original message ID'}));
  assert.deepEqual(copied,['/original/plan.pdf','17']);
  assert.match(preview.textContent,/exact-message navigation is unavailable/i);
  assert.match(preview.textContent,/2025-12-31.*19:00.*America\/New_York/);
  await choose('Preview version','Version 3');
  await within(preview).findByText('/newer/plan.pdf');
  assert.match(preview.textContent,/2025-12-31.*20:00.*America\/New_York/);
  await click(within(preview).getByRole('button',{name:'Open original conversation'}));
  assert.deepEqual(opened,[['origin-chat','original-bot'],['other-chat','other-bot']]);
  await choose('Preview version','Version 2');
  assert.match(preview.textContent,/Original source unavailable/);assert.match(preview.textContent,/Original conversation unavailable/);assert.match(preview.textContent,/Original message unavailable/);
  assert.equal(within(preview).queryByRole('button',{name:'Open original conversation'}),null);
  assert.ok(!preview.textContent.includes('latest-not-original'));
  assert.equal(warnings.filter(text=>text.includes('same key')).length,0,'version changes must not reuse sibling React keys');
 }finally{entry=original;console.error=originalError;}
});

test('Saved opens Together companion cards; Library has persistent inspector and Gallery remains optional',async()=>{
 render(React.createElement(NativeShelf,{api,ownerKey:'library',modal:false}));
 await screen.findByRole('region',{name:'Delivery catalog'});
 assert.equal(screen.queryByRole('tab',{name:'Add delivery'}),null);
 assert.equal(screen.getByRole('button',{name:'Together',exact:true}).getAttribute('aria-pressed'),'true');
 const group=await screen.findByRole('region',{name:'Launch materials'});
 assert.ok(within(group).getByText('plan.pdf'));assert.ok(within(group).getByText('cover.png'));
 await click(screen.getByRole('button',{name:'Library',exact:true}));
 const inspector=await screen.findByRole('complementary',{name:'File preview'});assert.ok(within(inspector).getByText('plan.pdf'));
 await click(screen.getByRole('button',{name:'Inspect cover.png'}));await within(inspector).findByRole('img',{name:'cover.png'});
 assert.ok(calls.some(c=>c.url==='/entries/delivery/thumbnail?version_id=v1&file_id=managed-image'));
 await click(screen.getByRole('button',{name:'Gallery',exact:true}));assert.ok(screen.getByRole('region',{name:'File gallery'}));
 await click(screen.getByRole('button',{name:'Preview cover.png'}));const preview=await screen.findByRole('region',{name:'Delivery preview'});await within(preview).findByRole('img',{name:'cover.png'});
 cleanup();
});

test('Together title and header share one native disclosure without swallowing delivery actions',async()=>{
 const start=calls.length;
 render(React.createElement(NativeShelf,{api,ownerKey:'disclosure',modal:false}));
 const group=await screen.findByRole('region',{name:'Launch materials'});
 const title=within(group).getByText('Launch materials'),toggle=title.closest('button');
 assert.ok(toggle,'the title must belong to the disclosure button');
 assert.equal(toggle.getAttribute('aria-expanded'),'true');
 assert.equal(toggle.querySelector('button,a,input'),null,'no nested interactive controls');
 const panel=document.getElementById(toggle.getAttribute('aria-controls'));assert.ok(panel);
 await click(title);assert.equal(toggle.getAttribute('aria-expanded'),'false');assert.equal(panel.hidden,true);
 assert.equal(within(group).queryByRole('button',{name:'Preview plan.pdf'}),null);
 assert.equal(calls.slice(start).filter(c=>c.url==='/entries/delivery').length,0,'collapse is not navigation');
 await click(toggle);assert.equal(toggle.getAttribute('aria-expanded'),'true');
 await click(within(group).getByRole('button',{name:'Open delivery Launch materials'}));
 await screen.findByRole('region',{name:'Delivery details'});
 assert.equal(calls.slice(start).filter(c=>c.url==='/entries/delivery').length,1);
});

test('document visuals request authenticated raster thumbnails for sources and exact saved editions',async()=>{
 for(const extension of ['pdf','docx','pptx','xlsx']){
  const source={...files[0],id:extension,name:'preview.'+extension};const requests=[];
  const thumbnail=async(url,options)=>{requests.push({url,options});return {base64:'dGVzdA==',media_type:'image/png'};};
  render(React.createElement(FileVisual,{api:thumbnail,source,sessionId:'chat-A'}));
  await screen.findByRole('img',{name:source.name});
  assert.deepEqual(requests,[{url:'/sources/thumbnail',options:{method:'POST',body:{session_id:'chat-A',file:source.file,source:source.source}}}]);cleanup();
  const record={entry:{id:'exact entry',revision:2},version:{id:'old/v1'},file:{id:'file '+extension,name:source.name}};
  render(React.createElement(FileVisual,{api:thumbnail,record}));await screen.findByRole('img',{name:source.name});
  assert.equal(requests[1].url,'/entries/exact%20entry/thumbnail?version_id=old%2Fv1&file_id=file+'+extension);cleanup();
 }
});

test('unavailable, malformed, unsafe and failed image previews remain honest file-type icons',async()=>{
 for(const response of [()=>Promise.reject(Error('No renderer available')),()=>Promise.resolve({base64:'%',media_type:'image/png'}),()=>Promise.resolve({base64:'dGVzdA==',media_type:'application/pdf'}),()=>Promise.resolve({base64:'dGVzdA==',media_type:'image/svg+xml'})]){
  render(React.createElement(FileVisual,{api:response,source:files[0],sessionId:'chat-A'}));
  await act(async()=>{});assert.ok(screen.getByLabelText('PDF file'));assert.equal(screen.queryByRole('img'),null);cleanup();
 }
 const unsupported=[];const thumbnail=async(url)=>{unsupported.push(url);return {base64:'dGVzdA==',media_type:'image/png'};};
 for(const extension of ['html','svg','zip','exe','txt','md','csv','tsv','json','yaml','yml','log']){
  render(React.createElement(FileVisual,{api:thumbnail,source:{...files[0],name:'unsafe.'+extension},sessionId:'chat-A'}));
  await act(async()=>{});assert.ok(screen.getByLabelText(extension.toUpperCase()+' file'));cleanup();
 }
 assert.deepEqual(unsupported,[]);
 render(React.createElement(FileVisual,{api:thumbnail,source:files[0],sessionId:'chat-A'}));
 const image=await screen.findByRole('img',{name:'plan.pdf'});await act(async()=>fireEvent.error(image));
 assert.ok(screen.getByLabelText('PDF file'));assert.equal(screen.queryByRole('img'),null);
});

test('Add is a shared modal with recents plus server search, scoped select-all, thumbnails, clear and retained drafts',async()=>{
 const retained=new Map();const props={api,ownerKey:'add-flow',sessionId:'chat-A',modal:false,retained};
 const mounted=render(React.createElement(NativeShelf,props));
 await click(await screen.findByRole('button',{name:'Add delivery',exact:true}));await screen.findByRole('dialog',{name:'Add delivery'});
 await screen.findByRole('button',{name:'plan.pdf',exact:true});
 assert.equal(screen.getByRole('combobox',{name:'Conversation'}).textContent,'Launch work');
 await act(async()=>fireEvent.pointerDown(screen.getByRole('combobox',{name:'Conversation'}),{button:0,ctrlKey:false,pointerType:'mouse'}));
 assert.ok(await screen.findByRole('option',{name:'Campaign work',exact:true}));
 await act(async()=>fireEvent.keyDown(screen.getByRole('listbox'),{key:'Escape'}));
 await type(screen.getByRole('textbox',{name:'Find conversation'}),'Campaign');
 await waitFor(()=>assert.ok(calls.some(c=>c.url.startsWith('/sources/sessions?')&&new URL(c.url,'http://localhost').searchParams.get('q')==='Campaign')));
 await screen.findByRole('button',{name:'Select all files on this page'});
 await screen.findByRole('img',{name:'cover.png'});
 const thumb=calls.find(c=>c.url==='/sources/thumbnail'&&c.options.body.file.path==='cover.png');assert.deepEqual(thumb.options.body,{session_id:'chat-A',file:files[1].file,source:files[1].source});
 await click(screen.getByRole('button',{name:'Select all files on this page'}));assert.equal(screen.getByRole('button',{name:'plan.pdf',exact:true}).getAttribute('aria-pressed'),'true');
 await click(screen.getByRole('button',{name:'Next files'}));await screen.findByRole('button',{name:'notes.txt',exact:true});
 assert.ok(screen.getByRole('button',{name:'Remove plan.pdf'}));await click(screen.getByRole('button',{name:'Select all files on this page'}));
 assert.ok(screen.getByText('3 files selected'));
 await click(screen.getByRole('button',{name:'Clear selection'}));assert.equal(screen.queryByRole('button',{name:'Remove plan.pdf'}),null);
 await click(screen.getByRole('button',{name:'notes.txt',exact:true}));
 await type(screen.getByRole('textbox',{name:'Title'}),'  Exact title  ');await type(screen.getByRole('textbox',{name:'Tags'}),' same ');await click(screen.getByRole('button',{name:'Add tag',exact:true}));await type(screen.getByRole('textbox',{name:'Tags'}),' same ');
 await click(screen.getByRole('button',{name:'Close',exact:true}));assert.equal(screen.queryByRole('dialog'),null);
 await click(screen.getByRole('button',{name:'Add delivery',exact:true}));assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'  Exact title  ');assert.equal(screen.getByRole('textbox',{name:'Tags'}).value,' same ');
 mounted.unmount();render(React.createElement(NativeShelf,{...props,initialView:'add',modal:true}));await screen.findByRole('dialog',{name:'Add delivery'});
 assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'  Exact title  ');
 await click(screen.getByRole('button',{name:'Save',exact:true}));await screen.findByRole('region',{name:'Delivery details'});
 const post=calls.findLast(c=>c.url==='/sources/register-many');assert.equal(post.options.body.title,'  Exact title  ');assert.deepEqual(post.options.body.tags,[' same ',' same ']);assert.equal(post.options.body.selections.length,1);
 assert.ok(calls.slice(calls.indexOf(post)+1).some(c=>c.url==='/entries/delivery'),'registration is followed by exact saved-entry readback, independent of preview/catalog refreshes');cleanup();
});

test('switching conversations resets the delivered-file page and clears only file selection, not typed metadata',async()=>{
 render(React.createElement(NativeShelf,{api,ownerKey:'conversation-reset',sessionId:'chat-A',initialView:'add'}));
 await click(await screen.findByRole('button',{name:'plan.pdf',exact:true}));await type(screen.getByRole('textbox',{name:'Title'}),'Keep this title');
 await click(screen.getByRole('button',{name:'Next files'}));await screen.findByRole('button',{name:'notes.txt',exact:true});
 await choose('Conversation','Campaign work');await waitFor(()=>{const call=calls.findLast(c=>c.url.startsWith('/sources/sessions/chat-B/artifacts?'));assert.ok(call);assert.equal(new URL(call.url,'http://localhost').searchParams.get('offset'),'0');});
 await screen.findByRole('button',{name:'plan.pdf',exact:true});assert.equal(screen.queryByRole('button',{name:'Remove plan.pdf'}),null);assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'Keep this title');
});

test('server filters and total-based pagination apply to all deliveries and reset their cursor',async()=>{
 const filteredApi=async(url,options)=>{const data=await api(url,options);return url.startsWith('/entries?')?{items:data.items,total:61}:data;};
 render(React.createElement(NativeShelf,{api:filteredApi,ownerKey:'filters',modal:false}));
 await screen.findByRole('region',{name:entry.title.trim()});
 await click(screen.getByRole('button',{name:'Next deliveries'}));await waitFor(()=>assert.ok(calls.some(c=>c.url.startsWith('/entries?')&&new URL(c.url,'http://localhost').searchParams.get('offset')==='30')));
 await type(screen.getByRole('textbox',{name:'Search deliveries'}),' launch ');await type(screen.getByRole('textbox',{name:'Project filter'}),' Website ');await choose('Delivery type','image');
 await waitFor(()=>{const u=new URL(calls.findLast(c=>c.url.startsWith('/entries?')).url,'http://localhost');assert.equal(u.searchParams.get('offset'),'0');assert.equal(u.searchParams.get('q'),' launch ');assert.equal(u.searchParams.get('kind'),'image');assert.equal(u.searchParams.get('project'),' Website ');});
 await screen.findByRole('region',{name:entry.title.trim()});await click(screen.getByRole('button',{name:'Clear filters'}));
 await waitFor(()=>{const u=new URL(calls.findLast(c=>c.url.startsWith('/entries?')).url,'http://localhost');assert.equal(u.searchParams.get('q'),'');assert.equal(u.searchParams.get('kind'),'');assert.equal(u.searchParams.get('project'),'');});cleanup();
});

test('details preview chooses preserved edition and file; downloads retain exact version and updates are explicit',async()=>{
 entry={...entry,title:'Versioned materials',file:files[0].file,files:files.map(f=>f.file),revision:1,current_version:'v1',versions:[{id:'v0',number:1,files:[{id:'old-image',name:'earlier.png',size:4,media_type:'image/png'}]},{id:'v1',number:2,files:[{id:'managed-pdf',name:'plan.pdf',size:4,media_type:'application/pdf'},{id:'managed-image',name:'cover.png',size:4,media_type:'image/png'}]}]};
 render(React.createElement(NativeShelf,{api,ownerKey:'versions',sessionId:'chat-A',modal:false}));
 await click(await screen.findByRole('button',{name:'Open delivery Versioned materials',exact:true}));await screen.findByRole('region',{name:'Delivery details'});
 await screen.findByRole('combobox',{name:'Preview version'});await choose('Preview version','Version 1');
 await screen.findByRole('img',{name:'earlier.png'});assert.ok(calls.some(c=>c.url==='/entries/delivery/thumbnail?version_id=v0&file_id=old-image'));
 await click(screen.getByRole('button',{name:'Download earlier.png, version 1'}));assert.equal(calls.at(-1).url,'/entries/delivery/versions/v0/files/old-image');assert.equal(downloads.at(-1).name,'earlier.png');
 const before=calls.filter(c=>c.url==='/entries/delivery/versions'&&c.options.method==='POST').length;
 await click(screen.getByRole('button',{name:'Add version',exact:true}));await click(await screen.findByRole('button',{name:'plan.pdf',exact:true}));
 assert.equal(calls.filter(c=>c.url==='/entries/delivery/versions'&&c.options.method==='POST').length,before);
 await click(screen.getByRole('button',{name:'Save new version',exact:true}));await screen.findByRole('region',{name:'Version 2'});
 const update=calls.findLast(c=>c.url==='/entries/delivery/versions');assert.deepEqual(update.options.body,{revision:1,files:[files[0].file],session_id:'chat-A',sources:[{file:files[0].file,source:files[0].source,session_id:'chat-A'}]});assert.equal(entry.revision,2);cleanup();
});

test('generation only fills blanks, fences edits, and an unmounted request cannot overwrite a reopened retained draft',async()=>{
 const retained=new Map(),props={api,ownerKey:'generation',sessionId:'chat-A',retained,initialView:'add'};
 const mounted=render(React.createElement(NativeShelf,props));await click(await screen.findByRole('button',{name:'plan.pdf',exact:true}));
 await type(screen.getByRole('textbox',{name:'Title'}),'  Human title  ');await type(screen.getByRole('textbox',{name:'Tags'}),' repeat ');await click(screen.getByRole('button',{name:'Add tag'}));await type(screen.getByRole('textbox',{name:'Tags'}),' repeat ');
 await click(screen.getByRole('button',{name:'Generate',exact:true}));await waitFor(()=>assert.ok(generationResolve));
 const request=calls.findLast(c=>c.url==='/generation/draft').options.body;
 assert.deepEqual(request.requested_fields,['description']);assert.deepEqual(request.supplied_metadata,{title:'  Human title  ',tags:[' repeat ',' repeat ']});
 await type(screen.getByRole('textbox',{name:'Description'}),'Written during request');
 await act(async()=>generationResolve({draft:{title:'replace',description:'late description',tags:['replace']}}));
 assert.equal(screen.getByRole('textbox',{name:'Description'}).value,'Written during request');
 await click(screen.getByRole('button',{name:'Generate',exact:true}));const late=generationResolve;
 mounted.unmount();render(React.createElement(NativeShelf,props));await type(screen.getByRole('textbox',{name:'Title'}),'Newer retained title');
 await act(async()=>late({draft:{description:'old instance'}}));
 assert.equal(retained.get('generation').metadata.values.title,'Newer retained title');
 cleanup();
});

test('real Chromium layout: themed Together/Library, unclipped native selects, opaque Add and reachable Save at compact viewport', {skip:!process.env.NATIVE_LIBRARY_BROWSER},async()=>{
 const {chromium,expect}=requireHost('@playwright/test'),{createServer}=await import('node:http');
 const {compile}=requireHost('@tailwindcss/node'),{Scanner}=requireHost('@tailwindcss/oxide'),desktopSource=join(source,'apps/desktop/src');
 const compiler=await compile(await readFile(join(desktopSource,'styles.css'),'utf8'),{base:desktopSource,onDependency:()=>{}});
 const scanner=new Scanner({sources:[{base:desktopSource,negated:false,pattern:'**/*.{tsx,ts,jsx,js}'}]});
 const codiconFont=(await readFile(requireHost.resolve('@vscode/codicons/dist/codicon.ttf'))).toString('base64');
 const nativeCSS=compiler.build(scanner.scan()).replace(/url\([^)]*codicon\.ttf[^)]*\)/g,`url("data:font/ttf;base64,${codiconFont}")`);
 const fixtureEntry={...entry,title:'Fictional launch materials',description:'A plan and its companion artwork, kept together.',created:1767225600,current_version:'v1',versions:[{id:'v1',number:1,files:[{id:'managed-pdf',name:'plan.pdf',media_type:'application/pdf'},{id:'managed-image',name:'cover.png',media_type:'image/png'}]}]};
 const contents=`import React from 'react';import {createRoot} from 'react-dom/client';import {NativeShelf} from '${root}/ui/NativeShelf.jsx';
 document.head.appendChild(Object.assign(document.createElement('style'),{textContent:${JSON.stringify(nativeCSS)}}));
 const entry=${JSON.stringify(fixtureEntry)},files=${JSON.stringify(files)};
 const api=async(url,options)=>{(window.__libraryRequests??=[]).push({url,method:options?.method||'GET'});const u=new URL(url,'http://localhost');if(u.pathname==='/entries')return {items:[entry],total:1};if(u.pathname==='/settings')return {enabled_views:['together','library','gallery'],default_view:'together'};if(u.pathname==='/generation/settings')return {previous_exchanges:10};if(u.pathname==='/sources/sessions')return {items:[{id:'chat-A',title:'Fictional launch work'},{id:'chat-B',title:'Fictional campaign'}],has_more:false};if(u.pathname.endsWith('/artifacts'))return {items:files,has_more:false};if(u.pathname.includes('thumbnail'))throw Error('Fixture deliberately uses type-icon fallback');if(u.pathname==='/entries/delivery')return entry;throw Error('Unexpected fixture request '+url);};
 document.body.style.margin='0';document.body.style.padding='24px';createRoot(document.getElementById('root')).render(<NativeShelf api={api} ownerKey="browser" sessionId="chat-A" modal={false}/>);`;
 await build({stdin:{contents,loader:'jsx',resolveDir:root},outfile:join(scratch,'browser.js'),bundle:true,format:'esm',target:'es2022',jsx:'automatic',nodePaths:[join(source,'node_modules')],loader:{'.css':'text','.woff2':'dataurl','.woff':'dataurl','.ttf':'dataurl'},alias:{react:join(source,'node_modules/react'),'react-dom':join(source,'node_modules/react-dom'),'@saved/presentation':join(root,'ui/presentation.desktop.jsx'),'@':join(source,'apps/desktop/src')},plugins:[{name:'browser-real-sdk',setup(b){b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'native-sdk'}));b.onLoad({filter:/.*/,namespace:'native-sdk'},()=>({contents:components,resolveDir:source,loader:'ts'}));}}]});
 const bundle=await readFile(join(scratch,'browser.js'));
 const server=createServer((req,res)=>{res.setHeader('Content-Type',req.url==='/bundle.js'?'text/javascript':'text/html');res.end(req.url==='/bundle.js'?bundle:'<!doctype html><html><body><div id="root"></div><script type="module" src="/bundle.js"></script></body></html>');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const browser=await chromium.launch({headless:true});
 const proof=process.env.NATIVE_LIBRARY_PROOF||join(scratch,'proof');await mkdir(proof,{recursive:true});
 try{const page=await browser.newPage({viewport:{width:1200,height:850}}),errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('Browser error:',e.message);});await page.goto('http://127.0.0.1:'+server.address().port);
  const group=page.getByRole('region',{name:'Fictional launch materials'});await expect(group).toBeVisible();
  await page.evaluate(()=>document.fonts.ready);assert.equal(await page.evaluate(()=>document.fonts.check('16px codicon')),true,'real icon font must load');
  await expect(page.getByRole('alert')).toHaveCount(0);
  const paint=boxes=>boxes.evaluateAll(elements=>elements.map(el=>{const glyph=el.querySelector('.codicon-check'),style=getComputedStyle(el),ink=glyph&&getComputedStyle(glyph),rect=glyph?.getBoundingClientRect();return {checked:el.getAttribute('aria-checked'),state:el.getAttribute('data-state'),background:style.backgroundColor,glyph:!!glyph&&ink.display!=='none'&&ink.visibility==='visible'&&Number(ink.opacity)>0&&rect.width>0&&rect.height>0,title:el.title,description:el.getAttribute('aria-description')};}));
  for(const view of ['Together','Library','Gallery']){
   await page.getByRole('button',{name:view,exact:true}).click();
   const boxes=page.locator('.ds-native-select-checkbox'),first=boxes.first();await expect(first).toBeVisible();
   const empty=await paint(boxes);assert.ok(empty.every(box=>box.state==='unchecked'&&box.checked==='false'&&!box.glyph));
   assert.ok(empty.every(box=>box.title==='Select entire delivery: Fictional launch materials'&&box.description===box.title),'whole-delivery hint remains natively available and accessible without a TooltipTrigger');
   // Natural keyboard input exercises the native control and host modality gate.
   for(let n=0;n<40&&!await first.evaluate(el=>el===document.activeElement);n++)await page.keyboard.press('Tab');
   assert.equal(await first.evaluate(el=>el===document.activeElement),true);await page.keyboard.press('Space');
   await expect(page.getByText('1 delivery selected',{exact:true})).toBeVisible();
   const selectedPaint=await paint(boxes);assert.ok(selectedPaint.every(box=>box.state==='checked'&&box.checked==='true'&&box.glyph&&box.background!==empty[0].background&&box.background!=='rgba(0, 0, 0, 0)'),view+' must paint actual native check glyphs and selected backgrounds on every companion');
   await first.hover();await page.waitForTimeout(900);assert.deepEqual(await paint(boxes),selectedPaint,'hover hint delay must not overwrite checkbox state');
   await page.mouse.move(1,1);await page.keyboard.press('Tab');await page.keyboard.press('Shift+Tab');await page.waitForTimeout(900);assert.deepEqual(await paint(boxes),selectedPaint,'keyboard focus/hint delay must not overwrite checkbox state');
   await page.screenshot({animations:'disabled',path:join(proof,'native-'+view.toLowerCase()+'-checked.png')});
   await page.getByRole('button',{name:'Clear delivery selection'}).click();
   const cleared=await paint(boxes);assert.ok(cleared.every((box,i)=>box.state==='unchecked'&&box.checked==='false'&&!box.glyph&&box.background===empty[i].background),'Clear removes the actual checked painting');
  }
  await page.getByRole('button',{name:'Together',exact:true}).click();
  const groupBox=group.getByRole('checkbox',{name:'Select delivery Fictional launch materials'});await expect(groupBox).not.toBeChecked();
  const lightGradient=await group.evaluate(el=>getComputedStyle(el).backgroundImage);assert.match(lightGradient,/linear-gradient/);
  for(const selector of ['.ds-native-group','.ds-native-file-card','.ds-native-visual'])assert.equal(await page.locator(selector).first().evaluate(el=>getComputedStyle(el).borderRadius),'0px');
  const toggle=group.locator('.ds-native-group-toggle');
  const heading=group.locator('header');assert.ok((await toggle.boundingBox()).width>(await heading.boundingBox()).width*.65,'disclosure owns the full header, not only its arrow');
  await group.getByText('Fictional launch materials',{exact:true}).click();await expect(toggle).toHaveAttribute('aria-expanded','false');await expect(group.getByRole('button',{name:'Preview plan.pdf'})).toBeHidden();
  await toggle.focus();await page.keyboard.press('Enter');await expect(toggle).toHaveAttribute('aria-expanded','true');await page.keyboard.press('Space');await expect(toggle).toHaveAttribute('aria-expanded','false');await page.keyboard.press('Space');await expect(toggle).toHaveAttribute('aria-expanded','true');
  await page.screenshot({animations:'disabled',path:join(proof,'native-together.png')});
  await page.evaluate(()=>{document.documentElement.classList.add('dark');document.documentElement.style.setProperty('--theme-secondary','#2d2a25');document.documentElement.style.setProperty('--theme-accent-soft','#35302a');document.documentElement.style.setProperty('--theme-foreground','#ececef');document.documentElement.style.setProperty('--theme-midground','#d5af66');document.documentElement.style.setProperty('--theme-primary','#bd8f58');document.documentElement.style.setProperty('--ui-chat-bubble-opaque-background','#202024');document.documentElement.style.setProperty('--ui-bg-editor','#17171b');document.body.style.background='var(--ui-bg-editor)';});
  const darkGradient=await group.evaluate(el=>getComputedStyle(el).backgroundImage);assert.match(darkGradient,/linear-gradient/);assert.notEqual(darkGradient,lightGradient);await page.screenshot({animations:'disabled',path:join(proof,'native-together-dark.png')});
  await page.setViewportSize({width:360,height:640});assert.equal(await group.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);await page.screenshot({animations:'disabled',path:join(proof,'native-together-mobile.png')});await page.setViewportSize({width:1200,height:850});
  await page.evaluate(()=>{document.documentElement.classList.remove('dark');for(const key of ['--theme-secondary','--theme-accent-soft','--theme-foreground','--theme-midground','--theme-primary','--ui-chat-bubble-opaque-background','--ui-bg-editor'])document.documentElement.style.removeProperty(key);document.body.style.background='';});
  await page.getByRole('button',{name:'Library',exact:true}).click();await expect(page.getByRole('complementary',{name:'File preview'})).toBeVisible();for(const selector of ['.ds-native-library-list','.ds-native-inspector','.ds-native-visual-large'])assert.equal(await page.locator(selector).first().evaluate(el=>getComputedStyle(el).borderRadius),'0px');await page.screenshot({animations:'disabled',path:join(proof,'native-library.png')});
  assert.notEqual(await page.getByRole('button',{name:'Add delivery',exact:true}).evaluate(el=>getComputedStyle(el).borderRadius),'0px','ordinary host buttons retain native corners');
  await page.getByRole('button',{name:'Add delivery',exact:true}).click();const dialog=page.getByRole('dialog');await expect(dialog.getByRole('button',{name:'plan.pdf',exact:true})).toBeVisible();
  assert.equal(await dialog.evaluate(el=>getComputedStyle(el).borderRadius),'0px');assert.equal(await dialog.getByRole('button',{name:'plan.pdf',exact:true}).evaluate(el=>getComputedStyle(el).borderRadius),'0px');
  await dialog.getByRole('textbox',{name:'Find conversation'}).fill('launch');await dialog.getByRole('textbox',{name:'Find conversation'}).press('Enter');assert.equal(await page.evaluate(()=>window.__libraryRequests.filter(c=>c.url==='/sources/register-many').length),0);
  await page.setViewportSize({width:560,height:600});await dialog.getByRole('combobox',{name:'Conversation'}).click();await expect(page.getByRole('option',{name:'Fictional campaign'})).toBeInViewport();await page.keyboard.press('Escape');await expect(dialog).toBeVisible();
  await dialog.getByRole('button',{name:'Select all files on this page'}).click();await dialog.getByRole('textbox',{name:'Tags'}).fill(' exact tag ');await dialog.getByRole('button',{name:'Add tag'}).click();
  const save=dialog.getByRole('button',{name:'Save',exact:true});await save.scrollIntoViewIfNeeded();await expect(save).toBeInViewport({ratio:1});
  assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);assert.notEqual(await dialog.evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 0, 0, 0)');
  await page.screenshot({animations:'disabled',path:join(proof,'native-add-compact.png')});await page.setViewportSize({width:360,height:640});await save.scrollIntoViewIfNeeded();await expect(save).toBeInViewport({ratio:1});assert.equal(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1),true);await page.screenshot({animations:'disabled',path:join(proof,'native-add-mobile.png')});
  assert.deepEqual(errors,[]);console.log('Native library browser proof:',proof);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
