import React,{useEffect,useRef,useState} from 'react';
import {Switch} from '@hermes/plugin-sdk';
import {Button,Input,Choice,Field,Loader} from '@saved/presentation';
import {EmptyTrashConfirmation} from './NativeLifecycle.jsx';
import styles from './native-chat-shelf.css';

export const defaultSettings={trash_retention_days:60,auto_cleanup:true,timezone:'auto',hour_cycle:'auto',date_format:'medium',default_view:'together',enabled_views:['together','library','gallery'],generate_metadata:true,context_messages:10};
export const viewOptions=[{id:'together',label:'Together'},{id:'library',label:'Library'},{id:'gallery',label:'Gallery'}];
export function resolvedTimezone(settings={}){return settings.timezone&&settings.timezone!=='auto'?settings.timezone:Intl.DateTimeFormat().resolvedOptions().timeZone;}
export function formatShelfTime(seconds,settings={}){
 if(typeof seconds!=='number'||!Number.isFinite(seconds))return 'Date unavailable';
 try{
  const timeZone=resolvedTimezone(settings),date=new Date(seconds*1000),hour=String(settings.hour_cycle||'auto');
  const options={timeZone,hour:'2-digit',minute:'2-digit',timeZoneName:'short',...(hour==='auto'?{}:{hour12:hour==='12'})};
  const day=settings.date_format==='iso'?new Intl.DateTimeFormat('en-CA',{timeZone,year:'numeric',month:'2-digit',day:'2-digit'}).format(date):new Intl.DateTimeFormat(undefined,{timeZone,dateStyle:settings.date_format||'medium'}).format(date);
  return day+' · '+new Intl.DateTimeFormat(undefined,options).format(date)+' · '+timeZone;
 }catch{return 'Date unavailable (invalid timezone or display preference)';}
}
function Toggle({label,value,disabled,onChange}){const id=React.useId();return <div className="ds-native-preference"><label htmlFor={id}>{label}</label><Switch id={id} aria-label={label} checked={value} disabled={disabled} onCheckedChange={onChange}/></div>;}
function formatBytes(bytes=0){
 const units=['B','KiB','MiB','GiB','TiB'];let value=Math.max(0,Number(bytes)||0),unit=0;
 while(value>=1024&&unit<units.length-1){value/=1024;unit++;}
 return new Intl.NumberFormat(undefined,{maximumFractionDigits:1}).format(value)+' '+units[unit];
}
function UsageCounts({entries=0,files=0,bytes=0}){return <span>{entries} {entries===1?'delivery':'deliveries'} · {files} {files===1?'file':'files'} · {formatBytes(bytes)}</span>;}
export function NativeShelfSettings({api}){
 const [settings,setSettings]=useState(null),[storage,setStorage]=useState(null),[error,setError]=useState(''),[status,setStatus]=useState(''),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false),[retry,setRetry]=useState(0);
 const lock=useRef(false),alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{let active=true;setError('');Promise.all([api('/settings'),api('/storage')]).then(([values,usage])=>{if(active){setSettings({...defaultSettings,...values});setStorage(usage);}}).catch(e=>{if(active)setError(e?.message||'Could not load Shelf settings.');});return()=>{active=false;};},[api,retry]);
 const change=(key,value)=>{setSettings(s=>({...s,[key]:value}));setStatus('');};
 async function action(fn){if(lock.current)return;lock.current=true;setBusy(true);setError('');setStatus('');try{await fn();}catch(e){if(alive.current)setError(e?.message||'Request failed. Try again.');}finally{lock.current=false;if(alive.current)setBusy(false);}}
 async function save(){await action(async()=>{
  if(settings.timezone!=='auto'){try{new Intl.DateTimeFormat(undefined,{timeZone:settings.timezone});}catch{throw Error('Use auto or a valid IANA timezone, such as America/New_York.');}}
  // Enumerate the preference-only schema. Never forward unknown server fields
  // or make UI settings an authority for either first saves or new versions.
  const payload=Object.fromEntries(Object.keys(defaultSettings).map(key=>[key,settings[key]]));
  await api('/settings',{method:'PUT',body:payload});const verified=await api('/settings');
  if(alive.current){setSettings({...defaultSettings,...verified});setStatus('Settings saved.');}
 });}
 async function cleanup(){await action(async()=>{await api('/cleanup',{method:'POST',body:{}});const usage=await api('/storage');if(alive.current){setStorage(usage);setStatus('Due-item cleanup complete. Original files were not changed.');}});}
 async function empty(){await action(async()=>{const result=await api('/entries/bulk-action',{method:'POST',body:{action:'empty_trash',filter:{state:'trash'}}});const usage=await api('/storage');if(alive.current){setStorage(usage);setConfirm(false);setStatus(`${result.affected} deliveries moved to Pending deletion. Restore within 60 minutes.`);}});}
 return <section className="ds-native-shelf ds-native-settings" aria-label="Delivery Shelf settings"><style>{styles}</style><h2>Delivery Shelf settings</h2>
  <p>Profile-local browsing, metadata and preservation preferences. Saving a delivery remains a deliberate choice.</p>
  {error&&<div role="alert">{error}<Button disabled={busy} onClick={()=>setRetry(n=>n+1)}>Reload settings</Button></div>}
  {!settings&&!error&&<Loader label="Loading Shelf settings"/>}
  {settings&&<form aria-label="Shelf preferences" onSubmit={e=>{e.preventDefault();void save();}}>
   <h3>Browsing</h3><div className="ds-native-selection-toolbar">{viewOptions.map(view=><Toggle key={view.id} label={'Enable '+view.label} value={settings.enabled_views.includes(view.id)} disabled={busy||(settings.enabled_views.length===1&&settings.enabled_views[0]===view.id)} onChange={enabled=>{const enabled_views=enabled?[...settings.enabled_views,view.id]:settings.enabled_views.filter(id=>id!==view.id);setSettings(s=>({...s,enabled_views,default_view:enabled_views.includes(s.default_view)?s.default_view:enabled_views[0]}));setStatus('');}}/>)}</div>
   <Field title="Default view"><Choice disabled={busy} value={settings.default_view} options={viewOptions.filter(view=>settings.enabled_views.includes(view.id)).map(view=>({value:view.id,label:view.label}))} onValueChange={value=>change('default_view',value)}/></Field><p className="ds-native-muted">Keep at least one view enabled. Disabling the default chooses another enabled view.</p>
   <h3>Date and time</h3><Field title="Timezone" description={'auto uses this device: '+resolvedTimezone()}><Input disabled={busy} value={settings.timezone} maxLength={100} onChange={e=>change('timezone',e.target.value)} placeholder="auto or America/New_York"/></Field>
   <Field title="Date format"><Choice disabled={busy} value={settings.date_format} options={['short','medium','long','iso'].map(value=>({value,label:value==='iso'?'YYYY-MM-DD':value}))} onValueChange={value=>change('date_format',value)}/></Field>
   <Field title="Hour display"><Choice disabled={busy} value={settings.hour_cycle} options={[{value:'auto',label:'Device default'},{value:'12',label:'12-hour'},{value:'24',label:'24-hour'}]} onValueChange={value=>change('hour_cycle',value)}/></Field><p className="ds-native-muted">Example: {formatShelfTime(Date.now()/1000,settings)}</p>
   <h3>Metadata generation</h3><Toggle label="Generate metadata by default" value={settings.generate_metadata} disabled={busy} onChange={value=>change('generate_metadata',value)}/><Field title="Context messages"><Choice disabled={busy} value={String(settings.context_messages)} options={[5,10,20,50].map(value=>({value:String(value),label:String(value)}))} onValueChange={value=>change('context_messages',Number(value))}/></Field>
   <h3>Trash and preservation</h3><Field title="Trash retention" description="Changes also apply to deliveries already in Trash."><Choice disabled={busy} value={String(settings.trash_retention_days)} options={[30,60].map(value=>({value:String(value),label:value+' days'}))} onValueChange={value=>change('trash_retention_days',Number(value))}/></Field><Toggle label="Automatic due-item cleanup" value={settings.auto_cleanup} disabled={busy} onChange={value=>change('auto_cleanup',value)}/>
   <p>Archive keeps deliveries indefinitely. Trash is recoverable until its deadline. Empty Trash starts a separate 60-minute Pending deletion window; recovery is impossible after the preserved copies are purged. Original working files are never deleted.</p>
   <div className="ds-native-selection-toolbar"><Button disabled={busy} onClick={cleanup}>Clean up due items now</Button><Button disabled={busy} onClick={()=>setConfirm(true)}>Empty Trash</Button></div>
   <Button type="submit" variant="default" disabled={busy}>Save settings</Button>
  </form>}
  {storage&&<section aria-label="Storage usage" className="ds-native-storage"><h3>Storage usage</h3><p><strong>Total preserved</strong> · <UsageCounts entries={storage.total_entries} files={storage.total_files} bytes={storage.total_bytes}/></p><dl>{[{id:'active',label:'Active'},{id:'archived',label:'Archive'},{id:'trash',label:'Trash'},{id:'pending_delete',label:'Pending deletion'}].map(({id,label})=><div key={id}><dt>{label}</dt><dd><UsageCounts {...storage.states?.[id]}/></dd></div>)}</dl>{storage.pending_purges>0&&<p>{storage.pending_purges} {storage.pending_purges===1?'purge awaiting completion':'purges awaiting completion'} · {formatBytes(storage.pending_purge_bytes)}</p>}<p className="ds-native-muted">All saved versions are counted. Preserved Shelf copies only; original working files, database and preview cache are excluded.</p></section>}
  {status&&<p role="status">{status}</p>}
  <EmptyTrashConfirmation open={confirm} busy={busy} onCancel={()=>setConfirm(false)} onConfirm={empty}/>
 </section>;
}
