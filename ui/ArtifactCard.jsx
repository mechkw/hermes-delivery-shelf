import React,{useEffect,useState} from 'react';
import {Button} from '@saved/presentation';
export function ArtifactCard({api,item,busy,open,download,tag}){
 const [image,setImage]=useState(null);
 const name=item.file?.path.split('/').pop()||item.title;
 const type=item.file?.path.split('.').pop().toUpperCase()||'NOTE';
 useEffect(()=>{
  let live=true,url;setImage(null);
  if(item.file&&/\.(png|jpe?g|webp|gif)$/i.test(item.file.path))api(`/entries/${item.id}/thumbnail`).then(file=>{
   if(!live)return;
   if(!['image/png','image/jpeg','image/webp','image/gif'].includes(file.media_type))return;
   const bytes=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));
   url=URL.createObjectURL(new Blob([bytes],{type:file.media_type}));setImage(url);
  }).catch(()=>{});
  return()=>{live=false;if(url)URL.revokeObjectURL(url);};
 },[api,item.id,item.revision,item.file?.path]);
 return <article className="ds-card ds-artifact-card" data-kind={item.kind}>
  <div className="ds-artifact-preview">{image?<img src={image} alt={item.title} onError={()=>setImage(null)}/>:<span className="ds-file-type" aria-label={type+' file'}>{type}</span>}
   {item.file&&<Button className="ds-download-overlay" aria-label={'Download '+name} disabled={busy} onClick={()=>download(item)}><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5"/></svg></Button>}
  </div>
  <div className="ds-artifact-meta"><small className="ds-muted">{type} · {item.kind}</small><h2><Button className="ds-card-title" data-dialog-trigger variant="text" disabled={busy} onClick={()=>open(item)}><span>{item.title}</span></Button></h2>
  {name!==item.title&&<p className="ds-artifact-name">{name}</p>}<p className="ds-description">{item.description}</p>
  <div className="ds-tags">{item.tags.slice(0,3).map(t=><Button variant="chip" aria-label={`Filter tag ${t}`} key={t} onClick={()=>tag(t)}>#{t}</Button>)}</div>
  <footer><time dateTime={new Date(item.updated*1000).toISOString()}>{new Date(item.updated*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'})}</time>{item.project&&<span>{item.project}</span>}</footer>
  <div className="ds-artifact-actions">{item.session_id&&api.openSession&&<Button variant="text" onClick={()=>api.openSession(item.session_id)}>Chat</Button>}{item.file&&<Button variant="text" disabled={busy} onClick={()=>download(item)}>Download</Button>}</div></div>
 </article>;
}
