import React,{useRef,useState} from 'react';
import {Checkbox,Codicon,Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@hermes/plugin-sdk';
import {Button,Choice,DialogFooter,Hint} from '@saved/presentation';

export const lifecycleStates=[{value:'active',label:'Active'},{value:'archived',label:'Archive'},{value:'trash',label:'Trash'},{value:'pending_delete',label:'Pending deletion'}];
export function EmptyTrashConfirmation({open,busy,onCancel,onConfirm}){
 return <Dialog open={open} onOpenChange={value=>{if(!value&&!busy)onCancel();}}><DialogContent aria-describedby="shelf-empty-trash-description" showCloseButton={!busy}><DialogHeader><DialogTitle>Empty Trash?</DialogTitle><DialogDescription id="shelf-empty-trash-description">All deliveries in Trash will move to Pending deletion. You can restore them for 60 minutes. After that, preserved Shelf copies are irreversibly deleted. Original working files are never deleted.</DialogDescription></DialogHeader><DialogFooter><Button disabled={busy} onClick={onCancel}>Cancel</Button><Button disabled={busy} onClick={onConfirm}>Empty Trash · start 60-minute recovery</Button></DialogFooter></DialogContent></Dialog>;
}
export function NativeLifecycleControls({api,catalog,busy,selection,setSelection,filterKey,filters}){
 const [notice,setNotice]=useState(null),[error,setError]=useState(''),[working,setWorking]=useState(false),[confirm,setConfirm]=useState(false);
 const lock=useRef(false),alive=useRef(true);React.useEffect(()=>()=>{alive.current=false;},[]);
 const items=catalog.result?.data?.items||[],total=catalog.result?.data?.total||0;
 const selected=selection.key===filterKey?selection:{key:filterKey,ids:[],all:false,count:0};
 const count=selected.all?selected.count:selected.ids.length,state=filters.state||'active';
 const disabled=busy||working;
 async function run(action,explicit){
  if(lock.current)return;lock.current=true;setWorking(true);setError('');
  const target=explicit||(selected.all?{filter:filters}:{ids:selected.ids});
  try{
   const result=await api('/entries/bulk-action',{method:'POST',body:{action,...target}});
   // Refresh the authoritative filtered catalog after every mutation. Archive
   // Undo is scoped to exact returned IDs, never a filter that can grow later.
   catalog.retry();
   if(!alive.current)return;
   const ids=(result.items||[]).map(item=>item.id);
   setSelection({key:filterKey,ids:[],all:false,count:0});setConfirm(false);
   setNotice({text:action==='empty_trash'?`${result.affected} deliveries moved to Pending deletion. Recoverable for 60 minutes.`:`${result.affected} ${result.affected===1?'delivery':'deliveries'} ${action==='archive'?'archived':action==='trash'?'moved to Trash':'restored'}.`,undo:action==='archive'&&ids.length===result.affected?ids:null});
  }catch(e){if(alive.current)setError(e?.message||'Could not update deliveries. Retry.');}
  finally{lock.current=false;if(alive.current)setWorking(false);}
 }
 return <section className="ds-native-lifecycle" aria-label="Manage deliveries" aria-busy={working}>
  <div className="ds-native-selection-toolbar"><Choice aria-label="Delivery state" value={state} disabled={disabled} options={lifecycleStates} onValueChange={value=>catalog.setFilter('state',value)}/><span aria-live="polite">{count} {count===1?'delivery':'deliveries'} selected{selected.all?' · all matching filters':''}</span>
   <label className="ds-native-page-selection"><Checkbox aria-label="Select deliveries on this page" disabled={disabled||!items.length||selected.all} checked={selected.all||items.length>0&&items.every(item=>selected.ids.includes(item.id))?true:items.some(item=>selected.ids.includes(item.id))?'indeterminate':false} onCheckedChange={checked=>setSelection({...selected,ids:checked?[...new Set([...selected.ids,...items.map(item=>item.id)])]:selected.ids.filter(id=>!items.some(item=>item.id===id))})}/>This page</label>
   <label className="ds-native-page-selection"><Checkbox aria-label={'Select all '+total+' matching deliveries'} disabled={disabled||!total} checked={selected.all} onCheckedChange={checked=>setSelection({key:filterKey,ids:[],all:checked===true,count:checked?total:0})}/>All {total} matching deliveries</label>
   <Hint label="Clear delivery selection" name="Clear delivery selection" disabled={disabled||!count}><Button className="ds-native-icon-action" variant="text" aria-label="Clear delivery selection" disabled={disabled||!count} onClick={()=>setSelection({key:filterKey,ids:[],all:false,count:0})}><Codicon name="clear-all"/></Button></Hint>
  </div>
  <div className="ds-native-selection-toolbar">
   {state==='active'&&<Button disabled={disabled||!count} onClick={()=>run('archive')}><Codicon name="archive"/>Archive selected</Button>}
   {['active','archived'].includes(state)&&<Button disabled={disabled||!count} onClick={()=>run('trash')}><Codicon name="trash"/>Trash selected</Button>}
   {state!=='active'&&<Button disabled={disabled||!count} onClick={()=>run('restore')}><Codicon name="discard"/>Restore selected</Button>}
   {state==='trash'&&<Button disabled={disabled||!total} onClick={()=>setConfirm(true)}>Empty Trash</Button>}
  </div>
  <p className="ds-native-muted">Selection applies to whole deliveries, including all their files and saved versions. {state==='archived'?'Archive is indefinite. Restore any time. Automatic version updates are paused.':state==='trash'?'Trash is recoverable for the configured 30 or 60 days. Automatic version updates are paused.':state==='pending_delete'?'Restore before the displayed deadline. After 60 minutes, preserved copies are irreversibly deleted.':'Archive keeps deliveries indefinitely. Trash is recoverable. Neither deletes your original working files.'}</p>
  {notice&&<div role="status">{notice.text} {notice.undo?.length>0&&<Button disabled={disabled} onClick={()=>run('restore',{ids:notice.undo})}>Undo archive</Button>}</div>}
  {error&&<p role="alert">{error}</p>}
  <EmptyTrashConfirmation open={confirm} busy={disabled} onCancel={()=>setConfirm(false)} onConfirm={()=>run('empty_trash',{filter:{state:'trash'}})}/>
 </section>;
}
