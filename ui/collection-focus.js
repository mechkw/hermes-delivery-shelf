import {useRef} from 'react';

// The collection owns focus for the entire detail → edit/remove flow. An
// outgoing modal must neither become the return target nor steal autofocus
// from its replacement. Never move focus into a retired profile's collection.
export function useCollectionFocus(open){
 const collection=useRef(null),trigger=useRef(null),isOpen=useRef(open);
 isOpen.current=open;
 return {
  ref:collection,
  capture(event){
   if(!isOpen.current){const target=event.target.closest('[data-dialog-trigger]');if(target&&collection.current?.contains(target))trigger.current=target;}
  },
  restore(event){
   if(isOpen.current&&collection.current?.isConnected){event.preventDefault();return;}
   const target=trigger.current?.isConnected&&!trigger.current.disabled?trigger.current:collection.current?.querySelector('[data-collection-fallback]:not(:disabled)');
   if(target?.isConnected){target.focus();if(document.activeElement===target)event.preventDefault();}
  }
 };
}
