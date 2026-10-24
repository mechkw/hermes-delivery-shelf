import React,{useEffect,useState,useId} from 'react';
import styles from './saved.css';
const features=[
  {id:'conversation-bookmarks',label:'Bookmarks',description:'Keep a reference to a useful conversation, with a title, note and tags.'},
  {id:'delivery-shelf',label:'Deliverables',description:'Keep finished work at hand. Register files without moving or copying them.'}
];
export function useProviders(hub){
  const [,update]=useState(0);
  useEffect(()=>{const changed=()=>update(n=>n+1);hub.listeners.add(changed);changed();return()=>hub.listeners.delete(changed);},[hub]);
  return features.map(f=>hub.providers.get(f.id)).filter(Boolean);
}
// Dashboard exposes ApiError.status; Desktop HTTP errors may cross Electron
// IPC as a message only. Match the host's exact prefix, never arbitrary text.
function availabilityError(error){
  const match=String(error?.message||'').match(/^(?:Error invoking remote method 'hermes:api': Error: )?(\d{3}): /);
  const status=error?.status??error?.statusCode??(match?Number(match[1]):0);
  return status===404?'missing':status===401||status===403?'auth':'error';
}
export function Saved({hub,manage,scope=''}){
  const providers=useProviders(hub),[selected,setSelected]=useState(null),id=useId();
  const [checks,setChecks]=useState({}),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    let active=true;
    setChecks({});
    const timers=[];
    for(const provider of providers){
      let settled=false;
      const finish=state=>{if(!active||settled)return;settled=true;clearTimeout(timer);setChecks(old=>({...old,[provider.id]:{provider,scope,state}}));};
      const timer=setTimeout(()=>finish('error'),12000);timers.push(timer);
      Promise.resolve().then(()=>provider.probe(scope)).then(()=>finish('ready'),error=>finish(availabilityError(error)));
    }
    return()=>{active=false;timers.forEach(clearTimeout);};
  },[hub,scope,providers[0],providers[1],attempt]);
  const stateFor=feature=>{
    const provider=providers.find(p=>p.id===feature.id),check=checks[feature.id];
    return !provider?'missing':check?.provider===provider&&check.scope===scope?check.state:'checking';
  };
  const available=providers.filter(p=>stateFor(p)==='ready');
  const current=available.find(p=>p.id===selected)||available[0];
  const Page=current?.Page;
  return <section className="hs-saved" aria-label="Saved">
    <style>{styles}</style>
    <header className="hs-saved-head"><h1>Saved</h1><p>Conversations to return to. Work to keep.</p></header>
    <div className="hs-saved-tabs" role="tablist" aria-label="Saved collections">
      {features.filter(f=>available.some(p=>p.id===f.id)).map(f=><button key={f.id} role="tab" id={id+f.id} aria-controls={id+'panel'} aria-selected={current?.id===f.id} tabIndex={current?.id===f.id?0:-1} onClick={()=>setSelected(f.id)} onKeyDown={event=>{
        const tabs=[...event.currentTarget.parentElement.querySelectorAll('[role=tab]')],index=tabs.indexOf(event.currentTarget);
        const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:null;
        if(next!==null){event.preventDefault();tabs[next].focus();tabs[next].click();}
      }}>{f.label}</button>)}
    </div>
    {Page&&<div role="tabpanel" id={id+'panel'} aria-labelledby={id+current.id}><Page key={current.id+scope}/></div>}
    <aside className="hs-saved-missing" aria-label="Optional Saved collections">
      {features.filter(f=>stateFor(f)!=='ready').map(f=>{
        const state=stateFor(f),hasUI=providers.some(p=>p.id===f.id);
        return <div key={f.id} aria-label={f.label+' availability'}>
          <p><strong>{f.label}</strong> · {state==='missing'?f.description:state==='checking'?'Checking availability…':state==='auth'?'Access could not be verified. Sign in or check permissions, then retry.':'Could not check availability. Check your connection, then retry.'}</p>
          {state==='missing'&&<button onClick={manage}>Install or enable {f.label.toLowerCase()}</button>}
          {hasUI&&state!=='checking'&&<button onClick={()=>setAttempt(n=>n+1)}>Retry {f.label.toLowerCase()}</button>}
        </div>;
      })}
    </aside>
  </section>;
}
export function SavedLink({hub,id}){
  useProviders(hub);
  const owner=hub.first();
  if(owner?.id!==id)return null;
  return <><style>{styles}</style><a className="hs-saved-link" href={owner.path}>Saved</a></>;
}
