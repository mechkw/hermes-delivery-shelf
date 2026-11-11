// Fictional transport only. ReactDOM and presentation controls are real.
import React from 'react';
import {createRoot} from 'react-dom/client';
import {MetadataForm} from '../../../ui/MetadataForm.jsx';
import css from '../../../ui/saved.css';
import styles from '../../../ui/style.css';
const sheet=document.createElement('style');sheet.textContent=css+'\n'+styles+'\nmain{max-width:580px;margin:auto;padding:20px}form{display:grid;gap:16px}textarea,input{max-width:100%;box-sizing:border-box}';document.head.append(sheet);
const calls=[],saves=[],cancels=[],checks=[];
let cancelResult={state:'stopped',safeToSave:true,canGenerate:true},statusResult=cancelResult;
let saveError=null;
const adapter={
 generate(request){return new Promise((resolve,reject)=>calls.push({request,resolve,reject}));},
 cancel(request){cancels.push(request);return cancelResult==='hang'?new Promise(()=>{}):Promise.resolve(cancelResult);},
 status(request){checks.push(request);return statusResult==='hang'?new Promise(()=>{}):Promise.resolve(statusResult);},
 save(request){saves.push(request);return saveError?Promise.reject(saveError):Promise.resolve();}
};
let setProps;
function App(){const [props,update]=React.useState({ownerKey:'fixture-owner',sourceKey:'fixture-file',initialValues:{title:'',description:'',tags:[]}});setProps=update;return <main><h1>Metadata form fixture</h1><p>Fictional adapter — no backend, model, native host or OS integration.</p><MetadataForm {...props} generationAllowed={true} adapter={adapter}/></main>;}
createRoot(document.getElementById('root')).render(<App/>);
window.fixture={calls,saves,cancels,checks,saveError(value){saveError=value;},reset(props){setProps(p=>({...p,...props}));},resolve(index,value){calls[index].resolve(value);},reject(index){calls[index].reject(Error('PRIVATE backend text'));},cancel(value){cancelResult=value;},status(value){statusResult=value;}};
