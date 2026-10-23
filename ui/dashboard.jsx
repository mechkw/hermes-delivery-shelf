import React from 'react';
import {Shelf} from './Shelf.jsx';
const sdk=window.__HERMES_PLUGIN_SDK__;
const script=document.currentScript;
const profile=script?.getAttribute('data-hermes-profile');
async function api(path, opts={}) {
  if(script && !script.isConnected)throw new Error('Profile changed. Reopen Delivery Shelf.');
  const suffix=profile ? (path.includes('?')?'&':'?')+'profile='+encodeURIComponent(profile) : '';
  const result=await sdk.fetchJSON('/api/plugins/delivery-shelf'+path+suffix,{
    method:opts.method||'GET',headers:opts.body?{'Content-Type':'application/json'}:undefined,
    body:opts.body?JSON.stringify(opts.body):undefined
  });
  if(script && !script.isConnected)throw new Error('Profile changed. Reopen Delivery Shelf.');
  return result;
}
api.copyText=text=>navigator.clipboard.writeText(text);
window.__HERMES_PLUGINS__.register('delivery-shelf',()=> <Shelf api={api}/>);
