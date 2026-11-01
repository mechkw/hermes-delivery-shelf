import React, {useEffect, useRef, useState, useId} from 'react';
import styles from './style.css';
import {ShelfEditor} from './ShelfEditor.jsx';
import {ArtifactCard} from './ArtifactCard.jsx';
import {useCollectionFocus} from './collection-focus.js';
import {Button,Input,Textarea,SearchField,Choice,Field,Dialog,DialogFooter,EmptyState,ErrorState,Loader} from '@saved/presentation';

const kinds = ['document', 'image', 'report', 'code', 'other'];
const fresh = () => ({title:'',description:'',kind:'document',project:'',tags:[],file:null,session_id:''});
const message = error => typeof error?.message === 'string' ? error.message : 'The request failed. Try again.';

export function Shelf({api,embedded=false}) {
  const [status,setStatus]=useState(null), [data,setData]=useState({items:[],total:0}), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [filters,setFilters]=useState({q:'',tag:'',kind:'',project:''}), [offset,setOffset]=useState(0), [refresh,setRefresh]=useState(0);
  const [editor,setEditor]=useState(undefined), [selected,setSelected]=useState(null), [removing,setRemoving]=useState(null);
  const [busy,setBusy]=useState(false), [actionError,setActionError]=useState(''), [notice,setNotice]=useState(''), [preview,setPreview]=useState(null);
 const focus=useCollectionFocus(editor!==undefined||Boolean(selected||removing));
  const alive=useRef(false), serial=useRef(0), fileSerial=useRef(0);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;serial.current++;fileSerial.current++;};},[]);
  useEffect(()=>{
    const ticket=++serial.current; setLoading(true); setError('');
    const timer=setTimeout(async()=>{
      try {
        const [s,d]=await Promise.all([api('/status'),api('/entries?'+new URLSearchParams({...filters,offset:String(offset),limit:'30'}))]);
        if(alive.current && ticket===serial.current){setStatus(s);setData(d);}
      } catch(e){if(alive.current && ticket===serial.current){setError(message(e));setData({items:[],total:0});}}
      finally{if(alive.current && ticket===serial.current)setLoading(false);}
    },180);
    return()=>{clearTimeout(timer);};
  },[api,filters,offset,refresh]);
  const filter=(key,value)=>{setFilters(f=>({...f,[key]:value}));setOffset(0);};
  const close=()=>{setEditor(undefined);setSelected(null);setRemoving(null);setActionError('');setPreview(null);fileSerial.current++;};
  async function save(draft){
    if(busy)return;setBusy(true);setActionError('');
    try{
      const payload=Object.fromEntries(['title','description','kind','project','tags','file','session_id'].map(k=>[k,draft[k]]));
      if(editor)payload.revision=editor.revision;
      if(!editor&&draft.source)payload.source=draft.source;
      const saved=await api(editor?`/entries/${editor.id}`:draft.source?'/sources/register':'/entries',{method:editor?'PUT':'POST',body:payload});
      if(!alive.current)return;
      // Read back via the same fenced transport; never a newly-selected host.
      await api(`/entries/${saved.id}`);
      if(!alive.current)return;
      close();setNotice(editor?'Changes saved.':'Delivery added.');setRefresh(n=>n+1);
    }catch(e){if(alive.current)setActionError(message(e));}
    finally{if(alive.current)setBusy(false);}
  }
  async function remove(){
    if(busy)return;setBusy(true);setActionError('');
    try{
      await api(`/entries/${removing.id}?revision=${removing.revision}`,{method:'DELETE'});
      if(!alive.current)return;
      close();setNotice('Delivery removed from the shelf. No files were deleted.');setRefresh(n=>n+1);setOffset(0);
    }catch(e){if(alive.current)setActionError(message(e));}
    finally{if(alive.current)setBusy(false);}
  }
  async function readFile(item,asPreview){
    const ticket=++fileSerial.current;setBusy(true);setActionError('');setPreview(null);
    try{
      const file=await api(`/entries/${item.id}/file${asPreview?'?preview=true':''}`);
      if(!alive.current || ticket!==fileSerial.current)return;
      if(asPreview)setPreview(file);
      else{
        const bytes=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));
        const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
        const a=document.createElement('a');a.href=url;a.download=file.name;a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);setNotice('Download requested.');
      }
    }catch(e){if(alive.current && ticket===fileSerial.current)setActionError(message(e));}
    finally{if(alive.current)setBusy(false);}
  }
  return <section ref={focus.ref} onClickCapture={focus.capture} className={"ds ds-shelf"+(api.desktop?" ds-desktop-gallery":"")}>
    <style>{styles}</style>
    <header className="ds-header"><div><p className="ds-muted">{status?.profile||'Your profile'}</p><h2>Deliverables</h2><p className="ds-subtitle">Files and finished work you chose to keep.</p></div>
      <Button data-dialog-trigger data-collection-fallback variant="default" disabled={!status||busy} onClick={()=>{close();setEditor(null);}}>Add delivery</Button></header>
    <section aria-label="Filter deliveries" className="ds-filters">
      <Field className="ds-search">Search<SearchField aria-label="Search deliveries" placeholder="Find a title or description…" value={filters.q} onChange={value=>filter('q',value.slice(0,200))}/></Field>
      <Field>Kind<Choice value={filters.kind} onChange={e=>filter('kind',e.target.value)}><option value="">All kinds</option>{kinds.map(k=><option key={k}>{k}</option>)}</Choice></Field>
      <Field>Project<Input placeholder="Exact project" maxLength={100} value={filters.project} onChange={e=>filter('project',e.target.value)}/></Field>
      <Field>Tag<Input placeholder="Exact tag" maxLength={40} value={filters.tag} onChange={e=>filter('tag',e.target.value)}/></Field>
    </section>
    <div className="ds-toolbar"><span aria-live="polite">{loading?'Loading your shelf…':`${data.total} ${data.total===1?'delivery':'deliveries'}`}</span><div><Button onClick={()=>{setFilters({q:'',tag:'',kind:'',project:''});setOffset(0);}}>Clear filters</Button><Button onClick={()=>setRefresh(n=>n+1)}>Refresh</Button></div></div>
    {notice && <p role="status" className="ds-notice">{notice}</p>}{actionError&&!selected&&editor===undefined&&<ErrorState title="Action failed" description={actionError}/>}
    {error ? <ErrorState title="Could not open your shelf" description={error}><Button onClick={()=>setRefresh(n=>n+1)}>Try again</Button></ErrorState>:
      loading ? <Loader label="Loading deliveries"/>:
      !data.items.length ? <section className="ds-empty"><EmptyState title={Object.values(filters).some(Boolean)?'No matching deliveries':'Keep finished work'} description={Object.values(filters).some(Boolean)?'Try another search or clear the filters.':'Add a report, design, document or other deliverable. Nothing is collected automatically.'}/>{!Object.values(filters).some(Boolean)&&<Button data-dialog-trigger variant="default" onClick={()=>setEditor(null)}>Add your first delivery</Button>}</section>:
      <section className="ds-grid" aria-label="Deliveries">{data.items.map(item=>api.desktop?<ArtifactCard key={item.id} api={api} item={item} busy={busy} open={item=>{close();setSelected(item);}} download={item=>readFile(item,false)} tag={t=>filter('tag',t)}/>:<article key={item.id} className="ds-card" data-kind={item.kind}>
        <div className="ds-card-top"><span className="ds-kind">{item.kind}</span><span className="ds-muted">{item.file?'File attached':'No attachment'}</span></div>
        <h2><Button data-dialog-trigger className="ds-card-title" variant="text" disabled={busy} onClick={()=>{close();setSelected(item);}}><span>{item.title}</span></Button></h2><p className="ds-description">{item.description||'No description added.'}</p>
        <div className="ds-tags">{item.tags.map(t=><Button variant="chip" key={t} onClick={()=>filter('tag',t)} aria-label={`Filter tag ${t}`}>#{t}</Button>)}</div>
        <footer><span>{item.project||'No project'}</span><time dateTime={new Date(item.updated*1000).toISOString()}>{new Date(item.updated*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})}</time></footer>
      </article>)}</section>}
    {!loading && data.total>30 && <nav className="ds-pagination" aria-label="Delivery pages"><Button disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-30))}>Previous</Button><span>{offset+1}–{Math.min(offset+30,data.total)} of {data.total}</span><Button disabled={offset+30>=data.total} onClick={()=>setOffset(n=>n+30)}>Next</Button></nav>}
    <p className="ds-footnote">Local to this profile. Intentionally registered. Files never deleted.</p>
    {editor!==undefined && <ShelfEditor api={api} restoreFocus={focus.restore} entry={editor} roots={status?.roots||[]} busy={busy} error={actionError} save={save} close={close}/>}
    {selected && <Dialog restoreFocus={focus.restore} busy={busy} title={selected.title} close={()=>{if(!busy)close();}}><p className="ds-kind">{selected.kind}{selected.project && ` / ${selected.project}`}</p><p className="ds-detail-description">{selected.description||'No description added.'}</p><p>{selected.tags.map(t=>'#'+t).join(' · ')}</p>
      {selected.session_id && <div className="ds-file"><Field>Session reference (not verified provenance)<Input readOnly value={selected.session_id} onFocus={e=>e.target.select()}/></Field><Button onClick={async()=>{try{await api.copyText(selected.session_id);if(alive.current)setNotice('Session reference copied.');}catch{if(alive.current)setActionError('Copy unavailable. Select the session reference and copy it manually.');}}}>Copy session ID</Button></div>}
      {selected.file && <div className="ds-file"><code>{selected.file.root} / {selected.file.path}</code><div className="ds-actions">{/\.(txt|md|csv)$/i.test(selected.file.path)&&<Button disabled={busy} onClick={()=>readFile(selected,true)}>Preview text</Button>}<Button disabled={busy} onClick={()=>readFile(selected,false)}>Download file</Button></div><small>Preview is plain text, never rendered HTML.</small></div>}
      {busy&&<p role="status">Working…</p>}{preview&&<div><pre className="ds-preview">{preview.text}</pre>{preview.truncated&&<p>Preview limited to 64 KiB. Download for the complete file.</p>}</div>}
      {actionError&&<ErrorState title="Action failed" description={actionError}/>}
      <div className="ds-actions"><Button disabled={busy} onClick={()=>{const item=selected;close();setEditor(item);}}>Edit metadata</Button><Button variant="destructive" disabled={busy} onClick={()=>{const item=selected;close();setRemoving(item);}}>Remove from shelf</Button></div>
    </Dialog>}
    {removing&&<Dialog restoreFocus={focus.restore} busy={busy} title="Remove this delivery?" close={()=>{if(!busy)close();}}><p><strong>{removing.title}</strong> will be removed from this profile’s shelf.</p><p>Only metadata is removed. The original file will not be deleted.</p>{actionError&&<ErrorState title="Action failed" description={actionError}/>}<div className="ds-actions"><Button data-initial-focus disabled={busy} onClick={close}>Keep delivery</Button><Button variant="destructive" disabled={busy} onClick={remove}>{busy?'Removing…':'Remove metadata'}</Button></div></Dialog>}
  </section>;
}
