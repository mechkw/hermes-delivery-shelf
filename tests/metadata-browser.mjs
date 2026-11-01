// Metadata regressions use actual host components/loaders and the fictional API.
import {expect} from '@playwright/test';
export async function metadataCases(page,adapter,api){
 const dialog=()=>page.getByRole('dialog');
 const choose=async(label,name)=>{await page.getByRole('combobox',{name:label,exact:true}).click();await page.getByRole('option',{name,exact:true}).click();};
 for(const id of ['conversation-bookmarks','delivery-shelf']){
  const bookmarks=id==='conversation-bookmarks',tab=bookmarks?'Bookmarks':'Deliverables',text=bookmarks?'note':'description',edit=bookmarks?'Edit bookmark':'Edit metadata',field=bookmarks?'Note':'Description';
  const tags=['design, decisions','say "hello"','café 日本語'];
  const prefix='/api/plugins/'+id;
  const seeded=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'Metadata regression',tags,...(bookmarks?{session_id:'fictional-session-01'}:{file:{root:'workspaces',path:'example.md'},session_id:'fictional-session-01'})})});
  await page.getByRole('tab',{name:tab,exact:true}).click();await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.getByRole('button',{name:seeded.title,exact:true}).click();
  if(!bookmarks){
   await dialog().getByRole('button',{name:'Preview text'}).click();await expect(dialog().locator('pre')).not.toBeEmpty();expect(await dialog().locator('pre script')).toHaveCount(0);
   const downloading=page.waitForEvent('download');await dialog().getByRole('button',{name:'Download file'}).click();expect((await downloading).suggestedFilename()).toBe('example.md');
  }else if(adapter==='desktop'){
   await dialog().getByRole('button',{name:'Open conversation'}).click();await expect.poll(()=>page.evaluate(()=>window.__QA_OPENED__?.id)).toBe('fictional-session-01');
  }
  await dialog().getByRole('button',{name:edit}).click();await dialog().getByLabel(field,{exact:true}).fill('Only metadata changed.');
  await dialog().getByRole('button',{name:'Save changes'}).click();await expect(dialog()).toHaveCount(0);
  let current=await api(id,'/entries/'+seeded.id);expect(current.tags).toEqual(tags);expect(current[text]).toBe('Only metadata changed.');
  expect((await api(id,'/entries?tag='+encodeURIComponent(tags[0]))).items.map(x=>x.id)).toEqual([seeded.id]);
  await page.getByRole('button',{name:seeded.title,exact:true}).click();await dialog().getByRole('button',{name:edit}).click();
  await dialog().getByLabel(bookmarks?'Tags':'Tags (one per line)',{exact:true}).fill('changed, intact\ncafé 日本語');
  if(!bookmarks){await dialog().getByText('More options',{exact:true}).click();await choose('Kind','report');}
  await dialog().getByRole('button',{name:'Save changes'}).click();await expect(dialog()).toHaveCount(0);
  current=await api(id,'/entries/'+seeded.id);expect(current.tags).toEqual(['changed, intact','café 日本語']);if(!bookmarks)expect(current.kind).toBe('report');
  // Search and native Select sorting/filtering, including escaped titles.
  await page.getByLabel('Search '+(bookmarks?'bookmarks':'deliveries'),{exact:true}).fill('no-such-metadata');
  await expect(page.getByText(bookmarks?'No matching bookmarks':'No matching deliveries',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Clear filters'}).click();
  await page.getByRole('button',{name:'Filter tag changed, intact',exact:true}).click();await expect(page.getByRole('button',{name:seeded.title,exact:true})).toBeVisible();await page.getByRole('button',{name:'Clear filters'}).click();
  if(bookmarks)await choose('Sort','Title A–Z');else {await choose('Kind','report');await expect(page.getByRole('button',{name:seeded.title,exact:true})).toBeVisible();await page.getByRole('button',{name:'Clear filters'}).click();}
  // Real revision conflict leaves draft/dialog open.
  await page.getByRole('button',{name:seeded.title,exact:true}).click();await dialog().getByRole('button',{name:edit}).click();
  const keys=bookmarks?['title','note','tags','session_id','message_id','revision']:['title','description','kind','project','tags','file','session_id','revision'];
  const payload=Object.fromEntries(keys.map(k=>[k,current[k]]));
  current=await api(id,'/entries/'+seeded.id,{method:'PUT',body:JSON.stringify({...payload,[text]:'Concurrent edit'})});
  await dialog().getByLabel(field,{exact:true}).fill('Unsaved draft');await dialog().getByRole('button',{name:'Save changes'}).click();
  await expect(dialog().getByRole('alert')).toBeVisible();await expect(dialog().getByLabel(field,{exact:true})).toHaveValue('Unsaved draft');await dialog().getByRole('button',{name:'Cancel',exact:true}).click();
  const escaped=await api(id,'/entries',{method:'POST',body:JSON.stringify({title:'<script>window.evil=true</script>',[text]:'<img src=x onerror=alert(1)>',...(bookmarks?{session_id:'fictional-session-01'}:{})})});
  await page.getByRole('button',{name:'Refresh',exact:true}).click();await expect(page.getByRole('button',{name:escaped.title,exact:true})).toBeVisible();expect(await page.evaluate(()=>window.evil)).toBeUndefined();expect(await page.locator('.cb-card img,.ds-card img')).toHaveCount(0);
  await api(id,`/entries/${escaped.id}?revision=${escaped.revision}`,{method:'DELETE'});
  // Outage/retry, cancellation and a failed delete never auto-close the dialog.
  const listing='**'+prefix+'/entries?**';await page.route(listing,route=>route.fulfill({status:503,json:{detail:'Fictional outage'}}));
  await page.getByRole('button',{name:'Refresh',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Fictional outage');await page.unroute(listing);await page.getByRole('button',{name:'Try again'}).click();
  await page.getByRole('button',{name:seeded.title,exact:true}).click();await dialog().getByRole('button',{name:bookmarks?'Remove bookmark':'Remove from shelf'}).click();await dialog().getByRole('button',{name:bookmarks?'Keep bookmark':'Keep delivery'}).click();
  expect((await api(id,'/entries/'+seeded.id)).id).toBe(seeded.id);
  await page.getByRole('button',{name:seeded.title,exact:true}).click();await dialog().getByRole('button',{name:bookmarks?'Remove bookmark':'Remove from shelf'}).click();
  const deleting='**'+prefix+'/entries/'+seeded.id+'*';await page.route(deleting,route=>route.request().method()==='DELETE'?route.fulfill({status:503,json:{detail:'Delete unavailable'}}):route.continue());
  await dialog().getByRole('button',{name:'Remove metadata'}).click();await expect(dialog().getByRole('alert')).toContainText('Delete unavailable');await page.unroute(deleting);
  await dialog().getByRole('button',{name:'Remove metadata'}).click();await expect(dialog()).toHaveCount(0);expect((await api(id,'/entries')).items.some(x=>x.id===seeded.id)).toBe(false);
  console.log('PASS metadata',adapter,id,'tags, native choices, conflict/draft, escaped text, outage/retry, delete error/cancel/readback'+(!bookmarks?', preview/download':''));
 }
}

export async function pendingMutationCases(page,adapter,api,base){
 for(const id of ['conversation-bookmarks','delivery-shelf'])for(const change of ['profile',...(adapter==='desktop'?['connection','dispose']:['dispose'])]){
  await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);await page.getByRole('tab',{name:id==='conversation-bookmarks'?'Bookmarks':'Deliverables',exact:true}).click();
  const old=(await api(id,'/entries')).items[0];await page.getByRole('button',{name:old.title,exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:id==='conversation-bookmarks'?'Edit bookmark':'Edit metadata'}).click();
  await dialog.getByLabel('Title',{exact:true}).fill(old.title);
  let release,seen;const held=new Promise(r=>release=r),entered=new Promise(r=>seen=r);
  const pattern='**/api/plugins/'+id+'/entries/'+old.id+'*';
  await page.route(pattern,async route=>{if(route.request().method()==='PUT'){seen();await held;}await route.continue();});
  await dialog.getByRole('button',{name:'Save changes'}).click();await entered;
  await expect(dialog.getByLabel('Title',{exact:true})).toBeDisabled();await page.keyboard.press('Escape');await expect(dialog).toBeVisible();
  await page.evaluate(({adapter,change})=>{if(adapter==='desktop'){if(change==='dispose')for(const id of ['conversation-bookmarks','delivery-shelf'])window.__QA_UNLOAD__(id);else window.__QA_SDK__.host.state[change==='profile'?'profile':'connectionId'].set(change==='profile'?'foreign':'changed');}else if(change==='profile')window.__QA_PROFILE__('foreign');else window.__QA_UNMOUNT__();},{adapter,change});
  await page.waitForTimeout(350);const count=await page.evaluate(()=>window.__QA_REQUESTS__.length);release();await page.unroute(pattern,{behavior:'wait'});await page.waitForTimeout(350);
  expect(await page.evaluate(()=>window.__QA_REQUESTS__.length)).toBe(count);
  console.log('PASS pending mutation fence',adapter,id,change);
 }
 await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);
}

export async function sourceFenceCases(page,adapter,base){
 for(const [id,tab,button] of [['conversation-bookmarks','Bookmarks','Save bookmark'],['delivery-shelf','Deliverables','Add delivery']])for(const change of ['profile',...(adapter==='desktop'?['connection']:[]),'dispose']){
  await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);await page.getByRole('tab',{name:tab,exact:true}).click();
  await page.getByRole('button',{name:button,exact:true}).click();
  let release,seen;const held=new Promise(r=>release=r),entered=new Promise(r=>seen=r);
  const pattern='**/api/plugins/'+id+'/sources/sessions?**';
  await page.route(pattern,async route=>{if(new URL(route.request().url()).searchParams.get('q')!=='fence'){await route.continue();return;}seen();await held;await route.fulfill({json:{items:[{id:'stale-secret',title:'Retired source result',updated_at:null}],has_more:false}});});
  await page.getByRole('dialog').getByLabel('Search conversations',{exact:true}).fill('fence');await entered;
  await page.evaluate(({adapter,change})=>{if(adapter==='desktop'){if(change==='dispose')for(const id of ['conversation-bookmarks','delivery-shelf'])window.__QA_UNLOAD__(id);else window.__QA_SDK__.host.state[change==='profile'?'profile':'connectionId'].set(change==='profile'?'foreign':'next-connection');}else if(change==='profile')window.__QA_PROFILE__('foreign');else window.__QA_UNMOUNT__();},{adapter,change});
  await expect(page.getByRole('dialog')).toHaveCount(0);release();await page.unroute(pattern,{behavior:'wait'});await page.waitForTimeout(250);
  await expect(page.getByText('Retired source result',{exact:false})).toHaveCount(0);
  console.log('PASS pending source fence',adapter,id,change);
 }
 await page.goto(base+'/qa/'+adapter);await expect(page.getByRole('tab')).toHaveCount(2);
}
