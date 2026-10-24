import React from 'react';
import {Shelf} from './Shelf.jsx';
import {Saved,SavedLink} from './Saved.jsx';
import {dashboardHub,attachDashboard} from './saved-coordinator.js';
const sdk=window.__HERMES_PLUGIN_SDK__;
const script=document.currentScript;
const profile=script?.getAttribute('data-hermes-profile')||'';
const hub=dashboardHub(profile);
const basePath=new URL(script.src).pathname.split('/dashboard-plugins/')[0];
async function api(path,opts={}) {
  if(!script?.isConnected)throw new Error('Profile changed. Reopen Saved.');
  const suffix=profile ? (path.includes('?')?'&':'?')+'profile='+encodeURIComponent(profile) : '';
  const result=await sdk.fetchJSON('/api/plugins/delivery-shelf'+path+suffix,{
    method:opts.method||'GET',headers:opts.body?{'Content-Type':'application/json'}:undefined,
    body:opts.body?JSON.stringify(opts.body):undefined
  });
  if(!script?.isConnected)throw new Error('Profile changed. Reopen Saved.');
  return result;
}
api.copyText=text=>{if(!script?.isConnected)throw new Error('Profile changed. Reopen Saved.');return navigator.clipboard.writeText(text);};
const provider={id:'delivery-shelf',probe:()=>api('/status'),path:basePath+'/delivery-shelf',Page:()=> <Shelf api={api} embedded/>};
attachDashboard(hub,provider,script,profile);
window.__HERMES_PLUGINS__.register('delivery-shelf',()=> <Saved hub={hub} scope={profile} manage={()=>{window.location.href=basePath+'/plugins';}}/>);
window.__HERMES_PLUGINS__.registerSlot('delivery-shelf','header-banner',()=> <SavedLink hub={hub} id="delivery-shelf"/>);
