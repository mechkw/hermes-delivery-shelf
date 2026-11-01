// Real host implementations, resolved from the installed checkout read-only.
// Only transport/state/native-OS boundaries are doubles; never UI components.
import {readFile,readdir} from 'node:fs/promises';
import {join} from 'node:path';
import {createRequire} from 'node:module';
export const uiExports={
 'components/ui/button':['Button'], 'components/ui/input':['Input'],
 'components/ui/textarea':['Textarea'],'components/ui/search-field':['SearchField'],
 'components/ui/select':['Select','SelectTrigger','SelectValue','SelectContent','SelectItem'],
 'components/ui/dialog':['Dialog','DialogContent','DialogHeader','DialogTitle','DialogDescription','DialogFooter'],
 'components/ui/tooltip':['Tooltip','TooltipProvider','TooltipTrigger','TooltipContent'],
 'components/ui/tabs':['Tabs','TabsList','TabsTrigger'],
 'components/ui/empty-state':['EmptyState'],'components/ui/error-state':['ErrorState'],
 'components/ui/loader':['Loader'],'app/settings/primitives':['ListRow'],
};
export async function realUI(source){
 const names=Object.values(uiExports).flat(),index=await readFile(join(source,'apps/desktop/src/sdk/index.ts'),'utf8');
 for(const [path,exports] of Object.entries(uiExports))for(const name of exports){
  if(!new RegExp('export\\s*\\{[^}]*\\b'+name+'\\b[^}]*\\}\\s*from\\s*[\'"]@/'+path+'[\'"]','s').test(index))throw Error('Not a public SDK re-export: '+name);
 }
 const imports=Object.entries(uiExports).map(([path,exports])=>`import {${exports.join(',')}} from '${source}/apps/desktop/src/${path}';`).join('\n');
 const assets=join(source,'apps/desktop/dist/assets');
 const nativeCSS=(await Promise.all((await readdir(assets)).filter(n=>n.endsWith('.css')).map(n=>readFile(join(assets,n),'utf8')))).join('\n');
 // Compile the host Dashboard stylesheet with its existing Tailwind toolchain.
 // build.css is a SOURCE file containing @imports, not browser-ready CSS.
 const requireHost=createRequire(join(source,'package.json'));
 const {compile}=requireHost('@tailwindcss/node'),{Scanner}=requireHost('@tailwindcss/oxide');
 const dashboard=join(source,'web/src');
 const compiler=await compile(await readFile(join(dashboard,'index.css'),'utf8'),{base:dashboard,onDependency:()=>{}});
 const scanner=new Scanner({sources:[{base:dashboard,negated:false,pattern:'**/*.{tsx,ts,jsx,js}'},{base:join(source,'node_modules/@nous-research/ui/dist'),negated:false,pattern:'**/*.js'}]});
 const dashCSS=compiler.build(scanner.scan());
 const cssBootstrap=css=>`document.querySelector('style')?.remove();const nativeStyles=document.createElement('style');nativeStyles.textContent=${JSON.stringify(css)};document.head.append(nativeStyles);`;
 return {names,imports,nativeBootstrap:cssBootstrap(nativeCSS),dashboardBootstrap:cssBootstrap(dashCSS)};
}
