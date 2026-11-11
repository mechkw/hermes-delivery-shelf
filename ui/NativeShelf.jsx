import React,{useEffect,useRef,useState} from 'react';
import {Dialog as NativeDialog,DialogContent,DialogHeader,DialogTitle} from '@hermes/plugin-sdk';
import {Button,Input,Textarea,SearchField,Choice,Field as PresentationField,DialogFooter,ErrorState,Loader,EmptyState} from '@saved/presentation';
import {createDraft,editField,invalidateGeneration,beginGeneration} from './metadata-draft.js';
import {metadataFeedback} from './metadata-errors.js';
import {newShelfDraft,toggleSelection,generateMetadata,registerDelivery,updateVersion,downloadFile} from './native-chat-shelf.js';
import styles from './native-chat-shelf.css';
import {NativeLibrary,NativeDeliveryPreview,FileVisual,savedFileUrl} from './NativeLibrary.jsx';
import {defaultSettings} from './NativeSettings.jsx';

const msg=e=>e?.code==='metadata_invalid'?metadataFeedback(e).message:e?.message||'The request failed. Try again.';
const path=id=>encodeURIComponent(id);
function Field(props){return <PresentationField {...props} className="ds-native-field"/>;}
function useChoices(api,url,enabled=true,refresh=0){
 const [query,setQuery]=useState(''),[filters,setFilters]=useState({kind:'',project:'',...(url==='/entries'?{state:'active'}:{})}),[offset,setOffset]=useState(0),[result,setResult]=useState(null),[retry,setRetry]=useState(0);
 const key=JSON.stringify([url,query,filters,offset,retry,refresh]);
 useEffect(()=>{setOffset(0);setQuery('');},[url]);
 useEffect(()=>{let active=true;if(!enabled||!url)return;setResult(null);
  const timer=setTimeout(()=>api(url+(url.includes('?')?'&':'?')+new URLSearchParams({...(url==='/entries'?filters:{}),q:query,offset:String(offset),limit:'30'})).then(data=>{if(active)setResult({key,data});}).catch(error=>{if(active)setResult({key,error:msg(error)});}),150);
  return()=>{active=false;clearTimeout(timer);};
 },[api,key,enabled]);
 return {query,setQuery:q=>{setQuery(q);setOffset(0);},filters,setFilter:(key,value)=>{setFilters(f=>({...f,[key]:value}));setOffset(0);},clear:()=>{setQuery('');setFilters(f=>({kind:'',project:'',...(url==='/entries'?{state:f.state||'active'}:{})}));setOffset(0);},offset,result:result?.key===key?result:null,previous:()=>setOffset(n=>Math.max(0,n-30)),next:()=>setOffset(n=>n+30),retry:()=>setRetry(n=>n+1)};
}
function Pages({choices,noun}) {const data=choices.result?.data,more=data?.has_more??(choices.offset+(data?.items?.length||0)<data?.total);return <div className="ds-native-pages"><Button disabled={!choices.offset||!data} onClick={choices.previous} aria-label={'Previous '+noun}>Previous</Button><Button disabled={!more||!data} onClick={choices.next} aria-label={'Next '+noun}>Next</Button></div>;}
function ChoicesStatus({choices,noun}) {return !choices.result?<Loader label={'Loading '+noun}/>:choices.result.error?<ErrorState title={'Could not load '+noun} description={choices.result.error}><Button onClick={choices.retry}>Retry</Button></ErrorState>:null;}
function FileChooser({api,draft,change,disabled,enabled=true}){
 const sessions=useChoices(api,'/sources/sessions',enabled),files=useChoices(api,draft.session_id?`/sources/sessions/${path(draft.session_id)}/artifacts`:null,enabled);
 const items=sessions.result?.data?.items||[];
 const knownSessions=useRef(new Map());for(const session of items)knownSessions.current.set(session.id,session.title||'Untitled conversation');
 const options=[{value:'',label:'Choose a conversation',disabled:true},...items.map(s=>({value:s.id,label:s.title||'Untitled conversation'}))];
 if(draft.session_id&&!items.some(s=>s.id===draft.session_id))options.push({value:draft.session_id,label:knownSessions.current.get(draft.session_id)||'Current conversation'});
 const pageFiles=files.result?.data?.items||[],additional=pageFiles.filter(f=>!draft.selections.some(s=>s.id===f.id));
 return <section className="ds-native-chooser" aria-label="Delivered files">
  <Field title="Conversation"><Choice value={draft.session_id} options={options} disabled={disabled} onValueChange={session_id=>change(d=>({...d,session_id,selections:[],metadata:invalidateGeneration(d.metadata)}))}/></Field>
  <SearchField aria-label="Find conversation" placeholder="Filter recent conversations…" value={sessions.query} onChange={q=>sessions.setQuery(q.slice(0,200))}/>
  <ChoicesStatus choices={sessions} noun="conversations"/><Pages choices={sessions} noun="conversations"/>
  {draft.session_id&&<><SearchField aria-label="Find delivered file" placeholder="Find delivered files…" value={files.query} onChange={q=>files.setQuery(q.slice(0,200))}/>
   <ChoicesStatus choices={files} noun="files"/>
   <div className="ds-native-selection-toolbar"><span aria-live="polite">{draft.selections.length} {draft.selections.length===1?'file':'files'} selected</span><Button disabled={disabled||!pageFiles.length||draft.selections.length+additional.length>32} onClick={()=>change(d=>({...d,selections:[...d.selections,...pageFiles.filter(f=>!d.selections.some(s=>s.id===f.id))],metadata:invalidateGeneration(d.metadata)}))}>Select all files on this page</Button><Button disabled={disabled||!draft.selections.length} onClick={()=>change(d=>({...d,selections:[],metadata:invalidateGeneration(d.metadata)}))}>Clear selection</Button></div>
   <p className="ds-native-muted">Up to 32 files per delivery. Selection is kept when you change pages.</p>
   <div className="ds-native-files">{pageFiles.map(file=><Button key={file.id} className="ds-native-file-choice" variant="secondary" disabled={disabled||(!draft.selections.some(s=>s.id===file.id)&&draft.selections.length>=32)} aria-label={file.name} aria-pressed={draft.selections.some(s=>s.id===file.id)} onClick={()=>change(d=>({...d,selections:toggleSelection(d.selections,file),metadata:invalidateGeneration(d.metadata)}))}><FileVisual api={api} source={file} sessionId={draft.session_id}/><strong>{file.name}</strong><span aria-hidden="true">{draft.selections.some(s=>s.id===file.id)?'Selected':'Select'}</span></Button>)}</div>
   {files.result?.data&&!files.result.data.items.length&&<EmptyState title="No delivered files"/>}<Pages choices={files} noun="files"/>
  </>}
  {draft.selections.length>0&&<div className="ds-native-selection" aria-label="Selected files">{draft.selections.map(file=><div key={file.id}><span>{file.name}</span><Button disabled={disabled} aria-label={'Remove '+file.name} onClick={()=>change(d=>({...d,selections:d.selections.filter(s=>s.id!==file.id),metadata:invalidateGeneration(d.metadata)}))}>Remove</Button></div>)}</div>}
 </section>;
}
function MetadataFields({draft,change,disabled}) {
 const values=draft.metadata.values;
 const edit=(key,value)=>change(d=>({...d,metadata:editField(d.metadata,key,value)}));
 return <>
  <Field title="Title"><Input value={values.title} disabled={disabled} onChange={e=>edit('title',e.target.value)}/></Field>
  <Field title="Description"><Textarea rows={3} value={values.description} disabled={disabled} onChange={e=>edit('description',e.target.value)}/></Field>
  <Field title="Tags"><Input value={draft.pendingTag||''} disabled={disabled} placeholder="Add a tag" onChange={e=>change(d=>({...d,pendingTag:e.target.value,metadata:invalidateGeneration(d.metadata)}))} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();if(draft.pendingTag?.length)change(d=>({...d,pendingTag:'',metadata:editField(d.metadata,'tags',[...d.metadata.values.tags,d.pendingTag])}));}}}/></Field>
  <div className="ds-native-tags">{values.tags.map((tag,index)=><div key={index}><Input aria-label={'Tag '+(index+1)} value={tag} disabled={disabled} onChange={e=>edit('tags',values.tags.map((t,i)=>i===index?e.target.value:t))}/><Button disabled={disabled} aria-label={'Remove tag '+(index+1)} onClick={()=>edit('tags',values.tags.filter((_,i)=>i!==index))}>Remove</Button></div>)}<Button disabled={disabled||!draft.pendingTag?.length} onClick={()=>change(d=>({...d,pendingTag:'',metadata:editField(d.metadata,'tags',[...d.metadata.values.tags,d.pendingTag])}))}>Add tag</Button></div>
  <Field title="Kind"><Choice value={draft.kind} disabled={disabled} options={['document','image','report','code','other'].map(value=>({value,label:value}))} onValueChange={kind=>change(d=>({...d,kind}))}/></Field>
  <Field title="Project"><Input value={draft.project} disabled={disabled} onChange={e=>change(d=>({...d,project:e.target.value}))}/></Field>
 </>;
}
const withPendingTag=d=>d.pendingTag?.length?{...d,pendingTag:'',metadata:editField(d.metadata,'tags',[...d.metadata.values.tags,d.pendingTag])}:d;

/** Shared native catalog/editor. Retained outside DialogContent so dismissing a
 * Radix portal never destroys form drafts, selected files, or generation state. */
export function NativeShelf({api,ownerKey,sessionId='',open=true,onClose,retained,modal=true,initialView='library'}){
 const fallbackStash=useRef(new Map());const stash=retained||fallbackStash.current;
 const addTrigger=useRef(null);
 const [draft,setDraft]=useState(()=>{const held=stash.get(ownerKey);return held?{...held,metadata:invalidateGeneration(held.metadata)}:newShelfDraft(ownerKey,sessionId);});

 const draftRef=useRef(draft);draftRef.current=draft;
 const change=update=>setDraft(current=>{const next=typeof update==='function'?update(current):update;draftRef.current=next;stash.set(ownerKey,next);return next;});
 const [tab,setTab]=useState(initialView==='add'?'add':'library'),[selected,setSelected]=useState(null),[editing,setEditing]=useState(false),[versioning,setVersioning]=useState(false);
 const [editDraft,setEditDraft]=useState(null);
 const [previewSelection,setPreviewSelection]=useState(null);
 const [settings,setSettings]=useState(null);
 const [busy,setBusy]=useState(false),[generating,setGenerating]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const working=useRef(false),alive=useRef(true),settingsLoaded=useRef(false);
 const catalog=useChoices(api,'/entries',open,refresh);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{if(!open||settingsLoaded.current)return;let active=true;
  api('/settings').then(s=>{if(active){settingsLoaded.current=true;setSettings({...defaultSettings,...s});if(!stash.has(ownerKey))change(d=>({...d,previous_exchanges:s.context_messages||10}));}}).catch(e=>{if(active){setSettings(defaultSettings);setError('Could not load Shelf preferences. Using temporary defaults. '+msg(e));}});return()=>{active=false;};
 },[api,open]);
 async function action(fn){if(working.current)return;working.current=true;setBusy(true);setError('');try{await fn();}catch(e){if(alive.current)setError(msg(e));}finally{working.current=false;if(alive.current)setBusy(false);}}
 async function save(){await action(async()=>{const saved=await registerDelivery(api,withPendingTag(draftRef.current));if(!alive.current)return;setSelected(saved);setEditing(false);setTab('shelf');setRefresh(n=>n+1);});}
 async function generate(){
  if(working.current||generating||!draftRef.current.selections.length)return;
  working.current=true;setGenerating(true);setError('');
  // Pending tag text is ordinary user input too, even before pressing Add tag.
  const current=withPendingTag(draftRef.current);change(current);
  try{await generateMetadata(api,current,change);}catch(e){if(alive.current)setError(msg(e));}
  finally{working.current=false;if(alive.current)setGenerating(false);}
 }
 async function openEntry(item,record){await action(async()=>{const entry=await api(`/entries/${path(item.id)}`);if(alive.current){setSelected(entry);setPreviewSelection(record?{version:record.version?.id,file:record.file.id}:null);setEditing(false);setVersioning(false);}});}
 async function saveMetadata(){await action(async()=>{const d=withPendingTag(editDraft);await api(`/entries/${path(selected.id)}`,{method:'PUT',body:{...d.metadata.values,kind:d.kind,project:d.project,revision:selected.revision,file:selected.file,files:selected.files,session_id:selected.session_id}});const entry=await api(`/entries/${path(selected.id)}`);if(alive.current){setSelected(entry);setEditing(false);setRefresh(n=>n+1);}});}
 function editMetadata(){setEditDraft({...draft,metadata:createDraft(ownerKey,'entry:'+selected.id,{title:selected.title,description:selected.description,tags:selected.tags},{title:'user',description:'user',tags:'user'}),pendingTag:'',kind:selected.kind,project:selected.project});setEditing(true);}
 const dismiss=()=>{onClose?.();};
 const title=tab==='add'?'Add delivery':selected?selected.title:'Deliverables';
 const content=<div className="ds-native-shelf"><style>{styles}</style>
  {tab==='add'&&<header className="ds-native-add-heading"><p>Choose the work you want to keep. Your draft stays here until you save.</p><Button onClick={()=>{setTab('library');setSelected(null);}}>Back to library</Button></header>}
  {error&&<div role="alert">{error}<Button onClick={()=>setError('')}>Dismiss error</Button></div>}
  <div>
  {tab==='add'?<form noValidate aria-label="Add delivery" onSubmit={e=>{e.preventDefault();if(!generating)void save();}}>
   <FileChooser api={api} draft={draft} change={change} disabled={busy} enabled={open}/>
   <MetadataFields draft={draft} change={change} disabled={busy}/>
   <Field title="Previous exchanges"><Choice value={String(draft.previous_exchanges)} disabled={busy||generating} options={[5,10,20,50].map(n=>({value:String(n),label:String(n)}))} onValueChange={value=>{change(d=>({...d,previous_exchanges:Number(value),metadata:invalidateGeneration(d.metadata)}));void action(async()=>{await api('/generation/settings',{method:'PUT',body:{previous_exchanges:Number(value)}});});}}/></Field>
   <DialogFooter><Button disabled={busy||generating||!draft.selections.length||!beginGeneration(draft.metadata).capture} onClick={generate}>{generating?'Generating…':'Generate'}</Button><Button type="submit" variant="default" disabled={busy||generating}>{busy?'Saving…':'Save'}</Button></DialogFooter>
  </form>:selected?<section aria-label="Delivery details" className="ds-native-detail"><Button onClick={()=>{setSelected(null);setEditing(false);setVersioning(false);}}>Back to shelf</Button>
   {editing?<form noValidate aria-label="Edit delivery" onSubmit={e=>{e.preventDefault();void saveMetadata();}}><MetadataFields draft={editDraft} change={setEditDraft} disabled={busy}/><DialogFooter><Button onClick={()=>setEditing(false)}>Cancel</Button><Button type="submit" variant="default" disabled={busy}>Save changes</Button></DialogFooter></form>:<><h2>{selected.title}</h2><p className="ds-native-description">{selected.description}</p><p>{selected.tags?.join(' · ')}</p><Button disabled={busy} onClick={editMetadata}>Edit metadata</Button></>}
   {!editing&&<><NativeDeliveryPreview key={selected.id+':'+selected.revision} api={api} entry={selected} busy={busy} settings={settings||defaultSettings} initialVersion={previewSelection?.version} initialFile={previewSelection?.file}/><h3>Versions</h3>{(selected.versions||[]).map(version=><section key={version.id} className="ds-native-version" aria-label={'Version '+version.number}><h4>Version {version.number}{selected.current_version===version.id?' · Current':''}</h4>{version.files.map(file=><div key={file.id}><span>{file.name}</span><Button disabled={busy} aria-label={`Download ${file.name}, version ${version.number}`} onClick={()=>action(async()=>downloadFile(await api(`/entries/${path(selected.id)}/versions/${path(version.id)}/files/${path(file.id)}`)))}>Download</Button></div>)}</section>)}
    {!selected.versions?.length&&selected.file&&<Button disabled={busy} onClick={()=>action(async()=>downloadFile(await api(`/entries/${path(selected.id)}/file`)))}>Download file</Button>}
    <Button disabled={busy} onClick={()=>setVersioning(v=>!v)}>{versioning?'Cancel update':'Add version'}</Button>
    {versioning&&<section aria-label="Update delivery"><FileChooser api={api} draft={draft} change={change} disabled={busy} enabled={open}/><DialogFooter><Button variant="default" disabled={busy} onClick={()=>action(async()=>{const entry=await updateVersion(api,selected,draftRef.current.selections,draftRef.current.session_id);if(alive.current){setSelected(entry);setVersioning(false);setRefresh(n=>n+1);}})}>Save new version</Button></DialogFooter></section>}
   </>}
  </section>:settings?<NativeLibrary api={api} settings={settings} catalog={{...catalog,addRef:addTrigger,add:()=>{setTab('add');setError('');}}} busy={busy} open={openEntry} download={record=>action(async()=>downloadFile(await api(savedFileUrl(record))))} pages={<Pages choices={catalog} noun="deliveries"/>} status={<ChoicesStatus choices={catalog} noun="deliveries"/>}/>:<Loader label="Loading Shelf preferences"/>}</div>
 </div>;
 if(!modal&&tab!=='add')return content;
 if(!modal)return <NativeDialog open={open} onOpenChange={value=>{if(!value)setTab('library');}}><DialogContent className="ds-native-dialog" bodyClassName="ds-native-dialog-body" aria-describedby={undefined} onCloseAutoFocus={event=>{if(addTrigger.current?.isConnected){event.preventDefault();addTrigger.current.focus();}}}><DialogHeader><DialogTitle>Add delivery</DialogTitle></DialogHeader>{content}</DialogContent></NativeDialog>;
 return <NativeDialog open={open} onOpenChange={value=>{if(!value)dismiss();}}><DialogContent className="ds-native-dialog" bodyClassName="ds-native-dialog-body" aria-describedby={undefined}><DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>{content}</DialogContent></NativeDialog>;
}
