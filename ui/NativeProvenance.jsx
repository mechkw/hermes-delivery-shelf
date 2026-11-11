import React,{useState} from 'react';
import {Button} from '@saved/presentation';
import {formatShelfTime} from './NativeSettings.jsx';

/** Never backfill an edition's missing origin from the entry's latest source. */
export function NativeProvenance({api,entry,version,file,settings,busy}){
 const [error,setError]=useState('');
 const origin=version?(file?.provenance||{}):(entry.provenance||{});
 const known=origin.known!==false,source=known?origin.original_path:null;
 const session=known?origin.session_id:null,profile=known?origin.profile:null,message=known?origin.message_id:null;
 const legacySession=!version?entry.session_id:null;
 async function copy(value){try{setError('');await api.copyText(String(value));}catch(e){setError(e?.message||'Copy unavailable.');}}
 return <section className="ds-native-provenance" aria-label="Original source">
  <p>Saved {formatShelfTime(version?.created??entry.created,settings)}</p>
  {source?<div><strong>Original source</strong><code>{source}</code><Button disabled={busy||!api.copyText} onClick={()=>copy(source)}>Copy original source path</Button></div>:<p>Original source unavailable · historical provenance was not recorded.</p>}
  {session&&profile?<div><span>Profile: {profile} · Conversation: {session}</span><Button disabled={busy||!api.openSession} onClick={()=>api.openSession(session,profile)}>Open original conversation</Button></div>:<p>Original conversation unavailable{legacySession?` · legacy association: ${legacySession} (owning profile not recorded)`:''}.</p>}
  {message!==null&&message!==undefined?<div><span>Original message: {String(message)}</span><Button disabled={busy||!api.copyText} onClick={()=>copy(message)}>Copy original message ID</Button><small>Conversation opens at its saved position; exact-message navigation is unavailable in the public SDK.</small></div>:<p>Original message unavailable · no message identifier was recorded.</p>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
