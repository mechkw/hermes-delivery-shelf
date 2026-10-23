import React, {useEffect, useRef, useState, useId} from 'react';
import styles from './style.css';

const kinds = ['document', 'image', 'report', 'code', 'other'];
const fresh = () => ({title:'',description:'',kind:'document',project:'',tags:[],file:null,session_id:''});
const message = error => typeof error?.message === 'string' ? error.message : 'The request failed. Try again.';

function Dialog({title, children, close}) {
  const ref = useRef(null), id = useId();
  useEffect(() => { const node=ref.current; node.showModal(); node.querySelector('[data-initial-focus]')?.focus(); return () => node.close(); }, []);
  return <dialog ref={ref} className="ds-dialog ds" aria-labelledby={id} onCancel={e=>{e.preventDefault();close();}}>
    <div className="ds-dialog-head"><h2 id={id}>{title}</h2><button type="button" aria-label="Close dialog" onClick={close}>×</button></div>
    {children}
  </dialog>;
}

function Editor({entry, roots, busy, error, save, close}) {
  const [draft,setDraft]=useState(entry || fresh()), [tags,setTags]=useState((entry?.tags||[]).join('\n'));
  const [root,setRoot]=useState(entry?.file?.root||roots[0]||''), [path,setPath]=useState(entry?.file?.path||'');
  const change=(key,value)=>setDraft(d=>({...d,[key]:value}));
  return <Dialog title={entry ? 'Edit delivery' : 'Add a delivery'} close={()=>{if(!busy)close();}}>
    <form onSubmit={e=>{e.preventDefault();save({...draft,tags:tags.split('\n').map(t=>t.trim()).filter(Boolean),file:path.trim()?{root,path:path.trim()}:null});}}>
      <p className="ds-muted">Save only the work you choose. Files stay where they are.</p>
      <label>Title<input data-initial-focus required maxLength={160} value={draft.title} onChange={e=>change('title',e.target.value)}/></label>
      <label>Description<textarea rows={3} maxLength={4000} value={draft.description} onChange={e=>change('description',e.target.value)}/></label>
      <div className="ds-two"><label>Kind<select value={draft.kind} onChange={e=>change('kind',e.target.value)}>{kinds.map(k=><option key={k}>{k}</option>)}</select></label>
      <label>Project<input maxLength={100} value={draft.project} onChange={e=>change('project',e.target.value)}/></label></div>
      <label>Session reference <span className="ds-muted">optional; not verified provenance</span><input maxLength={160} pattern="[A-Za-z0-9_.:\-]*" value={draft.session_id||''} onChange={e=>change('session_id',e.target.value)}/></label>
      <label>Tags (one per line)<textarea aria-label="Tags (one per line)" rows={3} value={tags} maxLength={820} onChange={e=>setTags(e.target.value)}/></label>
      <fieldset><legend>Optional registered file</legend><p className="ds-muted">Approved roots only. Text, PDF and raster images; up to 10 MiB. Hidden files, sensitive names, symlinks and hard links are refused.</p>
        <label>Approved root<select value={root} onChange={e=>setRoot(e.target.value)}><option value="" disabled>Select root</option>{roots.map(r=><option key={r}>{r}</option>)}</select></label>
        <label>Relative file path<input value={path} maxLength={1024} onChange={e=>setPath(e.target.value)} placeholder="project/final-report.pdf"/></label>
        <small>Leave the path empty for metadata only. A path is not an upload.</small>
      </fieldset>
      {error && <p role="alert" className="ds-error">{error}</p>}
      <div className="ds-actions"><button type="button" disabled={busy} onClick={close}>Cancel</button><button className="ds-primary" disabled={busy} type="submit">{busy?'Saving…':entry?'Save changes':'Add delivery'}</button></div>
    </form>
  </Dialog>;
}

export function Shelf({api}) {
  const [status,setStatus]=useState(null), [data,setData]=useState({items:[],total:0}), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [filters,setFilters]=useState({q:'',tag:'',kind:'',project:''}), [offset,setOffset]=useState(0), [refresh,setRefresh]=useState(0);
  const [editor,setEditor]=useState(undefined), [selected,setSelected]=useState(null), [removing,setRemoving]=useState(null);
  const [busy,setBusy]=useState(false), [actionError,setActionError]=useState(''), [notice,setNotice]=useState(''), [preview,setPreview]=useState(null);
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
      const saved=await api(editor?`/entries/${editor.id}`:'/entries',{method:editor?'PUT':'POST',body:payload});
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
  return <main className="ds ds-shelf">
    <style>{styles}</style>
    <header className="ds-header"><div><p className="ds-eyebrow">COLLECTED WORK <span> / {status?.profile||'your profile'}</span></p><h1>Delivery Shelf<span aria-hidden="true">.</span></h1><p className="ds-subtitle">The work worth keeping, right at hand.</p></div>
      <button className="ds-primary" disabled={!status} onClick={()=>{close();setEditor(null);}}>＋ Add delivery</button></header>
    <section aria-label="Filter deliveries" className="ds-filters">
      <label className="ds-search">Search<input type="search" placeholder="Find a title or description…" maxLength={200} value={filters.q} onChange={e=>filter('q',e.target.value)}/></label>
      <label>Kind<select value={filters.kind} onChange={e=>filter('kind',e.target.value)}><option value="">All kinds</option>{kinds.map(k=><option key={k}>{k}</option>)}</select></label>
      <label>Project<input placeholder="Exact project" maxLength={100} value={filters.project} onChange={e=>filter('project',e.target.value)}/></label>
      <label>Tag<input placeholder="Exact tag" maxLength={40} value={filters.tag} onChange={e=>filter('tag',e.target.value)}/></label>
    </section>
    <div className="ds-toolbar"><span aria-live="polite">{loading?'Loading your shelf…':`${data.total} ${data.total===1?'delivery':'deliveries'}`}</span><div><button onClick={()=>{setFilters({q:'',tag:'',kind:'',project:''});setOffset(0);}}>Clear filters</button><button onClick={()=>setRefresh(n=>n+1)}>Refresh</button></div></div>
    {notice && <p role="status" className="ds-notice">{notice}</p>}
    {error ? <section className="ds-empty" role="alert"><h2>Could not open your shelf</h2><p>{error}</p><button onClick={()=>setRefresh(n=>n+1)}>Try again</button></section>:
      loading ? <div className="ds-empty" role="status"><div className="ds-loader" aria-hidden="true"/><p>Loading registered deliveries…</p></div>:
      !data.items.length ? <section className="ds-empty"><span className="ds-shelf-mark" aria-hidden="true">▥</span><h2>{Object.values(filters).some(Boolean)?'No matching deliveries':'Make room for finished work'}</h2><p>{Object.values(filters).some(Boolean)?'Try another search or clear the filters.':'Add a report, design, document or other deliverable. Nothing is collected automatically.'}</p>{!Object.values(filters).some(Boolean)&&<button className="ds-primary" onClick={()=>setEditor(null)}>Add your first delivery</button>}</section>:
      <section className="ds-grid" aria-label="Deliveries">{data.items.map(item=><article key={item.id} className="ds-card" data-kind={item.kind}>
        <div className="ds-card-top"><span className="ds-kind">{item.kind}</span><span className="ds-muted">{item.file?'File attached':'No attachment'}</span></div>
        <h2><button onClick={()=>{close();setSelected(item);}}>{item.title}</button></h2><p className="ds-description">{item.description||'No description added.'}</p>
        <div className="ds-tags">{item.tags.map(t=><button key={t} onClick={()=>filter('tag',t)} aria-label={`Filter tag ${t}`}>#{t}</button>)}</div>
        <footer><span>{item.project||'No project'}</span><time dateTime={new Date(item.updated*1000).toISOString()}>{new Date(item.updated*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})}</time></footer>
      </article>)}</section>}
    {!loading && data.total>30 && <nav className="ds-pagination" aria-label="Delivery pages"><button disabled={offset===0} onClick={()=>setOffset(n=>Math.max(0,n-30))}>Previous</button><span>{offset+1}–{Math.min(offset+30,data.total)} of {data.total}</span><button disabled={offset+30>=data.total} onClick={()=>setOffset(n=>n+30)}>Next</button></nav>}
    <p className="ds-footnote">Local to this profile. Intentionally registered. Files never deleted.</p>
    {editor!==undefined && <Editor entry={editor} roots={status?.roots||[]} busy={busy} error={actionError} save={save} close={close}/>}
    {selected && <Dialog title={selected.title} close={()=>{if(!busy)close();}}><p className="ds-kind">{selected.kind}{selected.project && ` / ${selected.project}`}</p><p className="ds-detail-description">{selected.description||'No description added.'}</p><p>{selected.tags.map(t=>'#'+t).join(' · ')}</p>
      {selected.session_id && <div className="ds-file"><label>Session reference (not verified provenance)<input readOnly value={selected.session_id} onFocus={e=>e.target.select()}/></label><button onClick={async()=>{try{await api.copyText(selected.session_id);if(alive.current)setNotice('Session reference copied.');}catch{if(alive.current)setActionError('Copy unavailable. Select the session reference and copy it manually.');}}}>Copy session ID</button></div>}
      {selected.file && <div className="ds-file"><code>{selected.file.root} / {selected.file.path}</code><div className="ds-actions">{/\.(txt|md|csv)$/i.test(selected.file.path)&&<button disabled={busy} onClick={()=>readFile(selected,true)}>Preview text</button>}<button disabled={busy} onClick={()=>readFile(selected,false)}>Download file</button></div><small>Preview is plain text, never rendered HTML.</small></div>}
      {busy&&<p role="status">Working…</p>}{preview&&<div><pre className="ds-preview">{preview.text}</pre>{preview.truncated&&<p>Preview limited to 64 KiB. Download for the complete file.</p>}</div>}
      {actionError&&<p className="ds-error" role="alert">{actionError}</p>}
      <div className="ds-actions"><button disabled={busy} onClick={()=>{const item=selected;close();setEditor(item);}}>Edit metadata</button><button className="ds-danger" disabled={busy} onClick={()=>{const item=selected;close();setRemoving(item);}}>Remove from shelf</button></div>
    </Dialog>}
    {removing&&<Dialog title="Remove this delivery?" close={()=>{if(!busy)close();}}><p><strong>{removing.title}</strong> will be removed from this profile’s shelf.</p><p>Only metadata is removed. The original file will not be deleted.</p>{actionError&&<p role="alert" className="ds-error">{actionError}</p>}<div className="ds-actions"><button data-initial-focus disabled={busy} onClick={close}>Keep delivery</button><button className="ds-danger" disabled={busy} onClick={remove}>{busy?'Removing…':'Remove metadata'}</button></div></Dialog>}
  </main>;
}
