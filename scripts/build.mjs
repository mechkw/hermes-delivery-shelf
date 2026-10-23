import {build} from 'esbuild';
const common={bundle:true,minify:true,legalComments:'none',target:'es2020',loader:{'.css':'text'},jsx:'transform'};
await build({...common,entryPoints:['ui/desktop.jsx'],outfile:'desktop/plugin.js',format:'esm',external:['react','@hermes/plugin-sdk']});
await build({...common,entryPoints:['ui/dashboard.jsx'],outfile:'dashboard/dist/index.js',format:'iife',plugins:[{
  name:'host-react',setup(b){
    b.onResolve({filter:/^react$/},()=>({path:'react',namespace:'host-react'}));
    b.onLoad({filter:/.*/,namespace:'host-react'},()=>({contents:'const React=window.__HERMES_PLUGIN_SDK__.React;export default React;export const {useState,useEffect,useRef,useId,useMemo}=React;',loader:'js'}));
  }
}]});
console.log('Built Dashboard IIFE + Desktop ESM (host React only).');
