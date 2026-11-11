import React,{useEffect,useRef,useState,useId} from 'react';
import {Button,Input,Textarea,Field,DialogFooter} from '@saved/presentation';
import {createDraft,editField,beginGeneration,invalidateGeneration,applyGeneration} from './metadata-draft.js';
import {metadataFeedback} from './metadata-errors.js';

/** LOCAL adapter contract, not a claim that a host implements these methods.
 * @typedef {{title:string,description:string,tags:string[]}} Metadata
 * @typedef {{requestId:string,ownerKey:string,sourceKey:string,requested_fields:('title'|'description'|'tags')[],supplied_metadata:Partial<Metadata>}} GenerationRequest
 * @typedef {{state:'stopped'|'not_started'|'quarantined',safeToSave:true,canGenerate:boolean}|{state:'unknown'}} StopStatus
 * @typedef {{generate:(request:GenerationRequest)=>Promise<Partial<Metadata>>,cancel:(request:GenerationRequest)=>Promise<StopStatus>,status:(request:GenerationRequest)=>Promise<StopStatus>,save:(request:{ownerKey:string,sourceKey:string,metadata:Metadata,generation_policy:'never'})=>Promise<void>}} MetadataAdapter
 * A resolved generate promise must mean terminal work; rejection is uncertain.
 * cancel/status must certify durable stop or isolated safe quarantine, not UI abort.
 * Identity keys are UI fences, NOT authorization. The adapter owns authentication,
 * authoritative Unicode-14 validation, admission/permits and durable publication.
 * @param {{ownerKey:string,sourceKey:string,initialValues?:Partial<Metadata>,initialProvenance?:Object,generationAllowed:boolean,adapter:MetadataAdapter}} props
 */
export function MetadataForm({ownerKey,sourceKey,initialValues,initialProvenance,generationAllowed=false,adapter}){
 const [,render]=useState(0),id=useId(),operation=useRef(null),mounted=useRef(true),titleInput=useRef(null),descriptionInput=useRef(null),tagsInput=useRef(null);
 const session=useRef(null);
 const fresh=()=>({draft:createDraft(ownerKey,sourceKey,initialValues,initialProvenance),pendingTag:'',tagInputs:[],error:'',notice:'',errorField:null,errorTagIndex:null,focusError:false,invalidResult:false,saving:false,permit:true,recovery:null});
 if(!session.current)session.current=fresh();
 if(session.current.draft.ownerKey!==ownerKey||session.current.draft.sourceKey!==sourceKey){
  // Fence synchronously, before the identity-change effect or a queued response.
  if(operation.current)operation.current.fenced=true;
  session.current=fresh();
 }
 const current=session.current;
 const paint=()=>{if(mounted.current)render(n=>n+1);};
 const isCurrent=op=>mounted.current&&operation.current===op;
 const safe=status=>status&&['stopped','not_started','quarantined'].includes(status.state)&&status.safeToSave===true&&typeof status.canGenerate==='boolean';
 async function checkStop(op,method){
  if(!isCurrent(op)||op.checking)return;
  op.fenced=true;op.checking=true;op.phase='stopping';session.current.notice='';
  session.current.draft=invalidateGeneration(session.current.draft);paint();
  let timer;
  try{
   // A bounded explicit check, never a polling loop or an implicit generation retry.
   const status=await Promise.race([Promise.resolve().then(()=>op.adapter[method](op.request)),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout')),2000);})]);
   if(!isCurrent(op))return;
   if(safe(status)){
    operation.current=null;session.current.error='';
    // Safety may release the global active-work gate, not transfer a permit.
    if(session.current===op.session){session.current.permit=status.canGenerate;session.current.recovery=status.canGenerate?null:op;}
   }
   else{op.phase='unknown';session.current.error='Waiting for generation to stop.';}
  }catch{if(isCurrent(op)){op.phase='unknown';session.current.error='Waiting for generation to stop.';}}
  finally{clearTimeout(timer);op.checking=false;paint();}
 }
 async function checkPermit(s,op){
  if(!mounted.current||session.current!==s||s.recovery!==op||op.checking||s.saving)return;
  const currentCheck=()=>mounted.current&&session.current===s&&s.recovery===op&&!operation.current;
  op.checking=true;s.error='';s.notice='';s.errorField=null;s.errorTagIndex=null;paint();
  let timer;
  try{
   const status=await Promise.race([Promise.resolve().then(()=>op.adapter.status(op.request)),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout')),2000);})]);
   if(!currentCheck())return;
   if(safe(status)&&status.canGenerate){s.permit=true;s.recovery=null;}
   else s.error='Could not confirm generation is available. Check generation status.';
  }catch{if(currentCheck())s.error='Could not confirm generation is available. Check generation status.';}
  finally{clearTimeout(timer);op.checking=false;paint();}
  // Previously certified nongenerating publication stays safe on discovery failure.
 }
 useEffect(()=>{
  const op=operation.current;
  if(op&&(op.request.ownerKey!==ownerKey||op.request.sourceKey!==sourceKey))void checkStop(op,'cancel');
 },[ownerKey,sourceKey]);
 useEffect(()=>{mounted.current=true;return()=>{
  mounted.current=false;
  const op=operation.current;
  if(op){op.fenced=true;operation.current=null;try{Promise.resolve(op.adapter.cancel(op.request)).catch(()=>{});}catch{/* Detached UI cannot establish durable status. */}}
 };},[]);
 function edit(field,value){
  const s=session.current;s.error='';s.notice='';s.errorField=null;s.errorTagIndex=null;s.focusError=false;s.invalidResult=false;
  s.draft=editField(s.draft,field,value);paint();
 }
 // The draft always includes nonempty pending text, so Save and generation see
 // exactly what is on screen. Enter only moves it into the editable tag list.
 const listedTags=()=>session.current.pendingTag.length?session.current.draft.values.tags.slice(0,-1):session.current.draft.values.tags;
 function editTags(tags,pending=session.current.pendingTag){
  session.current.pendingTag=pending;
  edit('tags',pending.length?[...tags,pending]:tags);
 }
 function addTag(){
  if(!session.current.pendingTag.length)return;
  editTags(session.current.draft.values.tags,'');tagsInput.current?.focus();
 }
 function tagKey(event,add=false){
  if(event.key==='Enter'&&!event.nativeEvent.isComposing){event.preventDefault();if(add)addTag();}
 }
 async function generate(){
  const s=session.current;
  if(operation.current||s.saving||!generationAllowed||!s.permit)return;
  const started=beginGeneration(s.draft);if(!started.capture)return;
  s.draft=started.state;s.error='';s.notice='';s.errorField=null;s.errorTagIndex=null;s.invalidResult=false;
  const op={session:s,startedDraft:started.state,capture:started.capture,adapter,request:Object.freeze({requestId:crypto.randomUUID(),ownerKey,sourceKey,...started.request}),phase:'generating',fenced:false,checking:false};
  operation.current=op;paint();
  try{
   const result=await op.adapter.generate(op.request);
   if(!isCurrent(op)||op.phase!=='generating'||op.fenced)return;
   const applied=applyGeneration(session.current.draft,op.capture,result);
   session.current.draft=applied.state;operation.current=null;
   // Validate against the captured draft too: stale malformed output is not an
   // edits-kept event. The pure mapper never applies this validation-only result.
   if(applyGeneration(op.startedDraft,op.capture,result).reason==='invalid_result'){session.current.error='Could not generate details. Try again or edit your entries.';session.current.invalidResult=true;}
   else if(applied.reason==='stale')session.current.notice='Your edits were kept.';
  }catch{
   if(!isCurrent(op)||op.phase!=='generating'||op.fenced)return;
   op.fenced=true;op.phase='unknown';session.current.draft=invalidateGeneration(session.current.draft);
   session.current.error='Could not confirm generation stopped. Check generation status.';
  }finally{paint();}
 }
 async function save(event){
  event.preventDefault();const s=session.current;
  if(operation.current||s.saving||s.invalidResult)return;
  const captured=s;s.saving=true;s.error='';s.notice='';s.errorField=null;s.errorTagIndex=null;paint();
  try{await adapter.save({ownerKey,sourceKey,metadata:{...s.draft.values,tags:[...s.draft.values.tags]},generation_policy:'never'});}
  catch(error){if(session.current===captured){const feedback=metadataFeedback(error);s.error=feedback.message;s.errorField=feedback.field;s.errorTagIndex=feedback.tagIndex;s.focusError=true;}}
  finally{captured.saving=false;paint();}
 }
 useEffect(()=>{
  if(current.focusError&&!current.saving){
   const tag=current.tagInputs[current.errorTagIndex];
   if(current.errorField==='tags'&&Number.isInteger(current.errorTagIndex)&&tag?.isConnected)tag.focus();
   else ({title:titleInput,description:descriptionInput,tags:tagsInput}[current.errorField]||titleInput).current?.focus();
   current.focusError=false;
  }
 });
 const described=field=>current.error&&(!current.errorField||current.errorField===field)?id+'error':undefined;
 const pendingIndex=current.pendingTag.length?current.draft.values.tags.length-1:-1;
 const tagTarget=Number.isInteger(current.errorTagIndex)&&(current.tagInputs[current.errorTagIndex]?.isConnected||current.errorTagIndex===pendingIndex)?current.errorTagIndex:pendingIndex;
 const tagInvalid=index=>Boolean(current.error&&current.errorField==='tags'&&tagTarget===index)||undefined;
 const tagDescribed=index=>tagInvalid(index)||(!current.errorField&&index===pendingIndex)?described('tags'):undefined;
 const op=operation.current,values=current.draft.values,eligible=Boolean(beginGeneration(current.draft).capture);
 const blocked=Boolean(op)||current.saving||current.invalidResult;
 return <form className="hs-metadata-form" onSubmit={save} noValidate aria-label="Delivery metadata">
  <style>{`.hs-metadata-form :is(input,textarea,button):focus-visible{outline:2px solid currentColor;outline-offset:2px}.hs-metadata-tag-list{display:grid;gap:8px;min-width:0}.hs-metadata-tag-row{display:flex;gap:8px;align-items:center;min-width:0}.hs-metadata-tag-row textarea{flex:1;min-width:0}.hs-metadata-form .hs-metadata-tag{min-height:36px;height:36px;resize:none;white-space:pre;overflow:auto}.hs-metadata-form{min-width:0}`}</style>
  <Field title="Title"><Input ref={titleInput} required value={values.title} disabled={current.saving} aria-invalid={Boolean(current.error&&current.errorField==='title')||undefined} aria-describedby={described('title')} onChange={e=>edit('title',e.target.value)}/></Field>
  <Field title="Description"><Textarea ref={descriptionInput} rows={3} value={values.description} disabled={current.saving} aria-invalid={Boolean(current.error&&current.errorField==='description')||undefined} aria-describedby={described('description')} onChange={e=>edit('description',e.target.value)}/></Field>
  <div>
   <Field title="Tags"><Textarea ref={tagsInput} className="hs-dashboard-textarea hs-metadata-tag" rows={1} value={current.pendingTag} disabled={current.saving} aria-invalid={tagInvalid(pendingIndex)} aria-describedby={tagDescribed(pendingIndex)} onChange={e=>editTags(listedTags(),e.target.value)} onKeyDown={e=>tagKey(e,true)}/></Field>
   <div className="hs-metadata-tag-list">
    {listedTags().map((tag,index)=><div className="hs-metadata-tag-row" key={index}>
     <Textarea ref={node=>{current.tagInputs[index]=node;}} className="hs-dashboard-textarea hs-metadata-tag" rows={1} aria-label={'Tag '+(index+1)} value={tag} disabled={current.saving} aria-invalid={tagInvalid(index)} aria-describedby={tagDescribed(index)} onKeyDown={tagKey} onChange={e=>editTags(listedTags().map((value,i)=>i===index?e.target.value:value))}/>
     <Button type="button" aria-label={'Remove tag '+(index+1)} disabled={current.saving} onClick={()=>{editTags(listedTags().filter((_,i)=>i!==index));tagsInput.current?.focus();}}>Remove</Button>
    </div>)}
    <Button type="button" disabled={current.saving||!current.pendingTag.length} onClick={addTag}>Add tag</Button>
   </div>
  </div>
  {current.error&&<p id={id+'error'} role="alert">{current.error}</p>}
  {current.notice&&<p role="status" aria-live="polite">{current.notice}</p>}
  <DialogFooter>
   <Button type="button" disabled={current.saving||op?.phase==='stopping'||current.recovery?.checking||(!op&&!current.recovery&&(!eligible||!generationAllowed||!current.permit))} onClick={()=>op?checkStop(op,op.phase==='unknown'?'status':'cancel'):current.recovery?checkPermit(current,current.recovery):generate()}>
    {op?(op.phase==='generating'?'Stop generating':op.phase==='stopping'?'Stopping generation':'Check generation status'):current.recovery?(current.recovery.checking?'Checking generation status':'Check generation status'):'Generate'}
   </Button>
   <Button variant="default" type="submit" disabled={blocked}>Save</Button>
  </DialogFooter>
 </form>;
}
