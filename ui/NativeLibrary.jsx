import React,{useEffect,useState} from 'react';
import {Checkbox,Codicon,SegmentedControl} from '@hermes/plugin-sdk';
import {Button,Input,SearchField,Choice,EmptyState,Hint} from '@saved/presentation';
import {NativeLifecycleControls} from './NativeLifecycle.jsx';
import {defaultSettings,viewOptions,formatShelfTime} from './NativeSettings.jsx';
import {NativeProvenance} from './NativeProvenance.jsx';
import {NativeVersionPermission} from './NativeVersionPermission.jsx';

const encode=encodeURIComponent;
const raster=/\.(png|jpe?g|gif|webp)$/i;
// Eligibility requests only a backend-rendered raster; documents are never
// embedded directly. Missing renderers, rejected files and unsafe MIME types
// keep the honest file-type icon on both source and preserved-file surfaces.
const thumbnailTypes=/\.(png|jpe?g|gif|webp|pdf|docx|pptx|xlsx)$/i;
const imageMimes=new Set(['image/png','image/jpeg','image/webp','image/gif']);
export function fileType(file){return (file.name||file.file?.path||'').split('.').pop()?.toUpperCase()||'FILE';}
export function savedFiles(entry){
 const version=entry.versions?.find(v=>v.id===entry.current_version);
 if(version)return version.files.map(file=>({entry,version,file,key:entry.id+':'+version.id+':'+file.id}));
 const refs=entry.files?.length?entry.files:entry.file?[entry.file]:[];
 return refs.map((ref,index)=>({entry,version:null,file:{id:String(index),name:ref.path.split('/').pop(),file:ref},key:entry.id+':legacy:'+index}));
}
export function savedFileUrl({entry,version,file}){return version?`/entries/${encode(entry.id)}/versions/${encode(version.id)}/files/${encode(file.id)}`:`/entries/${encode(entry.id)}/file`;}
export function FileTypeIcon({file}){
 const type=fileType(file),icon=raster.test(file.name||file.file?.path||'')?'file-media':['TXT','MD','CSV'].includes(type)?'file-text':type==='ZIP'?'file-zip':type==='PDF'?'file-pdf':'file';
 return <span className="ds-native-type" aria-label={type+' file'}><Codicon name={icon} size={28}/><small>{type}</small></span>;
}
/** Only bounded authenticated raster bytes become images; HTML/SVG stay inert. */
export function FileVisual({api,record,source,sessionId,large=false}){
 const [image,setImage]=useState(null);
 const file=source||record.file,name=file.name||file.file?.path||'';
 const url=record?`/entries/${encode(record.entry.id)}/thumbnail`+(record.version?'?'+new URLSearchParams({version_id:record.version.id,file_id:file.id}):''):'/sources/thumbnail';
 const requestKey=JSON.stringify([url,record?.entry.revision,sessionId,source?.id,source?.source]);
 useEffect(()=>{let active=true,blobUrl;setImage(null);
  if(thumbnailTypes.test(name))api(url,source?{method:'POST',body:{session_id:sessionId,file:source.file,source:source.source}}:undefined).then(result=>{
   if(!active||!imageMimes.has(result.media_type))return;
   const bytes=Uint8Array.from(atob(result.base64),c=>c.charCodeAt(0));
   blobUrl=URL.createObjectURL(new Blob([bytes],{type:result.media_type}));setImage(blobUrl);
  }).catch(()=>{});
  return()=>{active=false;if(blobUrl)URL.revokeObjectURL(blobUrl);};
 },[api,requestKey]);
 return <div className={'ds-native-visual'+(large?' ds-native-visual-large':'')}>{image?<img src={image} alt={file.name} onError={()=>setImage(null)}/>:<FileTypeIcon file={file}/>}</div>;
}
function FileCard({api,record,busy,open,download,companion=false,selection}){
 return <article className="ds-native-file-card">
  {selection&&<div className="ds-native-card-selection">{selection}</div>}
  <Button className="ds-native-preview-button" variant="text" disabled={busy} aria-label={'Preview '+record.file.name} onClick={()=>open(record.entry,record)}><FileVisual api={api} record={record}/></Button>
  <div className="ds-native-file-copy"><h3><Button variant="text" disabled={busy} onClick={()=>open(record.entry,record)}>{record.file.name}</Button></h3>
   <p>{record.entry.description||'No description added.'}</p><div className="ds-native-meta-line"><span>{record.version?'Preserved copy · v'+record.version.number:'Original-file link'}</span><Hint label={'Download '+record.file.name} name={'Download '+record.file.name} disabled={busy}><Button className="ds-native-icon-action" variant="text" disabled={busy} aria-label={'Download '+record.file.name} onClick={()=>download(record)}><Codicon name="cloud-download"/></Button></Hint></div>
   {companion&&<Button variant="text" className="ds-native-companion" onClick={()=>open(record.entry,record)}>Delivered together · {savedFiles(record.entry).length} files</Button>}
  </div>
 </article>;
}
export function NativeDeliveryPreview({api,entry,busy,initialVersion,initialFile,settings}){
 const [versionId,setVersionId]=useState(initialVersion||entry.current_version),[fileId,setFileId]=useState(initialFile||null),[text,setText]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const versions=entry.versions||[],version=versions.find(v=>v.id===versionId)||versions.find(v=>v.id===entry.current_version)||versions[0];
 const records=version?version.files.map(file=>({entry,version,file,key:entry.id+':'+version.id+':'+file.id})):savedFiles(entry);
 const record=records.find(r=>r.file.id===fileId)||records[0],token=JSON.stringify([entry.id,entry.revision,version?.id,record?.file.id]);
 useEffect(()=>{setText(null);setError('');setLoading(false);},[token]);
 const alive=React.useRef(true),current=React.useRef(token);current.current=token;
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 async function previewText(){const ticket=token;setLoading(true);setError('');try{
  const result=await api(savedFileUrl(record)+(record.version?'':'?preview=true'));
  if(alive.current&&current.current===ticket){const value=record.version?new TextDecoder().decode(Uint8Array.from(atob(result.base64),c=>c.charCodeAt(0)).slice(0,65536)):result.text;setText({value,truncated:record.version?atob(result.base64).length>65536:result.truncated});}
 }catch(error){if(alive.current&&current.current===ticket)setError(error?.message||'Preview unavailable. Download the file instead.');}finally{if(alive.current&&current.current===ticket)setLoading(false);}}
 return <section aria-label="Delivery preview" className="ds-native-detail-preview ds-native-detail">
  <NativeVersionPermission api={api} entry={entry} busy={busy}/>
  {versions.length>0&&<Choice aria-label="Preview version" disabled={busy} value={version.id} options={versions.map(v=>({value:v.id,label:'Version '+v.number}))} onValueChange={id=>{setVersionId(id);setFileId(null);}}/>}
  {records.length>1&&<Choice aria-label="Preview file" disabled={busy} value={record?.file.id||''} options={records.map(r=>({value:r.file.id,label:r.file.name}))} onValueChange={setFileId}/>}
  {record&&<><FileVisual key={record.key} api={api} record={record} large/><p>{record.file.name} · {record.version?'Preserved copy · Version '+record.version.number:'Original-file link · source still required'}</p>
   <NativeProvenance key={'provenance:'+record.key} api={api} entry={entry} version={record.version} file={record.file} settings={settings} busy={busy}/>
   {/\.(txt|md|csv)$/i.test(record.file.name)&&<Button disabled={busy||loading} onClick={previewText}>{loading?'Loading preview…':'Preview text'}</Button>}
   {text&&<><pre className="ds-native-text-preview">{text.value}</pre>{text.truncated&&<small>Preview limited to 64 KiB. Download for the complete file.</small>}</>}{error&&<p role="alert">{error}</p>}
  </>}
 </section>;
}

export function NativeLibrary({api,catalog,busy,open,download,pages,status,settings=defaultSettings}){
 const enabled=viewOptions.filter(view=>settings.enabled_views.includes(view.id));
 const [view,setView]=useState(settings.default_view),[inspect,setInspect]=useState(null),[collapsed,setCollapsed]=useState(new Set());
 useEffect(()=>{if(!settings.enabled_views.includes(view))setView(settings.default_view);},[view,settings]);
 const groupId=React.useId();
 const items=catalog.result?.data?.items||[],records=items.flatMap(savedFiles),record=records.find(r=>r.key===inspect)||records[0];
 const filters=catalog.filters||{};
 const matching={q:catalog.query,...filters,state:filters.state||'active'},filterKey=JSON.stringify(matching);
 const [selection,setSelection]=useState({key:filterKey,ids:[],all:false,count:0});
 const selected=selection.key===filterKey?selection:{key:filterKey,ids:[],all:false,count:0};
 const checkbox=(item,name)=>{const label='Select delivery '+item.title+(name?' via '+name:''),hint='Select entire delivery: '+item.title;return <Checkbox className="ds-native-select-checkbox" aria-label={label} aria-description={hint} title={hint} disabled={busy||selected.all} checked={selected.all||selected.ids.includes(item.id)} onCheckedChange={checked=>setSelection({...selected,ids:checked?[...new Set([...selected.ids,item.id])]:selected.ids.filter(id=>id!==item.id)})}/>;};
 const filter=(key,value)=>catalog.setFilter(key,value);
 return <section aria-label="Delivery catalog" className="ds-native-library">
  <header className="ds-native-library-heading"><div><h2>Your work, kept together.</h2><p>Files from the same delivery, with room to evolve.</p></div><Button ref={catalog.addRef} variant="default" onClick={catalog.add}><Codicon name="add"/>Add delivery</Button></header>
  <div className="ds-native-toolbar"><SegmentedControl value={view} onChange={setView} options={enabled}/><span className="ds-native-muted" aria-live="polite">{catalog.result?.data?`${catalog.result.data.total} ${catalog.result.data.total===1?'delivery':'deliveries'} · ${records.length} files on this page`:'Loading deliveries…'}</span></div>
  <section className="ds-native-filters" aria-label="Filter deliveries"><SearchField aria-label="Search deliveries" placeholder="Find a title or description…" value={catalog.query} onChange={q=>catalog.setQuery(q.slice(0,200))}/><Choice aria-label="Delivery type" value={filters.kind||''} onValueChange={value=>filter('kind',value)} options={[{value:'',label:'All types'},...['document','image','report','code','other'].map(value=>({value,label:value}))]}/><Input aria-label="Project filter" placeholder="Exact project" maxLength={100} value={filters.project||''} onChange={e=>filter('project',e.target.value)}/><Button onClick={catalog.clear}>Clear filters</Button></section>
  {status}
  <NativeLifecycleControls api={api} catalog={catalog} busy={busy} selection={selection} setSelection={setSelection} filterKey={filterKey} filters={matching}/>

  {catalog.result?.data&&!items.length&&<EmptyState title="No matching deliveries" description="Try another search or clear the filters. Nothing is saved automatically."/>}
  {items.length>0&&view==='together'&&<div className="ds-native-groups">{items.map(item=><section className="ds-native-group" key={item.id} aria-label={item.title}>
   <header className="ds-native-group-header"><div className="ds-native-group-selection">{checkbox(item)}</div><h3><Button className="ds-native-group-toggle" variant="text" aria-label={(collapsed.has(item.id)?'Expand ':'Collapse ')+item.title} aria-expanded={!collapsed.has(item.id)} aria-controls={groupId+'-'+item.id} onClick={()=>setCollapsed(current=>{const next=new Set(current);next.has(item.id)?next.delete(item.id):next.add(item.id);return next;})}><Codicon name="files" size={22}/><span className="ds-native-group-copy"><span>{item.title}</span><small>{savedFiles(item).length} saved files{item.project?' · '+item.project:''}</small></span><Codicon name={collapsed.has(item.id)?'chevron-down':'chevron-up'}/></Button></h3><Hint label="Open delivery details" name={'Open delivery '+item.title} disabled={busy}><Button className="ds-native-icon-action" variant="text" disabled={busy} aria-label={'Open delivery '+item.title} onClick={()=>open(item)}><Codicon name="go-to-file"/></Button></Hint></header>
   <div id={groupId+'-'+item.id} className="ds-native-group-body" hidden={collapsed.has(item.id)}><p className="ds-native-delivery-dates">Saved {formatShelfTime(item.created,settings)}{item.delete_after!=null&&<> · Recover before {formatShelfTime(item.delete_after,settings)}</>}</p><div className="ds-native-companion-grid">{savedFiles(item).map(r=><FileCard key={r.key} api={api} record={r} busy={busy} open={open} download={download}/>)}</div>{!savedFiles(item).length&&<p className="ds-native-muted ds-native-no-files">Metadata only · no attached file</p>}</div>
  </section>)}</div>}
  {records.length>0&&view==='gallery'&&<section className="ds-native-companion-grid" aria-label="File gallery">{records.map(r=><FileCard key={r.key} api={api} record={r} busy={busy} open={open} download={download} companion selection={checkbox(r.entry,r.file.name)}/>)}</section>}
  {records.length>0&&view==='library'&&<div className="ds-native-library-split"><section aria-label="Saved file list" className="ds-native-library-list"><div className="ds-native-list-heading">File / delivery</div>{records.map(r=><div key={r.key} className="ds-native-selectable-row">{checkbox(r.entry,r.file.name)}<Button className="ds-native-file-row" variant="text" aria-label={'Inspect '+r.file.name} aria-pressed={record.key===r.key} onClick={()=>setInspect(r.key)}><FileTypeIcon file={r.file}/><span><strong>{r.file.name}</strong><small>{r.entry.title}</small></span><small>{r.version?'v'+r.version.number:'Link'}</small></Button></div>)}</section><aside className="ds-native-inspector" aria-label="File preview"><FileVisual api={api} record={record} large/><p className="ds-native-eyebrow">{fileType(record.file)} · {record.version?'Preserved copy':'Original-file link'}</p><h3>{record.file.name}</h3><p>{record.entry.description}</p><small>From {record.entry.title}</small><NativeVersionPermission api={api} entry={record.entry} busy={busy}/><Button variant="default" disabled={busy} onClick={()=>open(record.entry,record)}>Open file & history</Button><Button disabled={busy} onClick={()=>download(record)}>Download file</Button></aside></div>}
  {pages}<p className="ds-native-footnote">Local to this profile. Intentionally saved. Original files are never deleted.</p>
 </section>;
}
