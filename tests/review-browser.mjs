import {expect} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {nativeShelf,nativeTitleCases,nativeFocusCases} from './native-shelf-browser.mjs';

export async function sourceDetailCases(page,adapter,api,sourceBank){
 const id='conversation-bookmarks',pattern='**/api/plugins/conversation-bookmarks/status*';
 // Transport-only double verifies that the command uses the reported profile,
 // not the Dashboard launch profile. Actual profile switching is tested separately.
 await page.route(pattern,async route=>{const response=await route.fetch();await route.fulfill({response,json:{...await response.json(),profile:'review-profile'}});});
 await page.context().grantPermissions(['clipboard-read','clipboard-write']);
 await page.getByRole('tab',{name:'Bookmarks',exact:true}).click();
 const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Inspectable source',session_id:'pruned-session',message_id:44})});
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await page.getByRole('button',{name:entry.title,exact:true}).click();
 await expect(dialog.getByLabel('Session ID',{exact:true})).toHaveValue('pruned-session');
 await expect(dialog.getByText('Message ID: 44',{exact:false})).toBeVisible();
 await expect(dialog.getByLabel('Resume in this profile',{exact:true})).toHaveValue("hermes --profile 'review-profile' --resume 'pruned-session'");
 await dialog.getByRole('button',{name:'Copy session ID'}).click();
 await expect.poll(()=>page.evaluate(adapter=>adapter==='desktop'?window.__QA_CLIPBOARD__:navigator.clipboard.readText(),adapter)).toBe('pruned-session');
 if(adapter==='dashboard')await expect(dialog.getByRole('button',{name:'Open conversation'})).toHaveCount(0);
 await page.keyboard.press('Escape');sourceBank.prune();
 await page.getByRole('button',{name:entry.title,exact:true}).click();
 await expect(dialog.getByText('Session unavailable',{exact:true})).toBeVisible();
 await expect(dialog.getByLabel('Session ID',{exact:true})).toHaveValue('pruned-session');
 await expect(dialog.getByText('Message ID: 44',{exact:false})).toBeVisible();
 await dialog.getByRole('button',{name:'Copy session ID'}).click();
 if(adapter==='desktop')await expect(dialog.getByRole('button',{name:'Open conversation'})).toBeDisabled();
 await dialog.getByRole('button',{name:'Edit bookmark'}).click();
 await expect(dialog.getByLabel('Session ID',{exact:true})).toHaveCount(0);
 await expect(dialog.getByLabel('Message ID',{exact:true})).toHaveCount(0);
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 await api(id,`/entries/${entry.id}?revision=${entry.revision}`,{method:'DELETE'});
 sourceBank.restore();await page.unroute(pattern);await page.getByRole('button',{name:'Refresh',exact:true}).click();
 console.log('PASS review source detail',adapter,'exact refs/copy, named-profile resume, pruned refs, no editor ID inputs');
}

// A visible title can belong to the previous list commit: Refresh schedules a
// passive-effect reload which temporarily disconnects every card. Own the active
// collection and observe that reload's loading -> settled commit before measuring.
export async function refreshCollection(page,id){
 const bookmarks=id==='conversation-bookmarks';
 if(!bookmarks&&id!=='delivery-shelf')throw new Error('Unknown Saved collection: '+id);
 const collection=page.locator(bookmarks?'.cb-bookmarks':'.ds-shelf');
 const summary=collection.locator(bookmarks?'.cb-toolbar > span':'.ds-toolbar > span');
 const settled=bookmarks?/^\d+ bookmarks?$/:/^\d+ (delivery|deliveries)$/;
 await expect(collection).toBeVisible();
 await expect(summary).toHaveText(settled);
 // Arm before clicking: polling only after click can miss a fast loading commit.
 const cycle=await summary.evaluateHandle((node,{loading,pattern})=>{
  const state={node,started:false,done:false};
  const observer=new MutationObserver(()=>{
   const text=node.textContent;
   if(text===loading)state.started=true;
   else if(state.started&&new RegExp(pattern).test(text))state.done=true;
  });
  observer.observe(node,{childList:true,subtree:true,characterData:true});
  state.stop=()=>observer.disconnect();return state;
 },{loading:bookmarks?'Loading bookmarks…':'Loading your shelf…',pattern:settled.source});
 try{
  await collection.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.waitForFunction(state=>state.done||!state.node.isConnected,cycle,{timeout:5000});
  expect(await cycle.evaluate(state=>state.node.isConnected)).toBe(true);
  await expect(summary).toHaveText(settled);
 }finally{await cycle.evaluate(state=>state.stop());await cycle.dispose();}
}

export async function titleBoundsCases(page,adapter,api,proof){
 await page.setViewportSize({width:360,height:640});
 const evidence=[];
 for(const id of ['conversation-bookmarks','delivery-shelf']){
  if(nativeShelf(adapter,id)){await nativeTitleCases(page,api,proof);continue;}
  await page.getByRole('tab',{name:id==='conversation-bookmarks'?'Bookmarks':'Deliverables',exact:true}).click();
  await refreshCollection(page,id);
  for(const title of ['UnbrokenTitle'.repeat(12),'A long card title with words that must wrap instead of overflowing the collection card at a narrow viewport '.repeat(2).slice(0,160)]){
   const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title,...(id==='conversation-bookmarks'?{session_id:'fictional-session-01'}:{})})});
   await refreshCollection(page,id);
   const button=page.getByRole('button',{name:title,exact:true});await expect(button).toBeVisible();await button.scrollIntoViewIfNeeded();
   const bounds=await button.evaluate(node=>{
    const range=document.createRange();range.selectNodeContents(node);
    return {button:node.getBoundingClientRect().toJSON(),card:node.closest('article').getBoundingClientRect().toJSON(),text:[...range.getClientRects()].map(r=>r.toJSON()),viewport:innerWidth};
   });
   evidence.push({id,title,...bounds});
   await writeFile(join(proof,`title-bounds-${adapter}.json`),JSON.stringify(evidence,null,2));
   expect(bounds.button.left).toBeGreaterThanOrEqual(bounds.card.left-1);
   expect(bounds.button.right).toBeLessThanOrEqual(bounds.card.right+1);
   expect(bounds.button.right).toBeLessThanOrEqual(360);
   for(const rect of bounds.text){expect(rect.left).toBeGreaterThanOrEqual(bounds.button.left-1);expect(rect.right).toBeLessThanOrEqual(bounds.button.right+1);expect(rect.top).toBeGreaterThanOrEqual(bounds.button.top-1);expect(rect.bottom).toBeLessThanOrEqual(bounds.button.bottom+1);}
   expect(bounds.button.height).toBeGreaterThan(40);
   await page.screenshot({path:join(proof,`title-${adapter}-${id}.png`),fullPage:true});
   await api(id,`/entries/${entry.id}?revision=${entry.revision}`,{method:'DELETE'});
  }
  await refreshCollection(page,id);
 }
 await page.setViewportSize({width:1440,height:1100});
 console.log('PASS review title bounds',adapter,'both panels, worded/unbroken titles, 360px button AND text rects');
}

export async function focusEditorCases(page,adapter,api,proof){
 await page.setViewportSize({width:360,height:640});
 const evidence=[];
 const keyboardActivate=async control=>{await expect(control).toBeEnabled();await control.focus();await expect(control).toBeFocused();await page.keyboard.press('Enter');};
 const footerVisible=async control=>{
  await control.scrollIntoViewIfNeeded();await expect(control).toBeInViewport({ratio:1});
  const rect=await control.boundingBox();expect(rect.y).toBeGreaterThanOrEqual(0);expect(rect.y+rect.height).toBeLessThanOrEqual(640);
  return rect;
 };
 for(const id of ['conversation-bookmarks','delivery-shelf']){
  if(nativeShelf(adapter,id)){await nativeFocusCases(page,api,proof);continue;}
  const bookmarks=id==='conversation-bookmarks';
  await page.getByRole('tab',{name:bookmarks?'Bookmarks':'Deliverables',exact:true}).click();
  const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Keyboard focus regression',...(bookmarks?{session_id:'fictional-session-01'}:{})})});
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  const trigger=page.getByRole('button',{name:entry.title,exact:true}),dialog=page.getByRole('dialog');
  const openEditor=async()=>{await keyboardActivate(trigger);await keyboardActivate(dialog.getByRole('button',{name:bookmarks?'Edit bookmark':'Edit metadata'}));await expect(dialog.getByLabel('Title',{exact:true})).toBeVisible();};
  await openEditor();
  await dialog.getByLabel('Title',{exact:true}).fill(entry.title);
  const cancel=dialog.getByRole('button',{name:'Cancel',exact:true});
  const cancelRect=await footerVisible(cancel);
  await page.screenshot({path:join(proof,`editor-footer-${adapter}-${id}.png`)});
  await keyboardActivate(cancel);await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();
  // Edit Escape and detail Escape return to the same collection trigger.
  await openEditor();await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
  await keyboardActivate(trigger);await expect(dialog.getByRole('button',{name:bookmarks?'Edit bookmark':'Edit metadata'})).toBeEnabled();await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
  await keyboardActivate(trigger);await keyboardActivate(dialog.getByRole('button',{name:bookmarks?'Remove bookmark':'Remove from shelf'}));
  await keyboardActivate(dialog.getByRole('button',{name:bookmarks?'Keep bookmark':'Keep delivery'}));await expect(trigger).toBeFocused();
  // Keyboard traversal stays in the native modal; the short editor genuinely scrolls.
  await openEditor();
  for(let n=0;n<18;n++){await page.keyboard.press('Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
  await dialog.getByLabel(bookmarks?'Note':'Description',{exact:true}).fill('Short viewport saved by keyboard');
  const save=dialog.getByRole('button',{name:'Save changes',exact:true}),saveRect=await footerVisible(save);
  const scrolling=await dialog.evaluate(el=>[el,...el.querySelectorAll('*')].filter(n=>n.scrollHeight>n.clientHeight+1&&['auto','scroll'].includes(getComputedStyle(n).overflowY)).map(n=>({scrollTop:n.scrollTop,clientHeight:n.clientHeight,scrollHeight:n.scrollHeight})));
  // Compact Shelf metadata edits can fit without scrolling. If content does
  // overflow, the footer must be reachable through an actual scroll container.
  if(scrolling.length)expect(scrolling.some(s=>s.scrollTop>0)).toBe(true);
  else {await expect(save).toBeInViewport({ratio:1});await expect(cancel).toBeInViewport({ratio:1});}
  evidence.push({id,cancelRect,saveRect,scrolling});await writeFile(join(proof,`editor-focus-${adapter}.json`),JSON.stringify(evidence,null,2));
  await keyboardActivate(save);await expect(dialog).toHaveCount(0);
  const saved=await api(id,'/entries/'+entry.id);expect(saved[bookmarks?'note':'description']).toBe('Short viewport saved by keyboard');
  // After successful delete the originating card is disconnected: use the
  // connected collection action, never BODY or an outgoing dialog's button.
  await keyboardActivate(trigger);await keyboardActivate(dialog.getByRole('button',{name:bookmarks?'Remove bookmark':'Remove from shelf'}));
  await keyboardActivate(dialog.getByRole('button',{name:'Remove metadata',exact:true}));await expect(dialog).toHaveCount(0);await expect(trigger).toHaveCount(0);
  await expect(page.getByRole('button',{name:bookmarks?'Save bookmark':'Add delivery',exact:true})).toBeFocused();
  expect((await api(id,'/entries')).items.some(x=>x.id===entry.id)).toBe(false);
 }
 await page.setViewportSize({width:1440,height:1100});
 console.log('PASS review focus/editors',adapter,'both panels, 360x640 footer scroll/save/cancel, keyboard trap, detail/edit/remove return, connected delete fallback');
}
