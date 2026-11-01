import React,{useEffect,useState,useId,useRef} from 'react';
import {Button,Input,Textarea,SearchField,Choice,Field,Dialog,DialogFooter,EmptyState,ErrorState,Loader,Hint} from '@saved/presentation';
const PRESETS=['5','10','20','50'];
const kinds=['document','image','report','code','other'];
const fresh=()=>({title:'',description:'',kind:'document',project:'',tags:[],file:null,session_id:''});
function SourcePicker({api,path,label,value,onChange,artifacts=false,disabled}){
 const [query,setQuery]=useState(''),[offset,setOffset]=useState(0),[retry,setRetry]=useState(0),[result,setResult]=useState(null);
 const id=useId(),key=JSON.stringify([path,query,offset,retry]);
 useEffect(()=>{let active=true;if(!path)return;const timer=setTimeout(async()=>{
  try{const data=await api(path+'?'+new URLSearchParams({q:query,limit:'30',offset:String(offset)}));if(active)setResult({key,data});}
  catch(e){if(active)setResult({key,error:e?.message||'Could not load choices.'});}
 },180);return()=>{active=false;clearTimeout(timer);};},[api,key,path,query,offset]);
 const current=result?.key===key?result:null,items=current?.data?.items||[],loading=Boolean(path&&!current),noun=artifacts?'files':'conversations';
 const options=items.map(item=>({value:item.id,label:artifacts?`${item.name} · ${item.type}`:`${item.title?.includes(item.id)?'Untitled conversation':item.title} · ${item.updated_at?new Date(item.updated_at*1000).toLocaleDateString():'Date unavailable'}`}));
 if(value&&!options.some(o=>o.value===value))options.unshift({value,label:'Selected '+(artifacts?'file':'conversation')+' (outside these results)'});
 options.unshift({value:'',label,disabled:true});
 const window=current?.data?.window;
 const help=artifacts?`Search covers files explicitly delivered in up to ${window?.limit||500} responses in this conversation. ${window?.truncated?'Older responses are outside this window.':''} Unavailable or unapproved files are omitted.`:`Search covers the most recent ${window?.limit||1000} conversations. ${window?.truncated?'Older conversations are outside this window.':''}`;
 return <section className="hs-source-picker" aria-label={label+' choices'}><label htmlFor={id}>{label}</label>
  <Choice id={id} aria-label={label} disabled={disabled||!path} value={value||''} options={options} onValueChange={v=>onChange(v,items.find(i=>i.id===v))}/>
  {path&&<><SearchField aria-label={'Search '+noun} placeholder={'Find '+(artifacts?'a file…':'a conversation…')} value={query} onChange={v=>{setQuery(v.slice(0,200));setOffset(0);}} onKeyDown={e=>{if(e.key==='Enter')e.preventDefault();}}/>
  {loading?<Loader label={'Loading '+noun}/>:current?.error?<ErrorState title="Could not load choices" description={current.error}><Button onClick={()=>setRetry(n=>n+1)}>Retry {noun}</Button></ErrorState>:!items.length?<EmptyState title={query?'No matches':artifacts?'No available files':'No conversations'} description={artifacts?'Choose another conversation or add metadata manually.':'Try another search.'}/>:null}
  <nav className="hs-source-pages" aria-label={label+' pages'}>{[['Previous',offset===0,()=>setOffset(n=>Math.max(0,n-30))],['Next',!current?.data?.has_more,()=>setOffset(n=>n+30)]].map(([text,off,action])=><Hint key={text} label={help} disabled={disabled||loading||off} name={text+' '+noun}><Button aria-label={text+' '+noun} disabled={disabled||loading||off} onClick={action}>{text}</Button></Hint>)}</nav></>}
 </section>;
}
export function ShelfEditor({api,entry,roots,busy,error,save,close,restoreFocus}){
 const [draft,setDraft]=useState(entry||fresh),[tags,setTags]=useState((entry?.tags||[]).join('\n'));
 const [selected,setSelected]=useState(null),[manual,setManual]=useState(Boolean(entry));
 const [root,setRoot]=useState(entry?.file?.root||roots[0]||''),[path,setPath]=useState(entry?.file?.path||'');
 const [previous,setPrevious]=useState('10'),[ready,setReady]=useState(false),[settingsError,setSettingsError]=useState(''),[retry,setRetry]=useState(0);
 const [settingsBusy,setSettingsBusy]=useState(false);
 const [generating,setGenerating]=useState(false),[generationError,setGenerationError]=useState(''),[notice,setNotice]=useState('');
 const life=useRef(0),edits=useRef(0),working=useRef(false),settingVersion=useRef(0);
 useEffect(()=>{const token=++life.current;if(!entry)api('/generation/settings').then(s=>{if(life.current===token){setPrevious(PRESETS.includes(String(s.previous_exchanges))?String(s.previous_exchanges):'10');setReady(true);setSettingsError('');}}).catch(e=>{if(life.current===token)setSettingsError(e.message);});return()=>{life.current++;edits.current++;};},[api,entry,retry]);
 const invalidate=()=>{edits.current++;setNotice('');setGenerationError('');};
 const change=(k,v)=>{invalidate();setDraft(d=>({...d,[k]:v}));};
 async function persistPrevious(value){
  const token=life.current,version=++settingVersion.current;setSettingsBusy(true);setSettingsError('');
  try{await api('/generation/settings',{method:'PUT',body:{previous_exchanges:Number(value)}});}
  catch(e){if(token===life.current&&version===settingVersion.current)setSettingsError(e?.message||'Could not save context setting.');}
  finally{if(token===life.current&&version===settingVersion.current)setSettingsBusy(false);}
 }
 async function generate(){
  if(working.current||busy||!selected||!ready||settingsBusy||settingsError)return;
  working.current=true;setGenerating(true);setGenerationError('');setNotice('');
  const token=life.current,version=edits.current,current=()=>life.current===token&&edits.current===version;
  try{
   const result=await api('/generation/draft',{method:'POST',body:{session_id:draft.session_id,source:selected.source,previous_exchanges:Number(previous)}});
   if(life.current!==token)return;
   if(!current()){setNotice('Draft changed during generation. Your edits were kept.');return;}
   setDraft(d=>({...d,...result.draft}));setTags(result.draft.tags.join('\n'));
   setNotice(`Draft ready to review. ${result.context.content_mode.startsWith('history-only')?'History only; file content was not read.':result.context.content_mode==='image'?'Image and associated history used.':'File text and associated history used.'}${result.context.truncated||result.context.file_truncated?' Content shortened.':''}`);
  }catch(e){if(current())setGenerationError(e?.message||'Could not generate details. Retry or save manually.');}
  finally{working.current=false;if(life.current===token)setGenerating(false);}
 }
 const blocked=busy||generating||!selected||!ready||settingsBusy||Boolean(settingsError);
 return <Dialog restoreFocus={restoreFocus} description={null} title={entry?'Edit delivery':'Add a delivery'} busy={busy} close={close}>
 <form onSubmit={e=>{e.preventDefault();if(busy||!draft.title.trim()||(!manual&&!selected))return;invalidate();save({...draft,tags:tags.split('\n').map(t=>t.trim()).filter(Boolean),file:manual?(path.trim()?{root,path:path.trim()}:null):selected.file,source:manual?undefined:selected.source});}}>
 <fieldset disabled={busy} className="hs-form-fields">
 {!entry&&<><SourcePicker api={api} path={manual?null:'/sources/sessions'} label="Choose a conversation" value={draft.session_id} disabled={manual||busy} onChange={value=>{invalidate();setSelected(null);setDraft(d=>({...d,session_id:value,file:null}));}}/>
 {!manual&&<SourcePicker key={draft.session_id} api={api} path={draft.session_id?`/sources/sessions/${encodeURIComponent(draft.session_id)}/artifacts`:null} label="Choose a file" artifacts value={selected?.id} disabled={busy} onChange={(value,item)=>{invalidate();setSelected(item);setDraft(d=>({...d,file:item?.file||null,title:item?.name||d.title,kind:item?.content_mode==='image'?'image':'document'}));}}/>}
 {!manual&&<section aria-label="Generate delivery details"><div className="hs-generation-row"><Hint label={!selected?'Choose a file first.':!ready?'Load the context setting first.':'Send this selected file and preceding conversation context to your configured model. Image generation needs a vision-capable model. PDF and ZIP use history only.'} disabled={blocked} name="Generate details help"><Button variant="default" loading={generating} disabled={blocked} onClick={generate}>Generate details</Button></Hint><div className="hs-generation-context"><label>Context</label><Choice aria-label="Context" value={previous} disabled={!ready||generating||settingsBusy} options={PRESETS.map(value=>({value,label:value}))} onValueChange={value=>{invalidate();setPrevious(value);void persistPrevious(value);}}/></div></div>
 {selected?.content_mode==='history-only'&&<small>History only — this file format is not read.</small>}
 {settingsError&&<ErrorState title="Context unavailable" description={settingsError}><Button onClick={()=>ready?persistPrevious(previous):setRetry(n=>n+1)}>Retry context</Button></ErrorState>}
 {generating&&<p role="status">Generating details… You can keep editing.</p>}{generationError&&<ErrorState title="Could not generate details" description={generationError}/ >}{notice&&<p role="status">{notice}</p>}
 </section>}</>}
 <Field title="Title"><Input required maxLength={160} value={draft.title} onChange={e=>change('title',e.target.value)}/></Field>
 <Field title="Description"><Textarea rows={3} maxLength={4000} value={draft.description} onChange={e=>change('description',e.target.value)}/></Field>
 <Field title="Tags" description="One per line"><Textarea aria-label="Tags (one per line)" rows={2} maxLength={820} value={tags} onChange={e=>{invalidate();setTags(e.target.value);}}/></Field>
 <details className="ds-advanced"><summary>More options</summary><Field title="Kind"><Choice value={draft.kind} onChange={e=>change('kind',e.target.value)}>{kinds.map(k=><option key={k}>{k}</option>)}</Choice></Field><Field title="Project"><Input maxLength={100} value={draft.project} onChange={e=>change('project',e.target.value)}/></Field>
 {!entry&&<Button onClick={()=>{invalidate();setManual(v=>!v);setSelected(null);}}>{manual?'Choose from a conversation':'Add metadata manually'}</Button>}
 {manual&&<><Field title="Session reference"><Input value={draft.session_id||''} onChange={e=>change('session_id',e.target.value)} maxLength={160}/></Field><Field title="Approved root"><Choice value={root} onChange={e=>{invalidate();setRoot(e.target.value);}}>{roots.map(r=><option key={r}>{r}</option>)}</Choice></Field><Field title="Relative file path"><Input value={path} onChange={e=>{invalidate();setPath(e.target.value);}} maxLength={1024}/></Field><small>Leave the file path empty for metadata only.</small></>}
 </details></fieldset>
 {error&&<ErrorState title="Could not save delivery" description={error}/>}
 <DialogFooter><Button disabled={busy} onClick={close}>Cancel</Button><Button variant="default" type="submit" loading={busy} disabled={busy||!draft.title.trim()||(!manual&&!selected)}>{entry?'Save changes':'Save delivery'}</Button></DialogFooter>
 </form></Dialog>;
}
