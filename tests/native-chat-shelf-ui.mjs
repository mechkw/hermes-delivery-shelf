// Focused native component/contribution tests, not a browser preview or an
// installed-client readiness claim. Only SDK state/transport are test doubles.
import {test,after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,symlink,rm} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {uiExports} from './native-components.mjs';
const root=resolve('.'),source=process.env.HERMES_UI_SOURCE||resolve('../shelf-native-host');
// Exercise the checked-in OFFICIAL contract, not either checkout's dirty
// localActions extension. The plugin and real host middleware/hook are bundled
// together; only SDK state/transport/native-OS boundaries remain doubles.
const stockComposer=execFileSync('git',['show','HEAD:apps/desktop/src/app/chat/composer/contrib.ts'],{cwd:source,encoding:'utf8'});
const stockSubmit=execFileSync('git',['show','HEAD:apps/desktop/src/app/chat/composer/hooks/use-composer-submit.ts'],{cwd:source,encoding:'utf8'});
assert.ok(!stockComposer.includes('localActions'),'fixture must use the stock official composer surface');
const requireHost=createRequire(join(source,'package.json'));
const {JSDOM}=requireHost('jsdom'),{build}=requireHost('esbuild');
const dom=new JSDOM('<!doctype html><html><body></body></html>',{url:'http://localhost/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Element','Node','MutationObserver','CustomEvent','Event','KeyboardEvent','MouseEvent','getComputedStyle','navigator','localStorage'])Object.defineProperty(globalThis,key,{value:key==='getComputedStyle'?dom.window.getComputedStyle.bind(dom.window):dom.window[key],configurable:true});
globalThis.requestAnimationFrame=dom.window.requestAnimationFrame.bind(dom.window);globalThis.cancelAnimationFrame=dom.window.cancelAnimationFrame.bind(dom.window);
window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){},addListener(){},removeListener(){}});
for(const key of Object.getOwnPropertyNames(dom.window).filter(key=>/^(?:HTML|SVG|Node|Document|Event|FocusEvent|MutationObserver)/.test(key)))if(!(key in globalThis))Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
globalThis.ResizeObserver=class{observe(){}unobserve(){}disconnect(){}};
globalThis.PointerEvent=dom.window.MouseEvent;
HTMLElement.prototype.scrollIntoView=function(){};HTMLElement.prototype.hasPointerCapture=()=>false;HTMLElement.prototype.setPointerCapture=function(){};HTMLElement.prototype.releasePointerCapture=function(){};
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const scratch=await mkdtemp(join(process.env.TMPDIR,'native-chat-shelf-'));
await symlink(join(source,'node_modules'),join(scratch,'node_modules'),'dir');
const {atom}=requireHost('nanostores');
const atoms={profile:atom('default'),connectionId:atom('backend-A'),focusedSessionOwner:atom({connectionId:'backend-A',profile:'default'}),focusedStoredSessionId:atom('chat-A')};
const notifications=[];
globalThis.__shelfHost={state:atoms,notify(message){notifications.push(message);},navigate(){throw Error('Must not navigate');},openSession(){}};
const components=Object.entries({...uiExports,'components/ui/codicon':['Codicon'],'components/ui/segmented-control':['SegmentedControl']}).map(([file,names])=>`export {${names.join(',')}} from '${source}/apps/desktop/src/${file}';`).join('\n');
await build({entryPoints:[join(root,'ui/desktop.jsx')],outfile:join(scratch,'plugin.mjs'),bundle:true,format:'esm',platform:'node',target:'es2022',packages:'external',jsx:'automatic',define:{'import.meta.env':'{}'},loader:{'.css':'text'},alias:{'@saved/presentation':join(root,'ui/presentation.desktop.jsx'),'@':join(source,'apps/desktop/src')},plugins:[{name:'sdk-test-boundaries',setup(b){b.onLoad({filter:/\/hooks\/use-composer-submit\.ts$/},()=>({contents:stockSubmit,resolveDir:join(source,'apps/desktop/src/app/chat/composer/hooks'),loader:'ts'}));b.onLoad({filter:/\/app\/chat\/composer\/contrib\.ts$/},()=>({contents:stockComposer,resolveDir:join(source,'apps/desktop/src/app/chat/composer'),loader:'ts'}));b.onResolve({filter:/^@hermes\/plugin-sdk$/},()=>({path:'sdk',namespace:'native-sdk'}));b.onLoad({filter:/.*/,namespace:'native-sdk'},()=>({contents:components+`\nexport const host=globalThis.__shelfHost;export {atom} from 'nanostores';export {useStore as useValue} from '@nanostores/react';import {COMPOSER_AREAS as hostAreas,runComposerMiddleware} from '${source}/apps/desktop/src/app/chat/composer/contrib';import {useMiddlewareSubmit} from '${source}/apps/desktop/src/app/chat/composer/hooks/use-middleware-submit';import {useComposerSubmit} from '${source}/apps/desktop/src/app/chat/composer/hooks/use-composer-submit';globalThis.__shelfUseComposerSubmit=useComposerSubmit;export {COMPOSER_AREAS} from '${source}/apps/desktop/src/app/chat/composer/contrib';import {registry} from '${source}/apps/desktop/src/contrib/registry';globalThis.__shelfMiddleware=runComposerMiddleware;globalThis.__shelfUseMiddlewareSubmit=useMiddlewareSubmit;globalThis.__shelfRegistry=registry;export {TITLEBAR_AREAS} from '${source}/apps/desktop/src/sdk/areas';export {PALETTE_AREA} from '${source}/apps/desktop/src/app/command-palette/contrib';export const ROUTES_AREA='routes',SIDEBAR_NAV_AREA='sidebar.nav';`,resolveDir:source,loader:'ts'}));}}]});
const React=requireHost('react'),{render,renderHook,fireEvent,screen,waitFor,cleanup,act}=requireHost('@testing-library/react');
// The real submit engine imports app stores with process-lifetime maintenance
// timers. Own their initial timers in this bounded fixture and retire on exit.
const hostTimers=[],nativeSetInterval=globalThis.setInterval,nativeSetTimeout=globalThis.setTimeout;
const hostChannels=[],NativeBroadcastChannel=globalThis.BroadcastChannel;
globalThis.BroadcastChannel=class extends NativeBroadcastChannel{constructor(...args){super(...args);hostChannels.push(this);}};
globalThis.setInterval=(...args)=>{const timer=nativeSetInterval(...args);hostTimers.push(timer);return timer;};
globalThis.setTimeout=(...args)=>{const timer=nativeSetTimeout(...args);hostTimers.push(timer);return timer;};
const {default:plugin}=await import(pathToFileURL(join(scratch,'plugin.mjs')).href);

const downloads=[];
URL.createObjectURL=blob=>{downloads.push({media_type:blob.type,size:blob.size});return 'blob:native-test';};URL.revokeObjectURL=()=>{};
HTMLAnchorElement.prototype.click=function(){downloads.at(-1).name=this.download;};
const contributions=[],disposals=[],calls=[],settingsPages=[];
const files=[{id:'f-one',name:'one.pdf',file:{root:'workspace',path:'one.pdf'},source:{session_id:'chat-A',message_id:'m-one'}},{id:'f-two',name:'two.png',file:{root:'workspace',path:'two.png'},source:{session_id:'chat-A',message_id:'m-two'}}];
let entry={id:'entry-A',title:'Saved delivery',description:'Saved description',tags:['saved'],kind:'document',project:'',revision:1,session_id:'chat-A',file:files[0].file,current_version:'version-one',versions:[{id:'version-one',number:1,created:1,files:[{id:'managed-one',name:'one.pdf',size:4,sha256:'hash',media_type:'application/pdf'}]}]};
let generationResolve;
const shelfSettings={trash_retention_days:60,auto_cleanup:true,timezone:'auto',hour_cycle:'auto',default_view:'together',enabled_views:['together','library','gallery'],generate_metadata:true,context_messages:10};
const ctx={registerSettingsPage(page){settingsPages.push(page);return()=>{};},registerMany(items){contributions.push(...items);for(const item of items)if(item.area==='composer.middleware')disposals.push(globalThis.__shelfRegistry.register(item));return()=>{};},onDispose(fn){disposals.push(fn);},os:{writeClipboard:async()=>true},rest:async(url,options={})=>{
 calls.push({url,options});const path=new URL(url,'http://localhost/').pathname;
 if(path==='/status')return {enabled:true};
 if(path==='/settings'){if(options.method==='PUT')Object.assign(shelfSettings,options.body);return {...shelfSettings};}
 if(path==='/storage')return {total_bytes:8192,total_entries:3,total_files:4,pending_purges:1,pending_purge_bytes:1024,scope:'managed_payloads',states:{active:{entries:1,files:2,bytes:4096},archived:{entries:1,files:1,bytes:2048},trash:{entries:1,files:0,bytes:0},pending_delete:{entries:0,files:0,bytes:1024}}};
 if(path==='/generation/settings')return {previous_exchanges:10};
 if(path==='/sources/sessions')return {items:[{id:'chat-A',title:'Current work'}],has_more:false};
 if(path.endsWith('/artifacts'))return {items:files,has_more:false};
 if(path==='/entries')return {items:[entry],total:1,has_more:false};
 if(path==='/generation/draft')return new Promise(resolve=>{generationResolve=resolve;});
 if(path==='/sources/register-many'){if(!options.body.title){const e=Error('Invalid metadata: title/blank');e.code='metadata_invalid';throw e;}entry={...entry,title:options.body.title,description:options.body.description,tags:options.body.tags};return entry;}
 if(path==='/entries/entry-A/versions'){entry={...entry,revision:2,current_version:'version-two',versions:[...entry.versions,{id:'version-two',number:2,created:2,files:[{id:'managed-two',name:'two.png',size:5,sha256:'hash2',media_type:'image/png'}]}]};return entry;}
 if(path==='/entries/entry-A')return entry;
 if(path==='/entries/entry-A/versions/version-one/files/managed-one')return {name:'one.pdf',base64:'dGVzdA==',media_type:'application/pdf'};
 throw Error('Unexpected endpoint '+url);
}};
assert.doesNotThrow(()=>plugin.register(ctx),'activation must work without the nonstandard localActions area');

const attach=contributions.find(c=>c.area==='composer.attachments'),palette=contributions.find(c=>c.id==='add-delivery-shelf'),portal=contributions.find(c=>c.id==='delivery-shelf-dialog');
const writesCount=()=>calls.filter(c=>c.options.method==='POST'&&!new URL(c.url,'http://localhost/').pathname.endsWith('/thumbnail')).length;
const click=async(element)=>act(async()=>fireEvent.click(element));
const type=async(element,value)=>act(async()=>fireEvent.change(element,{target:{value}}));
after(async()=>{cleanup();disposals.forEach(fn=>fn());dom.window.close();hostTimers.forEach(timer=>{clearInterval(timer);clearTimeout(timer);});hostChannels.forEach(channel=>channel.close());globalThis.setInterval=nativeSetInterval;globalThis.setTimeout=nativeSetTimeout;globalThis.BroadcastChannel=NativeBroadcastChannel;await rm(scratch,{recursive:true,force:true});});

test('public native Settings page persists retention, views and timezone without any update authorization',async()=>{
 assert.equal(settingsPages.length,1);
 render(React.createElement(settingsPages[0].render));
 await screen.findByRole('heading',{name:'Delivery Shelf settings'});
 assert.equal(screen.queryByText(/auto.?save|standing|always update|allow updates/i),null);
 await click(screen.getByRole('combobox',{name:'Trash retention'}));await click(await screen.findByRole('option',{name:'30 days',exact:true}));
 await type(screen.getByRole('textbox',{name:'Timezone'}),'America/New_York');
 assert.equal(screen.getByRole('switch',{name:'Enable Gallery'}).getAttribute('aria-checked'),'true');
 assert.equal(screen.getByRole('switch',{name:'Generate metadata by default'}).getAttribute('aria-checked'),'true');
 assert.equal(screen.getByRole('switch',{name:'Automatic due-item cleanup'}).getAttribute('aria-checked'),'true');
 await click(screen.getByRole('switch',{name:'Enable Gallery'}));
 await click(screen.getByRole('button',{name:'Save settings'}));
 await screen.findByText('Settings saved.');
 const put=calls.findLast(c=>new URL(c.url,'http://localhost').pathname==='/settings'&&c.options.method==='PUT');
 assert.equal(put.options.body.trash_retention_days,30);assert.equal(put.options.body.timezone,'America/New_York');assert.deepEqual(put.options.body.enabled_views,['together','library']);
 assert.ok(calls.slice(calls.indexOf(put)+1).some(c=>new URL(c.url,'http://localhost').pathname==='/settings'&&!c.options.method));
 const usage=screen.getByRole('region',{name:'Storage usage'});
 assert.match(usage.textContent,/8 KiB/);assert.match(usage.textContent,/3 deliveries/);assert.match(usage.textContent,/4 files/);
 assert.match(usage.textContent,/Archive/);assert.match(usage.textContent,/Pending deletion/);assert.match(usage.textContent,/1 purge awaiting completion/);
 assert.equal(usage.querySelector('pre'),null,'storage must be labeled, not raw JSON');
 cleanup();
 render(React.createElement(settingsPages[0].render));
 await waitFor(()=>assert.equal(screen.getByRole('textbox',{name:'Timezone'}).value,'America/New_York'));
 assert.equal(screen.getByRole('switch',{name:'Enable Gallery'}).getAttribute('aria-checked'),'false');cleanup();
});

test('quick Add passes through stock submit unchanged, bare Shelf opens browsing only',async()=>{

 assert.equal(contributions.filter(c=>c.area==='composer.middleware').length,1);
 assert.equal(contributions.filter(c=>c.area==='composer.localActions').length,0);
 const sends=[],from=calls.length;
 const hook=renderHook(()=>globalThis.__shelfUseMiddlewareSubmit((...args)=>{sends.push(args);return true;}));
 render(React.createElement(portal.render));
 for(const text of ['/shelf']){
  const attachments=Object.freeze([{id:'draft-file',name:'keep.pdf',status:'ready'}]);
  const draft=Object.freeze({text,attachments});
  let accepted;await act(async()=>{accepted=await hook.result.current.onSubmit(text,{attachments,storedSessionId:'background-chat',sessionId:'runtime-background',fromQueue:true});});
  assert.equal(accepted,false,'host rejection retains the submitted draft rather than accepting it');
  assert.equal(draft.text,text);assert.equal(draft.attachments,attachments);
  await screen.findByRole('region',{name:'Delivery catalog'});
  assert.equal(screen.queryByRole('form',{name:'Add delivery'}),null);
  // The catalog contains a saved one.pdf too. Wait for it so this cannot pass
  // only because the catalog's debounced load has not completed, and distinguish
  // its navigation button from an aria-pressed conversation-file selection.
  const savedFile=await screen.findByRole('button',{name:'one.pdf',exact:true});
  assert.equal(savedFile.hasAttribute('aria-pressed'),false,'browsing must not expose a selectable conversation artifact');
  assert.ok(screen.queryByRole('region',{name:'Delivered files'})===null,'browsing must not open the conversation-file chooser');
  await click(screen.getByRole('button',{name:'Close',exact:true}));await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));
 }
 assert.equal(sends.length,0);assert.ok(!calls.slice(from).some(c=>new URL(c.url,'http://localhost/').pathname.endsWith('/artifacts')));
 for(const text of ['/shelf add','/shelf add r1']){
  const attachments=[{id:'keep',name:'draft.pdf'}],draft={text,attachments};
  assert.equal(await globalThis.__shelfMiddleware(draft),draft);
  assert.equal(await hook.result.current.onSubmit(text,{attachments,storedSessionId:'background-chat'}),true);
  assert.equal(sends.at(-1)[0],text);assert.equal(sends.at(-1)[1].storedSessionId,'background-chat');
 }
 assert.equal(calls.slice(from).filter(c=>c.options.method==='POST').length,0);
 cleanup();
});

test('typed chooser loads files only after an explicit conversation choice and never inherits it on reopening',async()=>{
 render(React.createElement(portal.render));
 await act(async()=>assert.equal(await globalThis.__shelfMiddleware({text:'/shelf'}),null));
 await click(await screen.findByRole('button',{name:'Add delivery',exact:true}));
 await screen.findByRole('combobox',{name:'Conversation'});
 await click(screen.getByRole('combobox',{name:'Conversation'}));
 await click(await screen.findByRole('option',{name:'Current work'}));
 await screen.findByRole('button',{name:'one.pdf',exact:true});
 await click(screen.getByRole('button',{name:'one.pdf',exact:true}));
 await type(screen.getByRole('textbox',{name:'Title'}),'  Retained command title  ');
 await click(screen.getByRole('button',{name:'Close',exact:true}));
 await act(async()=>assert.equal(await globalThis.__shelfMiddleware({text:'/shelf'}),null));
 await click(await screen.findByRole('button',{name:'Add delivery',exact:true}));
 await screen.findByRole('combobox',{name:'Conversation'});
 assert.equal(screen.getByRole('combobox',{name:'Conversation'}).textContent,'Choose a conversation');
 assert.equal(screen.queryByRole('button',{name:'one.pdf',exact:true}),null);
 assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'  Retained command title  ');
 await click(screen.getByRole('button',{name:'Close',exact:true}));cleanup();
});

test('stock dispatchSubmit restores cancelled text and attachments only to their originating composer',async()=>{
 for(const moved of [false,true]){
  const sent=[],stashed=[],painted=[],retried=[],attachments=[{id:'owned-attachment',name:'keep.pdf',kind:'file',status:'ready'}];
  const scope={current:'origin-chat'};
  const options={activeQueueSessionKey:'origin-chat',activeQueueSessionKeyRef:{current:'origin-chat'},attachments,busy:false,clearDraft(){},disabled:false,draftScopeRef:scope,draftRef:{current:'/shelf'},drainNextQueued:async()=>false,editorRef:{current:null},exitQueuedEdit:()=>false,focusInput(){},inputDisabled:false,loadIntoComposer:(...args)=>painted.push(args),onCancel(){},onSteer:undefined,onSteerHidden:undefined,queueCurrentDraft:()=>false,queueEdit:null,queuedPrompts:[],sessionId:'runtime-origin',setComposerText(){},stashAt:(...args)=>stashed.push(args),rememberDraftRetry:(...args)=>retried.push(args)};
  const hook=renderHook(()=>{
   const {onSubmit}=globalThis.__shelfUseMiddlewareSubmit((...args)=>{sent.push(args);return true;});
   return globalThis.__shelfUseComposerSubmit({...options,onSubmit});
  });
  await act(async()=>{
   hook.result.current.dispatchSubmit('/shelf',attachments);
   if(moved)scope.current='different-chat';
  });
  await waitFor(()=>assert.equal(stashed.length,1));
  assert.deepEqual(stashed[0],['origin-chat','/shelf',attachments]);
  assert.equal(retried[0][0],'origin-chat');assert.equal(retried[0][1].text,'/shelf');
  assert.equal(sent.length,0);assert.equal(painted.length,moved?0:1);
  if(!moved)assert.deepEqual(painted[0],['/shelf',attachments]);
  cleanup();
 }
});

test('native command palette discovers Shelf and opens the same Add dialog without a write',async()=>{
 const palette=contributions.find(c=>c.area==='palette'&&c.id==='add-delivery-shelf');
 assert.ok(palette,'Shelf must be discoverable in the native command palette');
 assert.ok(palette.data.keywords.includes('/shelf add'));
 render(React.createElement(portal.render));const writes=writesCount();
 await act(async()=>palette.data.run());await screen.findByRole('form',{name:'Add delivery'});
 assert.equal(writesCount(),writes);
 await act(async()=>fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape',code:'Escape'}));
 await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));cleanup();
});
test('stock attach and palette share one native Add dialog; dismiss preserves edits and files',async()=>{
 assert.equal(attach.data.label,'Delivery Shelf');assert.equal(contributions.filter(c=>c.area==='composer.localActions').length,0);
 render(React.createElement(portal.render));assert.equal(screen.queryByRole('dialog'),null);
 await act(async()=>attach.data.run({insertText(){throw Error('Must not touch composer');}}));
 await screen.findByRole('dialog');await screen.findByRole('button',{name:'one.pdf'});
 assert.equal(screen.getByRole('combobox',{name:'Conversation'}).textContent,'Current work');
 await click(screen.getByRole('button',{name:'one.pdf'}));await click(screen.getByRole('button',{name:'two.png'}));
 await type(screen.getByRole('textbox',{name:'Title'}),'  typed title  ');await type(screen.getByRole('textbox',{name:'Tags'}),'  Exact tag  ');
 await click(screen.getByRole('button',{name:'Close',exact:true}));await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));
 await act(async()=>palette.data.run());await screen.findByRole('dialog');
 await screen.findByRole('button',{name:'one.pdf'});
 assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'  typed title  ');assert.equal(screen.getByRole('textbox',{name:'Tags'}).value,'  Exact tag  ');
 assert.equal(screen.getByRole('button',{name:'one.pdf',exact:true}).getAttribute('aria-pressed'),'true');assert.equal(screen.getByRole('button',{name:'two.png',exact:true}).getAttribute('aria-pressed'),'true');
});
test('native Generate keeps typed title/tags exact and applies blank fields; edits during request fence results',async()=>{
 await click(screen.getByRole('button',{name:'Generate',exact:true}));await waitFor(()=>assert.ok(generationResolve));
 const request=calls.findLast(c=>c.url.startsWith('/generation/draft')).options.body;
 assert.deepEqual(request.requested_fields,['description']);assert.deepEqual(request.supplied_metadata,{tags:['  Exact tag  '],title:'  typed title  '});
 await act(async()=>generationResolve({draft:{title:'ignored',description:'Suggested description',tags:['ignored']},context:{}}));
 assert.equal(screen.getByRole('textbox',{name:'Description'}).value,'Suggested description');assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'  typed title  ');assert.equal(screen.getByRole('textbox',{name:'Tag 1'}).value,'  Exact tag  ');
 await click(screen.getByRole('button',{name:'Generate',exact:true}));await type(screen.getByRole('textbox',{name:'Description'}),'  typed during generation  ');
 await act(async()=>generationResolve({draft:{description:'Late overwrite'},context:{}}));assert.equal(screen.getByRole('textbox',{name:'Description'}).value,'  typed during generation  ');
});
test('native Save has no client title gate; server rejection retains file and metadata; success reads entry back',async()=>{
 await type(screen.getByRole('textbox',{name:'Title'}),'');await click(screen.getByRole('button',{name:'Save',exact:true}));
 await screen.findByRole('alert');assert.equal(calls.findLast(c=>c.url.startsWith('/sources/register-many')).options.body.title,'');assert.equal(screen.getByRole('button',{name:'one.pdf'}).getAttribute('aria-pressed'),'true');
 await type(screen.getByRole('textbox',{name:'Title'}),'Final title');await click(screen.getByRole('button',{name:'Save',exact:true}));
 await screen.findByRole('region',{name:'Delivery details'});const post=calls.findLast(c=>c.url.startsWith('/sources/register-many'));assert.equal(post.options.body.selections.length,2);assert.ok(calls.find(c=>c.url==='/entries/entry-A?profile=default'));
});
test('native versions retrieved and updated only by explicit Save new version',async()=>{
 await screen.findByRole('region',{name:'Version 1'});assert.equal(calls.filter(c=>c.url.startsWith('/entries/entry-A/versions')).length,0);
 await click(screen.getByRole('button',{name:'Download one.pdf, version 1'}));assert.deepEqual(downloads.at(-1),{name:'one.pdf',media_type:'application/pdf',size:4});
 await click(screen.getByRole('button',{name:'Add version',exact:true}));await screen.findByRole('button',{name:'two.png',exact:true});
 assert.equal(calls.filter(c=>c.url.startsWith('/entries/entry-A/versions')&&c.options.method==='POST').length,0);
 await click(screen.getByRole('button',{name:'Save new version',exact:true}));await screen.findByRole('region',{name:'Version 2'});
 const update=calls.findLast(c=>c.url.startsWith('/entries/entry-A/versions'));assert.equal(update.options.body.revision,1);assert.deepEqual(update.options.body.files,files.map(f=>f.file));
});
test('official explicit gestures reopen Add from details without silently saving; retain the exact draft',async()=>{
 for(const action of [attach,palette,attach]){
  await click(screen.getByRole('button',{name:'Close',exact:true}));await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));
  const writes=writesCount();
  await act(async()=>action.data.run());
  await screen.findByRole('form',{name:'Add delivery'});await screen.findByRole('button',{name:'one.pdf',exact:true});
  assert.equal(screen.getAllByRole('dialog').length,1);assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'Final title');
  assert.equal(screen.getByRole('button',{name:'one.pdf',exact:true}).getAttribute('aria-pressed'),'true');
  assert.equal(screen.getByRole('button',{name:'two.png',exact:true}).getAttribute('aria-pressed'),'true');
  assert.equal(writesCount(),writes);
 }
});
test('connection change hides old native dialog and a new source never inherits its draft',async()=>{
 await act(async()=>{atoms.connectionId.set('backend-B');atoms.focusedSessionOwner.set({connectionId:'backend-B',profile:'default'});});await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));
 await act(async()=>attach.data.run({}));await screen.findByRole('dialog');assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'');assert.equal(screen.queryByRole('button',{name:'Remove one.pdf'}),null);
});
test('focused owner profile wins over socket profile, with isolated drafts and captured request scope',async()=>{
 await act(async()=>atoms.focusedSessionOwner.set({connectionId:'backend-B',profile:'named-bot'}));
 await waitFor(()=>assert.equal(screen.queryByRole('dialog'),null));const from=calls.length;
 await act(async()=>attach.data.run());
 await screen.findByRole('form',{name:'Add delivery'});await screen.findByRole('button',{name:'one.pdf',exact:true});
 assert.equal(atoms.profile.get(),'default');assert.equal(screen.getByRole('textbox',{name:'Title'}).value,'');
 assert.ok(calls.length>from);assert.ok(calls.slice(from).every(c=>new URL(c.url,'http://localhost/').searchParams.get('profile')==='named-bot'));
 await click(screen.getByRole('button',{name:'Close',exact:true}));
});
test('explicit Add refuses unavailable owners without crossing source guards',async()=>{
 const from=calls.length,before=notifications.length;
 for(const owner of [null,{connectionId:'backend-A',profile:'named-bot'}]){
  await act(async()=>atoms.focusedSessionOwner.set(owner));
  await act(async()=>attach.data.run());
  assert.equal(screen.queryByRole('dialog'),null);assert.equal(calls.length,from);
 }
 assert.equal(notifications.length,before+2);
 await act(async()=>atoms.focusedSessionOwner.set({connectionId:'backend-B',profile:'named-bot'}));
});
test('fresh owned chat accepts null stored source through an explicit Add gesture',async()=>{
 await act(async()=>atoms.focusedStoredSessionId.set(null));
 const from=calls.length;
 await act(async()=>attach.data.run());
 await screen.findByRole('form',{name:'Add delivery'});await screen.findByRole('combobox',{name:'Conversation'});
 assert.equal(screen.getByRole('combobox',{name:'Conversation'}).textContent,'Choose a conversation');
 assert.ok(!calls.slice(from).some(c=>new URL(c.url,'http://localhost/').pathname.endsWith('/artifacts')));
 await click(screen.getByRole('button',{name:'Close',exact:true}));
 assert.equal(screen.queryByRole('dialog'),null);
});
test('stock middleware leaves unsupported syntax and prose byte-identical as ordinary sends',async()=>{
 cleanup();const sends=[];
 const hook=renderHook(()=>globalThis.__shelfUseMiddlewareSubmit((...args)=>{sends.push(args);return true;}));
 for(const text of ['/shelf add r2','/shelf add these files','/shelf add r1 please','Please /shelf','/shelf-more','/shelf  add','/shelf add\n',' /shelf','/shelf\tadd']){
  const attachments=[{id:'ordinary-file',name:'draft.txt'}],draft={text,attachments};
  assert.equal(await globalThis.__shelfMiddleware(draft),draft);
  assert.equal(await hook.result.current.onSubmit(text,{attachments,storedSessionId:'chat-origin'}),true);
  assert.equal(sends.at(-1)[0],text);assert.equal(sends.at(-1)[1].attachments,attachments);assert.equal(sends.at(-1)[1].storedSessionId,'chat-origin');
 }
 cleanup();
});
test('notification failure cannot leak an exact Shelf command through the host pass-through catch',async()=>{
 const notify=globalThis.__shelfHost.notify;globalThis.__shelfHost.notify=()=>{throw Error('notification unavailable');};
 try{assert.equal(await globalThis.__shelfMiddleware({text:'/shelf'}),null);}
 finally{globalThis.__shelfHost.notify=notify;}
});
test('Saved route starts in the rich library, not Add, and does not register anything on opening',async()=>{
 cleanup();const saved=contributions.find(c=>c.id==='saved-page'),from=calls.length,writes=writesCount();
 render(React.createElement(saved.render));await screen.findByRole('region',{name:'Delivery catalog'});
 assert.equal(screen.queryByRole('form',{name:'Add delivery'}),null);assert.equal(screen.queryByRole('dialog'),null);
 assert.ok(screen.getByRole('button',{name:'Add delivery',exact:true}));assert.equal(writesCount(),writes);
 assert.ok(calls.slice(from).every(c=>new URL(c.url,'http://localhost/').searchParams.get('profile')==='default'));
 cleanup();
});
