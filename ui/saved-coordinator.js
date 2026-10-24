// Shared protocol v1, mirrored verbatim in both independent packages.
// This is plugin-owned UI coordination, never the host's private registry.
const key=Symbol.for('hermes.saved.ui.v1');
const hubs=globalThis[key] ||= {desktop:new WeakMap(),dashboard:new Map()};
function createHub(){
  const hub={providers:new Map(),listeners:new Set(),owner:null,release:null};
  hub.notify=()=>{for(const fn of [...hub.listeners])fn();};
  hub.first=()=>[...hub.providers.values()].sort((a,b)=>a.id.localeCompare(b.id))[0];
  hub.elect=()=>{
    const next=hub.first();
    if(hub.owner===next)return;
    // Retire before handing over: never two live route/navigation owners.
    hub.release?.();hub.release=null;hub.owner=next;
    if(next?.claim)hub.release=next.claim();
  };
  hub.add=provider=>{
    if(hub.providers.has(provider.id))throw new Error('Saved provider already registered: '+provider.id);
    hub.providers.set(provider.id,provider);
    try{hub.elect();hub.notify();}catch(error){hub.providers.delete(provider.id);hub.elect();throw error;}
    let active=true;
    return ()=>{if(!active)return;active=false;hub.providers.delete(provider.id);hub.elect();hub.notify();};
  };
  return hub;
}
export function desktopHub(host){
  if(!hubs.desktop.has(host))hubs.desktop.set(host,createHub());
  return hubs.desktop.get(host);
}
export function dashboardHub(profile){
  if(!hubs.dashboard.has(profile))hubs.dashboard.set(profile,createHub());
  return hubs.dashboard.get(profile);
}
export function attachDashboard(hub,provider,script,profile){
  const remove=hub.add(provider);
  // The native Dashboard removes profile-owned scripts on profile change.
  // Observe only our script's lifetime; never edit host DOM or its registry.
  const observer=new MutationObserver(()=>{if(!script?.isConnected){
    remove();observer.disconnect();
    if(!hub.providers.size && hubs.dashboard.get(profile)===hub)hubs.dashboard.delete(profile);
  }});
  observer.observe(document.body,{childList:true});
  return remove;
}
