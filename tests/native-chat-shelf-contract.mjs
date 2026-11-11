import {test} from 'node:test';
import assert from 'node:assert/strict';
import {editField} from '../ui/metadata-draft.js';
import {newShelfDraft,generateMetadata,registerDelivery,updateVersion,createShelfApi,scopeKey,toggleSelection} from '../ui/native-chat-shelf.js';
const files=[{id:'one',name:'one.pdf',file:{root:'workspace',path:'one.pdf'},source:{session_id:'chat-A',message_id:'message-A'}},{id:'two',name:'two.png',file:{root:'workspace',path:'two.png'},source:{session_id:'chat-A',message_id:'message-B'}}];

test('register-many keeps exact metadata and one/several sources; always reads saved entry back',async()=>{
 for(const selections of [[files[0]],files]){
  let draft=newShelfDraft('owner','chat-A');draft={...draft,selections,metadata:editField(draft.metadata,'title','  Exact Title  ')};
  const calls=[];const api=async(url,options)=>{calls.push({url,options});return url==='/sources/register-many'?{id:'entry-A'}:{id:'entry-A',revision:1};};
  await registerDelivery(api,draft);
  assert.equal(calls[0].url,'/sources/register-many');assert.deepEqual(calls[0].options.body.selections,selections.map(({file,source})=>({file,source})));
  assert.equal(calls[0].options.body.title,'  Exact Title  ');assert.equal(calls[0].options.body.session_id,'chat-A');assert.equal(calls[1].url,'/entries/entry-A');
 }
});
test('blank title reaches server; server errors leave draft and selections untouched',async()=>{
 const draft={...newShelfDraft('owner','chat-A'),selections:files};let seen;
 await assert.rejects(registerDelivery(async(url,options)=>{seen=options.body;throw Error('server validation');},draft),/server validation/);
 assert.equal(seen.title,'');assert.equal(draft.selections.length,2);
});
test('real generation endpoint gets requested/supplied fields; typed bytes survive',async()=>{
 let draft={...newShelfDraft('owner','chat-A'),selections:files};draft.metadata=editField(draft.metadata,'title','  USER TITLE 🧭  ');draft.metadata=editField(draft.metadata,'tags',['User Tag','e\u0301']);
 let request;await generateMetadata(async(url,options)=>{assert.equal(url,'/generation/draft');request=options.body;return {draft:{title:'ignore',tags:['ignore'],description:'Generated description'},context:{}};},draft,update=>{draft=update(draft);});
 assert.deepEqual(request.requested_fields,['description']);assert.deepEqual(request.supplied_metadata,{tags:['User Tag','e\u0301'],title:'  USER TITLE 🧭  '});
 assert.equal(request.previous_exchanges,10);assert.deepEqual(request.source,files[0].source);assert.equal(draft.metadata.values.title,'  USER TITLE 🧭  ');assert.equal(draft.metadata.values.description,'Generated description');assert.deepEqual(draft.metadata.values.tags,['User Tag','e\u0301']);
});
test('edits during generation fence late output, and failure unlocks manual save',async()=>{
 let draft={...newShelfDraft('owner','chat-A'),selections:files};let release;
 const task=generateMetadata(()=>new Promise(resolve=>{release=resolve;}),draft,update=>{draft=update(draft);});
 draft={...draft,metadata:editField(draft.metadata,'description','Typed while generating')};release({draft:{title:'late',description:'late',tags:['late']}});await task;
 assert.equal(draft.metadata.values.description,'Typed while generating');assert.equal(draft.metadata.values.title,'');assert.equal(draft.metadata.pending,null);
 await assert.rejects(generateMetadata(async()=>{throw Error('model unavailable');},draft,update=>{draft=update(draft);}),/model unavailable/);assert.equal(draft.metadata.pending,null);
});
test('versions update only on explicit call and use revision plus FileRefs, followed by readback',async()=>{
 const calls=[];const api=async(url,options)=>{calls.push({url,options});return {id:'entry-A',revision:2,versions:[]};};
 await updateVersion(api,{id:'entry-A',revision:1},files);
 assert.deepEqual(calls[0],{url:'/entries/entry-A/versions',options:{method:'POST',body:{revision:1,files:files.map(s=>s.file)}}});assert.equal(calls[1].url,'/entries/entry-A');
});
test('version updates preserve each selected message origin and the explicitly chosen conversation',async()=>{
 const calls=[],source={message_id:17,digest:'a'.repeat(64),artifact_id:'b'.repeat(64)},selection={...files[0],source};
 await updateVersion(async(url,options)=>{calls.push({url,options});return {id:'entry-A'};},{id:'entry-A',revision:2},[selection],'chosen-chat');
 assert.deepEqual(calls[0].options.body,{revision:2,files:[selection.file],session_id:'chosen-chat',sources:[{file:selection.file,source,session_id:'chosen-chat'}]});
});
test('transport fences source connection and carries the captured profile, never current profile defaults',async()=>{
 let connection='backend-A',listener;const host={state:{connectionId:{get:()=>connection,listen:fn=>{listener=fn;return()=>{};}}}};const calls=[];let release;
 const ctx={onDispose(){},rest:(url,options)=>{calls.push({url,options});return new Promise(resolve=>{release=resolve;});}};
 const api=createShelfApi(ctx,host,{connectionId:'backend-A',profile:'named-bot'});
 const pending=api('/entries?limit=30');assert.equal(calls[0].url,'/entries?limit=30&profile=named-bot');connection='backend-B';listener(connection);release({items:[]});await assert.rejects(pending,/Connection changed/);connection='backend-A';listener(connection);await assert.rejects(api('/entries'),/Connection changed/);assert.equal(calls.length,1);
 assert.notEqual(scopeKey({connectionId:'backend-A',profile:'p',sessionId:'s'}),scopeKey({connectionId:'backend-B',profile:'p',sessionId:'s'}));
});
test('selection toggles retain full source proof and stable order',()=>{let selection=toggleSelection([],files[0]);selection=toggleSelection(selection,files[1]);assert.deepEqual(selection,files);assert.deepEqual(toggleSelection(selection,files[0]),[files[1]]);});
