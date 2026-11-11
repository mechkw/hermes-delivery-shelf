import React,{useEffect,useRef,useState} from 'react';
import {Button} from '@saved/presentation';

/** Delivery-level status only. Standing consent can only originate in a concrete offer. */
export function NativeVersionPermission({api,entry,busy}){
 const [permission,setPermission]=useState(null),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const epoch=useRef(0),url=`/entries/${encodeURIComponent(entry.id)}/version-permission`;
 useEffect(()=>{const ticket=++epoch.current;setPermission(null);setError('');setSaving(false);
  api(url).then(value=>{if(ticket===epoch.current)setPermission(value);}).catch(()=>{if(ticket===epoch.current)setError('New version permission unavailable.');});
  return()=>{epoch.current++;};
 },[api,url,entry.revision,entry.state]);
 async function revoke(){const ticket=epoch.current;setSaving(true);setError('');try{
  await api(url,{method:'DELETE'});
  const value=await api(url);
  if(ticket===epoch.current){setPermission(value);if(value.always)setError('Permission is still active. Try again.');}
 }catch(e){if(ticket===epoch.current)setError(e?.message||'Could not verify permission change.');}finally{if(ticket===epoch.current)setSaving(false);}}
 return <section aria-label="New version permission" className="ds-native-version-permission">
  <p aria-live="polite">{permission?`New versions: ${permission.always?'Always for this delivery':'Ask first'}${permission.paused?' · Paused':''}`:'New versions: Checking permission…'}</p>
  {permission?.always&&<Button variant="text" disabled={busy||saving} onClick={revoke}>Ask before next version</Button>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
