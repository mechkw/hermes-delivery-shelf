import {expect} from '@playwright/test';
import {join} from 'node:path';
import {nativeRedesignCases,nativeGenerationFenceCase} from './native-shelf-browser.mjs';
export async function shelfRedesignCases(page,adapter,api,proof){
 if(adapter==='desktop')return nativeRedesignCases(page,api,proof);
 const id='delivery-shelf';
 await page.getByRole('tab',{name:'Deliverables',exact:true}).click();
 await page.getByRole('button',{name:'Add delivery',exact:true}).click();
 const dialog=page.getByRole('dialog');
 const choose=async(label,name)=>{await dialog.getByRole('combobox',{name:label,exact:true}).click();await page.getByRole('option',{name,exact:false}).click();};
 const writes=await page.evaluate(()=>window.__QA_REQUESTS__.filter(r=>r.method!=='GET').length);
 await expect(dialog.getByRole('combobox',{name:'Context',exact:true})).toContainText('10');
 const help=dialog.getByLabel('Previous conversations unavailable',{exact:true});await page.mouse.move(0,0);await dialog.getByLabel('Search conversations',{exact:true}).focus();
 for(let n=0;n<20&&!await help.evaluate(el=>el===document.activeElement);n++)await page.keyboard.press('Tab');
 await expect(help).toBeFocused();await expect(page.getByRole('tooltip')).toContainText('most recent 1000 conversations');
 if(adapter==='dashboard')await expect(page.getByRole('tooltip')).not.toHaveCSS('background-color','rgba(0, 0, 0, 0)');
 await page.keyboard.press('Escape');await expect(dialog).toBeVisible();await dialog.getByLabel('Search conversations',{exact:true}).focus();await page.waitForTimeout(250);
 await dialog.getByLabel('Search conversations',{exact:true}).fill('Meadow');await page.waitForTimeout(250);
 await page.keyboard.press('Enter');await expect(dialog).toBeVisible();
 await choose('Choose a conversation','Meadow deliverables');
 await expect(dialog.getByLabel('Search files')).toBeVisible();await page.waitForTimeout(250);
 await dialog.getByRole('combobox',{name:'Choose a file',exact:true}).click();
 await expect(page.getByRole('option',{name:'meadow.md · MD',exact:true})).toBeVisible();
 await expect(page.getByRole('option',{name:'meadow.png · PNG',exact:true})).toBeVisible();
 await expect(page.getByRole('option',{name:'bundle.zip · ZIP',exact:true})).toBeVisible();
 await page.getByRole('option',{name:'meadow.md · MD',exact:true}).click();
 expect(await page.evaluate(()=>window.__QA_REQUESTS__.filter(r=>r.method!=='GET').length)).toBe(writes);
 // Two real editor windows: B persists 50 while A still displays 10.
 const other=await page.context().newPage();
 await other.goto(page.url());await expect(other.getByRole('tab')).toHaveCount(2);
 await other.getByRole('tab',{name:'Deliverables',exact:true}).click();
 await other.getByRole('button',{name:'Add delivery',exact:true}).click();
 const otherDialog=other.getByRole('dialog');
 await expect(otherDialog.getByRole('combobox',{name:'Context',exact:true})).toContainText('10');
 await otherDialog.getByRole('combobox',{name:'Context',exact:true}).click();
 await other.getByRole('option',{name:'50',exact:true}).click();
 await expect.poll(async()=>(await api(id,'/generation/settings')).previous_exchanges).toBe(50);
 await expect(dialog.getByRole('combobox',{name:'Context',exact:true})).toContainText('10');
 const contextPattern='**/api/plugins/delivery-shelf/generation/draft*';
 let contextRequest;
 await page.route(contextPattern,async route=>{contextRequest=route.request().postDataJSON();await route.fulfill({json:{draft:{title:'Ten exchanges draft',description:'Request-bound context',tags:[]},context:{content_mode:'text',truncated:false}}});});
 await dialog.getByRole('button',{name:'Generate details',exact:true}).click();
 await expect(dialog.getByLabel('Title',{exact:true})).toHaveValue('Ten exchanges draft');
 expect(contextRequest.previous_exchanges).toBe(10);
 expect((await api(id,'/generation/settings')).previous_exchanges).toBe(50);
 await page.unroute(contextPattern);await otherDialog.getByRole('button',{name:'Cancel',exact:true}).click();await other.close();
 console.log('PASS Shelf Context actual request: window A=10, window B persisted=50, POST previous_exchanges=10',adapter);
 await dialog.getByRole('combobox',{name:'Context',exact:true}).click();
 for(const n of ['5','10','20','50'])await expect(page.getByRole('option',{name:n,exact:true})).toBeVisible();
 await page.getByRole('option',{name:'20',exact:true}).click();
 const pattern='**/api/plugins/delivery-shelf/generation/draft*';
 let count=0;
 await page.route(pattern,async route=>{count++;expect(route.request().method()).toBe('POST');expect(route.request().postDataJSON().source.message_id).toBeGreaterThan(44);await route.fulfill({json:{draft:{title:'Meadow survey',description:'Fictional survey: three swallows.',tags:['meadow','survey']},context:{content_mode:'text',truncated:false}}});});
 const before=(await api(id,'/entries')).total;
 await dialog.getByRole('button',{name:'Generate details',exact:true}).click();
 await expect(dialog.getByLabel('Title',{exact:true})).toHaveValue('Meadow survey');expect(count).toBe(1);expect((await api(id,'/entries')).total).toBe(before);
 expect((await api(id,'/generation/settings')).previous_exchanges).toBe(20);
 await dialog.getByLabel('Title',{exact:true}).focus();await page.mouse.move(0,0);await page.waitForTimeout(250);
 await page.screenshot({path:join(proof,`shelf-editor-overview-${adapter}.png`)});
 await page.setViewportSize({width:360,height:640});await page.waitForTimeout(250);
 await dialog.getByRole('button',{name:'Save delivery',exact:true}).scrollIntoViewIfNeeded();await expect(dialog.getByRole('button',{name:'Save delivery',exact:true})).toBeInViewport({ratio:1});
 await page.screenshot({path:join(proof,`shelf-new-editor-${adapter}.png`)});
 await dialog.getByRole('button',{name:'Save delivery',exact:true}).focus();await page.keyboard.press('Enter');await expect(dialog).toHaveCount(0);
 const saved=(await api(id,'/entries?q=Meadow%20survey')).items[0];expect(saved.file.path).toBe('meadow.md');expect(saved.source.message_id).toBeGreaterThan(44);
 await page.getByRole('button',{name:'Add delivery',exact:true}).click();await expect(dialog.getByRole('combobox',{name:'Context',exact:true})).toContainText('20');
 await choose('Choose a conversation','Meadow deliverables');await page.waitForTimeout(250);await choose('Choose a file','bundle.zip');await expect(dialog.getByText('History only — this file format is not read.')).toBeVisible();
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();expect((await api(id,'/entries')).total).toBe(before+1);
 await page.unroute(pattern);
 // Explicit provider error keeps the editor and manual save available; no POST retry.
 await page.getByRole('button',{name:'Add delivery',exact:true}).click();await choose('Choose a conversation','Meadow deliverables');await page.waitForTimeout(250);await choose('Choose a file','meadow.md');
 let errors=0;await page.route(pattern,route=>{errors++;return route.fulfill({status:502,json:{detail:'Fictional model error'}});});
 await dialog.getByRole('button',{name:'Generate details',exact:true}).click();await expect(dialog.getByRole('alert')).toContainText('Fictional model error');expect(errors).toBe(1);await expect(dialog.getByRole('button',{name:'Save delivery',exact:true})).toBeEnabled();await page.unroute(pattern);
 let release,entered;const hold=new Promise(r=>release=r),seen=new Promise(r=>entered=r);
 await page.route(pattern,async route=>{entered();await hold;await route.fulfill({json:{draft:{title:'STALE DRAFT',description:'stale',tags:[]},context:{content_mode:'text'}}});});
 await dialog.getByRole('button',{name:'Generate details',exact:true}).click();await seen;await dialog.getByLabel('Title',{exact:true}).fill('My edit wins');release();await expect(dialog.getByText('Draft changed during generation. Your edits were kept.')).toBeVisible();await expect(dialog.getByLabel('Title',{exact:true})).toHaveValue('My edit wins');await page.unroute(pattern);await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 // Changing the selected file while inference is pending must retire the draft.
 await page.getByRole('button',{name:'Add delivery',exact:true}).click();await choose('Choose a conversation','Meadow deliverables');await page.waitForTimeout(250);await choose('Choose a file','meadow.md');
 let releaseFile,enteredFile;const fileHold=new Promise(r=>releaseFile=r),fileSeen=new Promise(r=>enteredFile=r);
 await page.route(pattern,async route=>{enteredFile();await fileHold;await route.fulfill({json:{draft:{title:'WRONG FILE',description:'stale',tags:[]},context:{content_mode:'text'}}});});
 await dialog.getByRole('button',{name:'Generate details',exact:true}).click();await fileSeen;await choose('Choose a file','meadow.png');releaseFile();await expect(dialog.getByText('Draft changed during generation. Your edits were kept.')).toBeVisible();await expect(dialog.getByLabel('Title',{exact:true})).toHaveValue('meadow.png');await page.unroute(pattern);await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 // Source outages are not empty states, and Retry is an explicit GET only.
 const sources='**/api/plugins/delivery-shelf/sources/sessions?**';
 await page.route(sources,route=>route.fulfill({status:503,json:{detail:'Fictional source outage'}}));
 await page.getByRole('button',{name:'Add delivery',exact:true}).click();await expect(dialog.getByRole('alert')).toContainText('Fictional source outage');await page.unroute(sources);
 await dialog.getByRole('button',{name:'Retry conversations',exact:true}).click();await choose('Choose a conversation','Meadow deliverables');await page.waitForTimeout(250);
 await dialog.getByLabel('Search files',{exact:true}).fill('no-matching-file');await expect(dialog.getByText('No matches',{exact:true})).toBeVisible();await expect(dialog.getByRole('button',{name:'Generate details',exact:true})).toBeDisabled();
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.setViewportSize({width:1440,height:1100});
 const candidates=(await api(id,'/sources/sessions/fictional-files/artifacts')).items;
 const image=candidates.find(x=>x.name==='meadow.png');
 const imageEntry=await api(id,'/sources/register',{method:'POST',body:JSON.stringify({title:'Fictional meadow illustration',description:'A fictional image for gallery QA.',session_id:'fictional-files',file:image.file,source:image.source,kind:'image',tags:['meadow']})});
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 if(adapter==='desktop'){
  const card=page.locator('article').filter({has:page.getByRole('button',{name:imageEntry.title,exact:true})});
  await expect(card.locator('img')).toHaveJSProperty('naturalWidth',180);
  const overlay=card.getByRole('button',{name:'Download meadow.png',exact:true});
  await card.locator('.ds-artifact-preview').hover();await expect(overlay).toHaveCSS('opacity','1');
  await overlay.focus();await expect(overlay).toHaveCSS('opacity','1');
  const downloading=page.waitForEvent('download');await page.keyboard.press('Enter');expect((await downloading).suggestedFilename()).toBe('meadow.png');
  await card.getByRole('button',{name:'Chat',exact:true}).click();expect(await page.evaluate(()=>window.__QA_OPENED__.id)).toBe('fictional-files');
  await page.screenshot({path:join(proof,'shelf-thumbnail-gallery.png'),fullPage:true});
 }
 for(const item of [saved,imageEntry])await api(id,`/entries/${item.id}?revision=${item.revision}`,{method:'DELETE'});
 await api(id,'/generation/settings',{method:'PUT',body:JSON.stringify({previous_exchanges:10})});
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 console.log('PASS Shelf redesign',adapter,'actual file chooser, 5/10/20/50, no autosave, save/readback/cancel, errors, edits/file fences, 360x640; Desktop image/download/Chat');
}
export async function shelfGenerationFenceCases(page,adapter,base){
 const pattern='**/api/plugins/delivery-shelf/generation/draft*';
 for(const change of ['profile',...(adapter==='desktop'?['connection']:[]),'dispose']){
  await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);await page.getByRole('tab',{name:'Deliverables',exact:true}).click();await page.getByRole('button',{name:'Add delivery',exact:true}).click();
  const dialog=page.getByRole('dialog');
  if(adapter==='desktop'){await nativeGenerationFenceCase(page,change,pattern);console.log('PASS Shelf generation lifetime fence',adapter,change);continue;}
  const choose=async(label,name)=>{await dialog.getByRole('combobox',{name:label,exact:true}).click();await page.getByRole('option',{name,exact:false}).click();};
  await dialog.getByLabel('Search conversations',{exact:true}).fill('Meadow');await page.waitForTimeout(250);await choose('Choose a conversation','Meadow deliverables');await page.waitForTimeout(250);await choose('Choose a file','meadow.md');
  let release,entered;const hold=new Promise(r=>release=r),seen=new Promise(r=>entered=r);
  await page.route(pattern,async route=>{entered();await hold;await route.fulfill({json:{draft:{title:'RETIRED GENERATION',description:'never render',tags:[]},context:{content_mode:'text'}}});});
  await dialog.getByRole('button',{name:'Generate details',exact:true}).click();await seen;
  await page.evaluate(({adapter,change})=>{if(adapter==='desktop'){if(change==='dispose')for(const id of ['conversation-bookmarks','delivery-shelf'])window.__QA_UNLOAD__(id);else window.__QA_SDK__.host.state[change==='profile'?'profile':'connectionId'].set(change==='profile'?'foreign':'next-connection');}else if(change==='profile')window.__QA_PROFILE__('foreign');else window.__QA_UNMOUNT__();},{adapter,change});
  await expect(dialog).toHaveCount(0);await page.waitForTimeout(250);const count=await page.evaluate(()=>window.__QA_REQUESTS__.length);release();await page.unroute(pattern,{behavior:'wait'});await page.waitForTimeout(250);
  await expect(page.getByText('RETIRED GENERATION',{exact:false})).toHaveCount(0);expect(await page.evaluate(()=>window.__QA_REQUESTS__.length)).toBe(count);
  console.log('PASS Shelf generation lifetime fence',adapter,change);
 }
 await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);
}
