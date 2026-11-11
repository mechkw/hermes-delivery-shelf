// Current Desktop replaces the legacy card/detail dialogs with NativeShelf.
// These are behavioral replacements, not omitted Desktop cases. All controls,
// loader code, persistence and reads use the real components/authenticated API.
import {expect} from '@playwright/test';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export const nativeShelf=(adapter,id)=>adapter==='desktop'&&id==='delivery-shelf';
export const entryButton=(page,adapter,id,title)=>page.getByRole('button',{name:nativeShelf(adapter,id)?'Open delivery '+title:title,exact:true});
export const entrySurface=(page,adapter,id)=>nativeShelf(adapter,id)?page.getByRole('region',{name:'Delivery details',exact:true}):page.getByRole('dialog');
export async function returnToShelf(page,adapter,id){
 if(nativeShelf(adapter,id))await page.getByRole('button',{name:'Back to shelf',exact:true}).click();
}
export async function nativeRefresh(page){
 // NativeShelf refresh is expressed by its retained query/filter controls.
 // Wait for an actual settled response, not an old visible title.
 const listing=r=>r.url().includes('/api/plugins/delivery-shelf/entries?')&&r.request().method()==='GET';
 const filtered=page.waitForResponse(listing);
 await page.getByRole('textbox',{name:'Search deliveries',exact:true}).fill('__qa_refresh_no_match__');await filtered;
 const response=page.waitForResponse(listing);await page.getByRole('button',{name:'Clear filters',exact:true}).click();await response;
 await expect(page.locator('.ds-native-toolbar')).toContainText(/\d+ deliver(y|ies) ·/);
}
const choose=async(page,label,name)=>{await page.getByRole('combobox',{name:label,exact:true}).click();await page.getByRole('option',{name,exact:true}).click();};
const dialog=page=>page.getByRole('dialog');
const closeAdd=async page=>{await dialog(page).getByRole('button',{name:'Close',exact:true}).click();await expect(dialog(page)).toHaveCount(0);};
async function openAdd(page){await page.getByRole('button',{name:'Add delivery',exact:true}).click();await expect(dialog(page).getByRole('form',{name:'Add delivery',exact:true})).toBeVisible();}
async function meadow(page,file='meadow.md'){
 await dialog(page).getByRole('textbox',{name:'Find conversation',exact:true}).fill('Meadow');
 await choose(page,'Conversation','Meadow deliverables');
 await dialog(page).getByRole('button',{name:file,exact:true}).click();
}
const requestWrites=page=>page.evaluate(()=>window.__QA_REQUESTS__.filter(r=>r.method!=='GET'&&!r.path.includes('/thumbnail')).length);

export async function nativeRedesignCases(page,api,proof){
 const id='delivery-shelf',pattern='**/api/plugins/delivery-shelf/generation/draft*';
 await page.getByRole('tab',{name:'Deliverables',exact:true}).click();
 await openAdd(page);const editor=dialog(page),writes=await requestWrites(page);
 await expect(editor.getByRole('combobox',{name:'Previous exchanges',exact:true})).toContainText('10');
 await editor.getByRole('textbox',{name:'Find conversation',exact:true}).fill('Meadow');
 await editor.getByRole('textbox',{name:'Find conversation',exact:true}).press('Enter');
 await expect(editor).toBeVisible();expect(await requestWrites(page)).toBe(writes);
 await choose(page,'Conversation','Meadow deliverables');
 for(const name of ['meadow.md','meadow.png','bundle.zip'])await expect(editor.getByRole('button',{name,exact:true})).toBeVisible();
 await editor.getByRole('button',{name:'meadow.md',exact:true}).click();
 expect(await requestWrites(page)).toBe(writes);
 // A different window persists context, but cannot change this request's value.
 const other=await page.context().newPage();await other.goto(page.url());
 await other.getByRole('tab',{name:'Deliverables',exact:true}).click();await openAdd(other);
 await choose(other,'Previous exchanges','50');
 await expect.poll(async()=>(await api(id,'/generation/settings')).previous_exchanges).toBe(50);
 await expect(editor.getByRole('combobox',{name:'Previous exchanges',exact:true})).toContainText('10');
 let generated=[];
 await page.route(pattern,async route=>{generated.push(route.request().postDataJSON());await route.fulfill({json:{draft:{title:'Meadow survey',description:'Fictional survey: three swallows.',tags:['meadow','survey']},context:{content_mode:'text',truncated:false}}});});
 await editor.getByRole('button',{name:'Generate',exact:true}).click();
 await expect(editor.getByRole('textbox',{name:'Title',exact:true})).toHaveValue('Meadow survey');
 expect(generated[0].previous_exchanges).toBe(10);
 expect((await api(id,'/generation/settings')).previous_exchanges).toBe(50);
 await closeAdd(other);await other.close();
 await choose(page,'Previous exchanges','20');
 await expect.poll(async()=>(await api(id,'/generation/settings')).previous_exchanges).toBe(20);
 await editor.getByRole('combobox',{name:'Previous exchanges',exact:true}).click();
 for(const n of ['5','10','20','50'])await expect(page.getByRole('option',{name:n,exact:true})).toBeVisible();
 await page.keyboard.press('Escape');await expect(editor).toBeVisible();
 const before=(await api(id,'/entries')).total;
 await page.setViewportSize({width:360,height:640});
 const save=editor.getByRole('button',{name:'Save',exact:true});await save.scrollIntoViewIfNeeded();await expect(save).toBeInViewport({ratio:1});
 for(let n=0;n<18;n++){await page.keyboard.press('Tab');expect(await editor.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
 await page.screenshot({path:join(proof,'shelf-new-editor-desktop.png')});
 await save.focus();await page.keyboard.press('Enter');await expect(editor).toHaveCount(0);
 const detail=entrySurface(page,'desktop',id);await expect(detail).toBeVisible();
 const saved=(await api(id,'/entries?q=Meadow%20survey')).items[0];
 expect(saved.file.path).toBe('meadow.md');expect(saved.versions).toHaveLength(1);
 expect(saved.versions[0].files).toHaveLength(1);expect((await api(id,'/entries')).total).toBe(before+1);
 await returnToShelf(page,'desktop',id);await page.setViewportSize({width:1440,height:1100});
 // Dismiss/reopen retains exact human text and file selection, without a write.
 await openAdd(page);await expect(editor.getByRole('textbox',{name:'Title',exact:true})).toHaveValue('Meadow survey');
 await expect(editor.getByRole('button',{name:'meadow.md',exact:true})).toHaveAttribute('aria-pressed','true');
 await editor.getByRole('button',{name:'Clear selection',exact:true}).click();
 await editor.getByRole('button',{name:'bundle.zip',exact:true}).click();await expect(editor.getByLabel('ZIP file',{exact:true})).toBeVisible();
 await closeAdd(page);expect((await api(id,'/entries')).total).toBe(before+1);
 await page.unroute(pattern);
 // Existing generated fields remain user-controlled. Clear fields explicitly
 // before asking for another blank-only generation.
 await openAdd(page);await editor.getByRole('button',{name:'Clear selection',exact:true}).click();await editor.getByRole('button',{name:'meadow.md',exact:true}).click();
 await editor.getByRole('textbox',{name:'Title',exact:true}).fill('');await editor.getByRole('textbox',{name:'Description',exact:true}).fill('');
 while(await editor.getByRole('button',{name:/^Remove tag \d+$/}).count())await editor.getByRole('button',{name:/^Remove tag \d+$/}).first().click();
 let errors=0;await page.route(pattern,route=>{errors++;return route.fulfill({status:502,json:{detail:'Fictional model error'}});});
 await editor.getByRole('button',{name:'Generate',exact:true}).click();await expect(editor.getByRole('alert')).toContainText('Fictional model error');expect(errors).toBe(1);await expect(editor.getByRole('button',{name:'Save',exact:true})).toBeEnabled();await page.unroute(pattern);
 let release,seen;const held=new Promise(r=>release=r),entered=new Promise(r=>seen=r);
 await page.route(pattern,async route=>{seen();await held;await route.fulfill({json:{draft:{title:'STALE DRAFT',description:'stale',tags:[]},context:{content_mode:'text'}}});});
 await editor.getByRole('button',{name:'Generate',exact:true}).click();await entered;
 await editor.getByRole('textbox',{name:'Title',exact:true}).fill('My edit wins');release();
 await expect(editor.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();
 await expect(editor.getByRole('textbox',{name:'Title',exact:true})).toHaveValue('My edit wins');await page.unroute(pattern);
 let releaseFile,seenFile;const heldFile=new Promise(r=>releaseFile=r),enteredFile=new Promise(r=>seenFile=r);
 await page.route(pattern,async route=>{seenFile();await heldFile;await route.fulfill({json:{draft:{description:'WRONG FILE'},context:{content_mode:'text'}}});});
 await editor.getByRole('button',{name:'Generate',exact:true}).click();await enteredFile;
 await editor.getByRole('button',{name:'Clear selection',exact:true}).click();await editor.getByRole('button',{name:'meadow.png',exact:true}).click();releaseFile();
 await expect(editor.getByRole('button',{name:'Generate',exact:true})).toBeEnabled();await expect(editor.getByRole('textbox',{name:'Description',exact:true})).toHaveValue('');await page.unroute(pattern);await closeAdd(page);
 // Real authenticated source failures and retry. A fresh mount has no retained
 // stale chooser response to confuse an error with an empty result.
 const sources='**/api/plugins/delivery-shelf/sources/sessions?**';
 await page.route(sources,route=>route.fulfill({status:503,json:{detail:'Fictional source outage'}}));
 await openAdd(page);await expect(editor.getByRole('alert')).toContainText('Fictional source outage');await page.unroute(sources);
 await editor.getByRole('button',{name:'Retry',exact:true}).click();await choose(page,'Conversation','Meadow deliverables');
 await editor.getByRole('button',{name:'Clear selection',exact:true}).click();
 await editor.getByRole('textbox',{name:'Find delivered file',exact:true}).fill('no-matching-file');
 await expect(editor.getByText('No delivered files',{exact:true})).toBeVisible();await expect(editor.getByRole('button',{name:'Generate',exact:true})).toBeDisabled();await closeAdd(page);
 // Gallery, native raster thumbnail and exact-edition download are the current
 // equivalents of the retired image overlay/Chat card.
 const candidates=(await api(id,'/sources/sessions/fictional-files/artifacts')).items;
 const image=candidates.find(x=>x.name==='meadow.png');
 const imageEntry=await api(id,'/sources/register',{method:'POST',body:JSON.stringify({title:'Fictional meadow illustration',description:'A fictional image for gallery QA.',session_id:'fictional-files',file:image.file,source:image.source,kind:'image',tags:['meadow']})});
 await nativeRefresh(page);await page.getByRole('button',{name:'Gallery',exact:true}).click();
 const card=page.locator('article').filter({has:page.getByRole('button',{name:'Preview meadow.png',exact:true})});
 await expect(card.getByRole('img',{name:'meadow.png',exact:true})).toHaveJSProperty('naturalWidth',180);
 const downloading=page.waitForEvent('download');await card.getByRole('button',{name:'Download meadow.png',exact:true}).click();expect((await downloading).suggestedFilename()).toBe('meadow.png');
 await card.getByRole('button',{name:'Preview meadow.png',exact:true}).click();
 await expect(entrySurface(page,'desktop',id)).toBeVisible();
 await page.getByRole('button',{name:'Open original conversation',exact:true}).click();expect(await page.evaluate(()=>window.__QA_OPENED__.id)).toBe('fictional-files');
 await page.screenshot({path:join(proof,'shelf-thumbnail-gallery.png'),fullPage:true});await returnToShelf(page,'desktop',id);
 await page.getByRole('button',{name:'Together',exact:true}).click();
 for(const item of [saved,imageEntry])await api(id,`/entries/${item.id}?revision=${item.revision}`,{method:'DELETE'});
 await api(id,'/generation/settings',{method:'PUT',body:JSON.stringify({previous_exchanges:10})});await nativeRefresh(page);
 console.log('PASS Shelf redesign desktop NativeShelf: actual multi-file chooser, request-bound 5/10/20/50, no autosave, exact save/readback/cancel, errors, edits/file fences, native keyboard trap, 360x640, gallery/download/provenance');
}

let metadataCase=0;
export async function nativeMetadataCases(page,api){
 const id='delivery-shelf',tags=['design, decisions','say "hello"','café 日本語'];
 const seeded=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Native metadata regression '+(++metadataCase),tags,file:{root:'workspaces',path:'example.md'},session_id:'fictional-session-01'})});
 await page.getByRole('tab',{name:'Deliverables',exact:true}).click();await nativeRefresh(page);
 const open=()=>entryButton(page,'desktop',id,seeded.title).click(),detail=entrySurface(page,'desktop',id);
 await open();await detail.getByRole('button',{name:'Preview text',exact:true}).click();await expect(detail.locator('pre')).not.toBeEmpty();await expect(detail.locator('pre script')).toHaveCount(0);
 const downloading=page.waitForEvent('download');await detail.getByRole('button',{name:seeded.versions?.length?'Download example.md, version 1':'Download file',exact:true}).click();expect((await downloading).suggestedFilename()).toBe('example.md');
 await detail.getByRole('button',{name:'Edit metadata',exact:true}).click();await detail.getByRole('textbox',{name:'Description',exact:true}).fill('Only metadata changed.');await detail.getByRole('button',{name:'Save changes',exact:true}).click();
 await expect(detail.getByRole('button',{name:'Edit metadata',exact:true})).toBeVisible();
 let current=await api(id,'/entries/'+seeded.id);expect(current.tags).toEqual(tags);expect(current.description).toBe('Only metadata changed.');
 expect((await api(id,'/entries?tag='+encodeURIComponent(tags[0]))).items.map(x=>x.id)).toEqual([seeded.id]);
 await detail.getByRole('button',{name:'Edit metadata',exact:true}).click();
 await detail.getByRole('textbox',{name:'Tag 1',exact:true}).fill('changed, intact');await detail.getByRole('button',{name:'Remove tag 2',exact:true}).click();
 await choose(page,'Kind','report');await detail.getByRole('button',{name:'Save changes',exact:true}).click();
 await expect(detail.getByRole('button',{name:'Edit metadata',exact:true})).toBeVisible();current=await api(id,'/entries/'+seeded.id);expect(current.tags).toEqual(['changed, intact','café 日本語']);expect(current.kind).toBe('report');
 await returnToShelf(page,'desktop',id);
 await page.getByRole('textbox',{name:'Search deliveries',exact:true}).fill('no-such-metadata');await expect(page.getByText('No matching deliveries',{exact:true})).toBeVisible();await nativeRefresh(page);
 await choose(page,'Delivery type','report');await expect(entryButton(page,'desktop',id,seeded.title)).toBeVisible();await nativeRefresh(page);
 await open();await detail.getByRole('button',{name:'Edit metadata',exact:true}).click();
 const payload=Object.fromEntries(['title','description','kind','project','tags','file','session_id','revision'].map(k=>[k,current[k]]));
 await api(id,'/entries/'+seeded.id,{method:'PUT',body:JSON.stringify({...payload,description:'Concurrent edit'})});
 await detail.getByRole('textbox',{name:'Description',exact:true}).fill('Unsaved draft');await detail.getByRole('button',{name:'Save changes',exact:true}).click();
 await expect(page.getByRole('alert')).toBeVisible();await expect(detail.getByRole('textbox',{name:'Description',exact:true})).toHaveValue('Unsaved draft');await detail.getByRole('button',{name:'Cancel',exact:true}).click();await page.getByRole('button',{name:'Dismiss error',exact:true}).click();await returnToShelf(page,'desktop',id);
 const escaped=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'<script>window.evil=true</script>',description:'<img src=x onerror=alert(1)>'})});
 await nativeRefresh(page);await expect(entryButton(page,'desktop',id,escaped.title)).toBeVisible();expect(await page.evaluate(()=>window.evil)).toBeUndefined();await expect(page.locator('.ds-native-group img')).toHaveCount(0);
 await api(id,`/entries/${escaped.id}?revision=${escaped.revision}`,{method:'DELETE'});
 const listing='**/api/plugins/delivery-shelf/entries?**';await page.route(listing,route=>route.fulfill({status:503,json:{detail:'Fictional outage'}}));
 // Native filter retry replaces the retired Refresh button and Try again label.
 await page.getByRole('textbox',{name:'Search deliveries',exact:true}).fill('Metadata');await expect(page.getByRole('alert')).toContainText('Fictional outage');await page.unroute(listing);await page.getByRole('button',{name:'Retry',exact:true}).click();await expect(entryButton(page,'desktop',id,seeded.title)).toBeVisible();
 // Current removal contract is recoverable Trash, not DELETE metadata. Assert
 // failed mutation, exact selection preservation, archive Undo and readbacks.
 await page.getByRole('checkbox',{name:'Select delivery '+seeded.title,exact:true}).click();
 const mutation='**/api/plugins/delivery-shelf/entries/bulk-action*';await page.route(mutation,route=>route.fulfill({status:503,json:{detail:'Delete unavailable'}}));
 await page.getByRole('button',{name:'Trash selected',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Delete unavailable');await expect(page.getByRole('checkbox',{name:'Select delivery '+seeded.title,exact:true})).toBeChecked();await page.unroute(mutation);
 await page.getByRole('button',{name:'Archive selected',exact:true}).click();await expect(page.getByRole('button',{name:'Undo archive',exact:true})).toBeVisible();expect((await api(id,'/entries/'+seeded.id)).state).toBe('archived');
 await page.getByRole('button',{name:'Undo archive',exact:true}).click();await expect(entryButton(page,'desktop',id,seeded.title)).toBeVisible();expect((await api(id,'/entries/'+seeded.id)).state).toBe('active');
 await page.getByRole('checkbox',{name:'Select delivery '+seeded.title,exact:true}).click();await page.getByRole('button',{name:'Trash selected',exact:true}).click();await expect(entryButton(page,'desktop',id,seeded.title)).toHaveCount(0);expect((await api(id,'/entries/'+seeded.id)).state).toBe('trash');
 await choose(page,'Delivery state','Trash');await expect(entryButton(page,'desktop',id,seeded.title)).toBeVisible();
 await page.getByRole('button',{name:'Empty Trash',exact:true}).click();const confirmation=page.getByRole('dialog',{name:'Empty Trash?',exact:true});await expect(confirmation).toContainText('Original working files are never deleted');await confirmation.getByRole('button',{name:'Cancel',exact:true}).click();expect((await api(id,'/entries/'+seeded.id)).state).toBe('trash');
 await page.getByRole('button',{name:'Empty Trash',exact:true}).click();await confirmation.getByRole('button',{name:'Empty Trash · start 60-minute recovery',exact:true}).click();await expect(confirmation).toHaveCount(0);expect((await api(id,'/entries/'+seeded.id)).state).toBe('pending_delete');
 await choose(page,'Delivery state','Pending deletion');await expect(entryButton(page,'desktop',id,seeded.title)).toBeVisible();await page.getByRole('checkbox',{name:'Select delivery '+seeded.title,exact:true}).click();await page.getByRole('button',{name:'Restore selected',exact:true}).click();await expect.poll(async()=>(await api(id,'/entries/'+seeded.id)).state).toBe('active');
 await choose(page,'Delivery state','Active');current=await api(id,'/entries/'+seeded.id);await api(id,`/entries/${seeded.id}?revision=${current.revision}`,{method:'DELETE'});await nativeRefresh(page);
 console.log('PASS metadata desktop delivery-shelf NativeShelf: exact tag rows, native choices, conflict/draft, escaped text, outage/retry, preview/download, failed Trash/selection, archive Undo, Trash cancel/confirm/pending/restore readback');
}

export async function nativeFocusCases(page,api,proof){
 const id='delivery-shelf';await page.getByRole('tab',{name:'Deliverables',exact:true}).click();await page.setViewportSize({width:360,height:640});
 const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Keyboard focus regression'})});await nativeRefresh(page);
 const trigger=entryButton(page,'desktop',id,entry.title);await trigger.focus();await page.keyboard.press('Enter');
 const detail=entrySurface(page,'desktop',id);await detail.getByRole('button',{name:'Edit metadata',exact:true}).focus();await page.keyboard.press('Enter');
 const cancel=detail.getByRole('button',{name:'Cancel',exact:true});await cancel.focus();await page.keyboard.press('Control+End');await cancel.scrollIntoViewIfNeeded();await writeFile(join(proof,'native-footer-geometry.json'),JSON.stringify(await cancel.evaluate(node=>({rect:node.getBoundingClientRect().toJSON(),parents:[...function*(x){while(x){yield x;x=x.parentElement;}}(node)].map(n=>({tag:n.tagName,cls:n.className,rect:n.getBoundingClientRect().toJSON(),scrollTop:n.scrollTop,scrollHeight:n.scrollHeight,clientHeight:n.clientHeight,overflow:getComputedStyle(n).overflowY,position:getComputedStyle(n).position,bottom:getComputedStyle(n).bottom}))})),null,2));await expect(cancel).toBeInViewport({ratio:1});await cancel.focus();await page.keyboard.press('Enter');
 await expect(detail.getByRole('button',{name:'Edit metadata',exact:true})).toBeVisible();await detail.getByRole('button',{name:'Edit metadata',exact:true}).click();
 await detail.getByRole('textbox',{name:'Description',exact:true}).fill('Short viewport saved by keyboard');const save=detail.getByRole('button',{name:'Save changes',exact:true});await save.scrollIntoViewIfNeeded();await expect(save).toBeInViewport({ratio:1});await page.screenshot({path:join(proof,'editor-footer-desktop-delivery-shelf.png')});await save.focus();await page.keyboard.press('Enter');await expect(detail.getByRole('button',{name:'Edit metadata',exact:true})).toBeVisible();
 const current=await api(id,'/entries/'+entry.id);expect(current.description).toBe('Short viewport saved by keyboard');await returnToShelf(page,'desktop',id);
 const add=page.getByRole('button',{name:'Add delivery',exact:true});await add.focus();await page.keyboard.press('Enter');const editor=dialog(page);
 for(let n=0;n<18;n++){await page.keyboard.press('Tab');expect(await editor.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
 await editor.getByRole('button',{name:'Save',exact:true}).scrollIntoViewIfNeeded();await expect(editor.getByRole('button',{name:'Save',exact:true})).toBeInViewport({ratio:1});await page.keyboard.press('Escape');await expect(editor).toHaveCount(0);await expect(add).toBeFocused();
 await api(id,`/entries/${entry.id}?revision=${current.revision}`,{method:'DELETE'});await nativeRefresh(page);await page.setViewportSize({width:1440,height:1100});
 console.log('PASS review focus/editors desktop delivery-shelf NativeShelf: inline metadata cancel/save, native Add modal keyboard trap/Escape/return, 360x640 footer');
}

export async function nativeTitleCases(page,api,proof){
 const id='delivery-shelf',evidence=[];await page.getByRole('tab',{name:'Deliverables',exact:true}).click();await page.setViewportSize({width:360,height:640});
 for(const title of ['UnbrokenTitle'.repeat(12),'A long card title with words that must wrap instead of overflowing the collection card at a narrow viewport '.repeat(2).slice(0,160)]){
  const entry=await api(id,'/entries',{method:'POST',body:JSON.stringify({title})});await nativeRefresh(page);
  const button=page.getByRole('button',{name:'Collapse '+title,exact:true});await expect(button).toBeVisible();await button.scrollIntoViewIfNeeded();
  const bounds=await button.evaluate(node=>{const text=node.querySelector('.ds-native-group-copy > span'),range=document.createRange();range.selectNodeContents(text);return {button:node.getBoundingClientRect().toJSON(),card:node.closest('.ds-native-group').getBoundingClientRect().toJSON(),text:[...range.getClientRects()].map(r=>r.toJSON()),viewport:innerWidth};});
  evidence.push({id,title,...bounds});expect(bounds.button.left).toBeGreaterThanOrEqual(bounds.card.left-1);expect(bounds.button.right).toBeLessThanOrEqual(bounds.card.right+1);expect(bounds.button.right).toBeLessThanOrEqual(360);
  for(const rect of bounds.text){expect(rect.left).toBeGreaterThanOrEqual(bounds.button.left-1);expect(rect.right).toBeLessThanOrEqual(bounds.button.right+1);expect(rect.top).toBeGreaterThanOrEqual(bounds.button.top-1);expect(rect.bottom).toBeLessThanOrEqual(bounds.button.bottom+1);}
  await page.screenshot({path:join(proof,'title-desktop-delivery-shelf.png'),fullPage:true});await api(id,`/entries/${entry.id}?revision=${entry.revision}`,{method:'DELETE'});
 }
 await writeFile(join(proof,'title-bounds-native-desktop.json'),JSON.stringify(evidence,null,2));await nativeRefresh(page);await page.setViewportSize({width:1440,height:1100});console.log('PASS review title bounds desktop delivery-shelf NativeShelf: group disclosure and text rects at 360px');
}

export async function nativeGenerationFenceCase(page,change,pattern){
 const editor=dialog(page);await meadow(page);
 let release,seen;const held=new Promise(r=>release=r),entered=new Promise(r=>seen=r);
 await page.route(pattern,async route=>{seen();await held;await route.fulfill({json:{draft:{title:'RETIRED GENERATION',description:'never render',tags:[]},context:{content_mode:'text'}}});});
 await editor.getByRole('button',{name:'Generate',exact:true}).click();await entered;
 await page.evaluate(change=>{if(change==='dispose')for(const id of ['conversation-bookmarks','delivery-shelf'])window.__QA_UNLOAD__(id);else window.__QA_SDK__.host.state[change==='profile'?'profile':'connectionId'].set(change==='profile'?'foreign':'next-connection');},change);
 await expect(editor).toHaveCount(0);await page.waitForTimeout(250);const count=await page.evaluate(()=>window.__QA_REQUESTS__.length);release();await page.unroute(pattern,{behavior:'wait'});await page.waitForTimeout(250);await expect(page.getByText('RETIRED GENERATION',{exact:false})).toHaveCount(0);expect(await page.evaluate(()=>window.__QA_REQUESTS__.length)).toBe(count);
}
