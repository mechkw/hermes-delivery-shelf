import {createDraft,beginGeneration,applyGeneration,invalidateGeneration} from './metadata-draft.js';

export const scopeKey = ({connectionId,profile,sessionId}) => JSON.stringify([connectionId,profile,sessionId||'']);
export function newShelfDraft(ownerKey,sessionId='') {
 return {metadata:createDraft(ownerKey,'delivery:'+sessionId),session_id:sessionId,selections:[],kind:'document',project:'',previous_exchanges:10};
}
export function toggleSelection(selections,item) {
 return selections.some(s=>s.id===item.id)?selections.filter(s=>s.id!==item.id):[...selections,item];
}
export async function generateMetadata(api,draft,commit) {
 const started=beginGeneration(draft.metadata);
 if(!started.capture)return;
 commit(current=>({...current,metadata:started.state}));
 try {
  const result=await api('/generation/draft',{method:'POST',body:{
   session_id:draft.session_id,source:draft.selections[0]?.source,
   previous_exchanges:draft.previous_exchanges,...started.request
  }});
  const generated=Object.fromEntries(started.request.requested_fields.filter(k=>Object.hasOwn(result.draft||{},k)).map(k=>[k,result.draft[k]]));
  commit(current=>({...current,metadata:applyGeneration(current.metadata,started.capture,generated).state}));
 } catch(error) {
  commit(current=>({...current,metadata:invalidateGeneration(current.metadata)}));
  throw error;
 }
}
export async function registerDelivery(api,draft) {
 const saved=await api('/sources/register-many',{method:'POST',body:{
  ...draft.metadata.values,kind:draft.kind,project:draft.project,session_id:draft.session_id,
  selections:draft.selections.map(({file,source})=>({file,source}))
 }});
 return api(`/entries/${encodeURIComponent(saved.id)}`);
}
export async function updateVersion(api,entry,selections,sessionId='') {
 const provenance=sessionId?{session_id:sessionId,sources:selections.filter(s=>s.source).map(s=>({file:s.file,source:s.source,session_id:s.session_id||sessionId}))}:{};
 await api(`/entries/${encodeURIComponent(entry.id)}/versions`,{method:'POST',body:{revision:entry.revision,files:selections.map(s=>s.file),...provenance}});
 return api(`/entries/${encodeURIComponent(entry.id)}`);
}
export function createShelfApi(ctx,host,owner,isDisposed=()=>false) {
 let retired=false;
 const stop=host.state.connectionId.listen(connection=>{if(connection!==owner.connectionId)retired=true;});
 ctx.onDispose(stop);
 const valid=()=>!retired&&!isDisposed()&&host.state.connectionId.get()===owner.connectionId;
 const api=async(path,options={})=>{
  if(!valid())throw Error('Connection changed. Reopen Delivery Shelf.');
  const result=await ctx.rest(path+(path.includes('?')?'&':'?')+'profile='+encodeURIComponent(owner.profile),options);
  if(!valid())throw Error('Connection changed. Reopen Delivery Shelf.');
  return result;
 };
 api.desktop=true;
 api.openSession=(id,profile)=>{if(valid())host.openSession(id,{profile:profile||owner.profile});};
 api.copyText=async text=>{if(!valid()||!await ctx.os.writeClipboard(text))throw Error('Copy unavailable');};
 return api;
}
export function downloadFile(file) {
 const bytes=Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0));
 const url=URL.createObjectURL(new Blob([bytes],{type:file.media_type||'application/octet-stream'}));
 const a=document.createElement('a');a.href=url;a.download=file.name;a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
}
