import React, {useMemo} from 'react';
import {host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA} from '@hermes/plugin-sdk';
import {Shelf} from './Shelf.jsx';
import {Saved} from './Saved.jsx';
import {desktopHub} from './saved-coordinator.js';

export default {
  id:'delivery-shelf', name:'Delivery Shelf',
  register(ctx) {
    let disposed=false;
    const hub=desktopHub(host);
    function Page() {
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
        request.openSession=id=>{if(valid())host.openSession(id);};
        return request;
      },[profile,connection]);
      return <Shelf key={JSON.stringify([profile,connection])} api={api} embedded/>;
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
