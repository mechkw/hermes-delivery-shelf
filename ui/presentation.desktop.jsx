import React,{useId} from 'react';
import {Button as NativeButton,Input,Textarea,SearchField,Select,SelectTrigger,SelectValue,SelectContent,SelectItem,Dialog as NativeDialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogFooter,ListRow,Tabs,TabsList,TabsTrigger,EmptyState,ErrorState as NativeErrorState,Loader} from '@hermes/plugin-sdk';
export {Input,Textarea,SearchField,DialogFooter,EmptyState,Loader};
// This adapter only translates domain props. The host owns control appearance,
// portals, keyboard interaction, focus trapping and disabled/loading treatment.
export function Button({variant='secondary',type='button',loading,children,...props}){return <NativeButton type={type} variant={variant} loading={loading} aria-label={loading&&typeof children==='string'?children:undefined} {...props}>{children}</NativeButton>;}
export function ErrorState(props){return <div role="alert"><NativeErrorState {...props}/></div>;}
export function Field({children,title,description,id:provided,...props}){
 const generated=useId(),id=provided||generated;
 const parts=React.Children.toArray(children),control=parts.find(x=>React.isValidElement(x)&&[Input,Textarea,Choice,SearchField].includes(x.type));
 const label=title||parts.filter(x=>x!==control);
 return <ListRow {...props} title={<label htmlFor={id}>{label}</label>} description={description} action={control?React.cloneElement(control,{id,'aria-label':control.props['aria-label']||(typeof title==='string'?title:undefined)}):undefined}/>;
}
export function Choice({value='',onValueChange,onChange,children,options,id,disabled,placeholder='Choose…','aria-label':label}){
 const items=options||React.Children.toArray(children).filter(React.isValidElement).map(c=>({value:String(c.props.value??c.props.children),label:c.props.children,disabled:c.props.disabled}));
 // Radix reserves an empty string for no selection. Encode all values rather
 // than reserve a domain ID that could collide with a real session.
 const encode=v=>'value:'+String(v);
 return <Select value={encode(value)} disabled={disabled} onValueChange={v=>{const next=v.slice(6);onValueChange?.(next);onChange?.({target:{value:next}});}}>
  <SelectTrigger id={id} aria-label={label}><SelectValue placeholder={placeholder}/></SelectTrigger>
  <SelectContent>{items.map(o=><SelectItem key={o.value} value={encode(o.value)} disabled={o.disabled}><span className="hs-option-label">{o.label}</span></SelectItem>)}</SelectContent>
 </Select>;
}
export function Dialog({title,description='Review saved metadata. Your original source is not changed.',children,close,busy=false,restoreFocus}){
 return <NativeDialog open onOpenChange={open=>{if(!open&&!busy)close();}}><DialogContent showCloseButton={!busy} onCloseAutoFocus={restoreFocus}>
  <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>
  <div className="hs-dialog-body">{children}</div>
 </DialogContent></NativeDialog>;
}
export function CollectionTabs({value,onChange,items,id}){
 return <Tabs value={value||''} onValueChange={onChange}><TabsList aria-label="Saved collections">{items.map(f=><TabsTrigger key={f.id} value={f.id} id={id+f.id} aria-controls={id+'panel'}>{f.label}</TabsTrigger>)}</TabsList></Tabs>;
}
