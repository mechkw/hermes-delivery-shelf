import React,{useId,useState} from 'react';
const SDK=window.__HERMES_PLUGIN_SDK__;
const C=SDK.components;
export const Input=C.Input,DialogFooter=C.DialogFooter;
export function Button({variant='secondary',type='button',loading,disabled,children,...props}){
 return <C.Button {...props} type={type} size="sm" destructive={variant==='destructive'} ghost={['ghost','text','chip'].includes(variant)} outlined={variant==='secondary'} disabled={disabled||loading} aria-busy={loading||undefined}>{children}</C.Button>;
}
// The legacy SDK does not export Textarea, SearchField or ListRow. Keep those
// fallbacks here, never in the Desktop bundle or as a second runtime.
export function Textarea(props){return <textarea className="hs-dashboard-textarea" {...props}/>;}
export function SearchField({value,onChange,placeholder,'aria-label':label,id,onKeyDown}){return <C.Input id={id} onKeyDown={onKeyDown} type="search" aria-label={label||placeholder} placeholder={placeholder} value={value} onChange={e=>onChange(e.target.value)}/>;}
export function Field({children,title,description,id:provided}){
 const generated=useId(),id=provided||generated;
 const parts=React.Children.toArray(children),control=parts.find(x=>React.isValidElement(x)&&[Input,Textarea,Choice,SearchField].includes(x.type));
 return <div className="hs-field"><label htmlFor={id}>{title||parts.filter(x=>x!==control)}</label>{description&&<p>{description}</p>}{control&&React.cloneElement(control,{id,'aria-label':control.props['aria-label']||(typeof title==='string'?title:parts.filter(x=>typeof x==='string').join('').trim())})}</div>;
}
export function Choice({value='',onValueChange,onChange,children,options,id,disabled,placeholder='Choose…','aria-label':label}){
 const items=options||React.Children.toArray(children).filter(React.isValidElement).map(c=>({value:String(c.props.value??c.props.children),label:c.props.children,disabled:c.props.disabled}));
 // Dashboard Select does not forward aria-label and puts its id on a div.
 // A surrounding semantic label labels its internal button without DOM edits.
 return <label className="hs-choice-label" onClick={event=>event.preventDefault()} onKeyDown={event=>{if(event.key==='Escape'&&event.currentTarget.querySelector('[role="listbox"]'))event.stopPropagation();}}><span className="hs-sr-only">{label||placeholder}</span><C.Select id={id} value={String(value)} placeholder={placeholder} disabled={disabled} onValueChange={v=>{onValueChange?.(v);onChange?.({target:{value:v}});}}>{items.filter(o=>!o.disabled||o.value===value).map(o=><C.SelectOption key={o.value} value={o.value}>{String(o.label)}</C.SelectOption>)}</C.Select></label>;
}
// Dashboard SDK has no public Tooltip. This local adapter provides hover,
// keyboard focus and Escape semantics without private component imports.
export function Hint({label,disabled,name,children}){
 const id=useId(),[open,setOpen]=useState(false);
 return <span className="hs-hint-anchor" tabIndex={disabled?0:undefined} aria-label={disabled?name+' unavailable':undefined} aria-describedby={disabled?id:undefined} onMouseEnter={()=>setOpen(true)} onMouseLeave={()=>setOpen(false)} onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onKeyDown={e=>{if(e.key==='Escape'&&open){e.preventDefault();e.stopPropagation();setOpen(false);}}}>
  {React.cloneElement(children,{'aria-describedby':disabled?undefined:id})}
  <span id={id} hidden={!open} data-state={open?'open':'closed'} role="tooltip" className="hs-dashboard-tooltip ds-dashboard-tooltip">{label}</span>
 </span>;
}
export function Dialog({title,description='Review saved metadata. Your original source is not changed.',children,close,busy=false,restoreFocus}){
 return <C.Dialog open onOpenChange={open=>{if(!open&&!busy)close();}}><C.DialogContent className="hs-dashboard-dialog" onEscapeKeyDown={event=>{if(event.target.closest('[role="dialog"]')?.querySelector('[role="listbox"],[role="tooltip"]:not([hidden])'))event.preventDefault();}} showCloseButton={!busy} onCloseAutoFocus={restoreFocus}><C.DialogHeader><C.DialogTitle>{title}</C.DialogTitle>{description&&<C.DialogDescription>{description}</C.DialogDescription>}</C.DialogHeader><div className="hs-dialog-body">{children}</div></C.DialogContent></C.Dialog>;
}
export function CollectionTabs({value,onChange,items,id}){
 return <C.Tabs defaultValue={value||''}>{()=> <C.TabsList role="tablist" aria-label="Saved collections">{items.map(f=><C.TabsTrigger key={f.id} value={f.id} active={value===f.id} role="tab" id={id+f.id} aria-controls={id+'panel'} aria-selected={value===f.id} tabIndex={value===f.id?0:-1} onClick={()=>onChange(f.id)} onKeyDown={e=>{
 const i=items.findIndex(x=>x.id===f.id),next=e.key==='Home'?0:e.key==='End'?items.length-1:e.key==='ArrowRight'?(i+1)%items.length:e.key==='ArrowLeft'?(i+items.length-1)%items.length:null;
 if(next!==null){e.preventDefault();onChange(items[next].id);document.getElementById(id+items[next].id)?.focus();}
 }}>{f.label}</C.TabsTrigger>)}</C.TabsList>}</C.Tabs>;
}
export function EmptyState({title,description}){return <div className="hs-empty"><h3>{title}</h3><p>{description}</p></div>;}
export function ErrorState({title,description,children}){return <div role="alert" className="hs-empty"><h3>{title}</h3><p>{description}</p>{children}</div>;}
export function Loader({label='Loading'}){return <p role="status">{label}…</p>;}
