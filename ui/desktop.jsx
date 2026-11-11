import React, {useMemo} from 'react';
import {host, useValue, atom, COMPOSER_AREAS, TITLEBAR_AREAS, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA} from '@hermes/plugin-sdk';
import {NativeShelf} from './NativeShelf.jsx';
import {NativeShelfSettings} from './NativeSettings.jsx';
import {createShelfApi,scopeKey} from './native-chat-shelf.js';
import {Saved} from './Saved.jsx';
import {desktopHub} from './saved-coordinator.js';

// Exact forms only: never claim arbitrary /shelf arguments or surrounding prose.
const shelfCommandForms=['/shelf'];

export default {
  id:'delivery-shelf', name:'Delivery Shelf',
  register(ctx) {
    let disposed=false,opening=0;
    const hub=desktopHub(host);
    const modal=atom(null),retained=new Map(),typedRetained=new Map();
    function openShelf(chooseSource=false) {
      // Typed middleware has no originating chat. Use only the explicit
      // browsing connection/profile and require a blank conversation choice.
      const owner=chooseSource?{connectionId:host.state.connectionId.get(),profile:host.state.profile.get()||'default'}:host.state.focusedSessionOwner.get();
      const sessionId=chooseSource?'':host.state.focusedStoredSessionId.get()||'';
      if(!owner||!owner.connectionId||owner.connectionId!==host.state.connectionId.get()){
        host.notify({kind:'error',message:'The conversation source is unavailable.'});return;
      }
      const identity={...owner,sessionId};
      const key=scopeKey(identity),stash=chooseSource?typedRetained:retained;
      // Re-confirm the source on typed reopening without discarding human text.
      if(chooseSource&&stash.has(key))stash.set(key,{...stash.get(key),session_id:'',selections:[]});
      // A new invocation returns to Add instead of reopening old entry details;
      // the owner-scoped external stash retains all human metadata and files.
      modal.set({identity,key,opening:++opening,api:createShelfApi(ctx,host,owner,()=>disposed),open:true,chooseSource,retained:stash});
    }
    function ChatModal() {
      const request=useValue(modal),connection=useValue(host.state.connectionId),owner=useValue(host.state.focusedSessionOwner),session=useValue(host.state.focusedStoredSessionId),profile=useValue(host.state.profile);
      if(!request)return null;
      const visible=request.open&&connection===request.identity.connectionId&&(request.chooseSource?profile===request.identity.profile:owner?.profile===request.identity.profile&&(session||'')===request.identity.sessionId);
      return <NativeShelf key={request.opening} api={request.api} ownerKey={request.key} sessionId={request.identity.sessionId} retained={request.retained} initialView={request.chooseSource?'library':'add'} open={visible} onClose={()=>modal.set({...modal.get(),open:false})}/>;
    }
    ctx.registerMany([
      {id:'attach-delivery-shelf',area:COMPOSER_AREAS.attachments,data:{label:'Delivery Shelf',icon:'archive',run:()=>openShelf()}},
      {id:'shelf-command-guard',area:COMPOSER_AREAS.middleware,data:{handler:draft=>{
        if(!shelfCommandForms.includes(draft.text))return draft;
        // Official ComposerDraft has text + attachments, NOT the originating
        // session/owner. This also runs for queued/background sends: sampling
        // focused state here could open another conversation's files. Cancel,
        // retain the host's draft/attachments, and require explicit selection.
        // Host middleware treats throws as pass-through, so notification errors
        // must never turn this local command into a model prompt.
        try{openShelf(true);}catch{}
        return null;
      }}},
      {id:'add-delivery-shelf',area:PALETTE_AREA,data:{id:'add-delivery-shelf',label:'Add delivery to Shelf',keywords:['saved','delivery','file','/shelf add'],detail:()=> 'Choose files and save a delivery',run:()=>openShelf()}},
      // The permanent SDK mount renders ONLY a native Dialog portal; no bar,
      // sidebar, URL, DOM interception, or duplicate portal per chat tile.
      {id:'delivery-shelf-dialog',area:TITLEBAR_AREAS.center,render:()=> <ChatModal/>}
    ]);
    function useProfileApi() {
      const profile=useValue(host.state.profile);
      const connection=useValue(host.state.connectionId);
      const api=useMemo(()=>{const valid=()=>!disposed && host.state.profile.get()===profile && host.state.connectionId.get()===connection;
        const request=async(path,opts={})=>{
          if(!valid())throw new Error('Connection changed. Reopen Saved.');
          const result=await ctx.rest(path+(path.includes('?')?'&':'?')+'profile='+encodeURIComponent(profile||'default'),opts);
          if(!valid())throw new Error('Connection changed. Reopen Saved.');
          return result;
        };
        request.copyText=async(text)=>{if(!valid() || !await ctx.os.writeClipboard(text))throw new Error('Copy unavailable');};
        request.desktop=true;
        request.openSession=(id,sourceProfile)=>{if(valid())host.openSession(id,{profile:sourceProfile||profile});};
        return request;
      },[profile,connection]);
      return {api,key:JSON.stringify([connection,profile,'saved'])};
    }
    function SettingsPage(){const {api,key}=useProfileApi();return <NativeShelfSettings key={key} api={api}/>;}
    ctx.registerSettingsPage({id:'delivery-shelf',title:'Delivery Shelf',icon:'archive',render:()=> <SettingsPage/>});
    function Page() {
      const {api,key}=useProfileApi();
      return <NativeShelf key={key} ownerKey={key} sessionId={host.state.focusedStoredSessionId.get()||''} api={api} retained={retained} modal={false} initialView="library"/>;
    }
    function Panel() {
      const profile=useValue(host.state.profile),connection=useValue(host.state.connectionId);
      const scope=JSON.stringify([profile,connection]);
      return <Saved key={scope} hub={hub} scope={scope} manage={()=>host.navigate('/capabilities?tab=plugins')}/>;
    }
    const probe=async(scope)=>{
      const [profile,connection]=JSON.parse(scope);
      const valid=()=>!disposed&&host.state.profile.get()===profile&&host.state.connectionId.get()===connection;
      if(!valid())throw new Error('Connection changed. Reopen Saved.');
      const status=await ctx.rest('/status?profile='+encodeURIComponent(profile||'default'));
      if(!valid())throw new Error('Connection changed. Reopen Saved.');
      return status;
    };
    const provider={id:'delivery-shelf',Page,probe,claim:()=>ctx.registerMany([
      {id:'saved-page',area:ROUTES_AREA,title:'Saved',data:{path:'/saved'},render:()=> <Panel/>},
      {id:'saved-nav',area:SIDEBAR_NAV_AREA,data:{path:'/saved',label:'Saved',codicon:'bookmark'}}
    ])};
    // Fence requests first, then retire provider and transfer route ownership.
    let detach=()=>{};
    ctx.onDispose(()=>{disposed=true;detach();});
    detach=hub.add(provider);
  }
};
