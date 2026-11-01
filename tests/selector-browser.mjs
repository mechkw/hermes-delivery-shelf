// User-facing selector contracts exercised through both real host loaders.
import {expect} from '@playwright/test';
import {join} from 'node:path';
const session='fictional-session-01';
const choices=[{id:session,title:'Release planning',updated_at:1793400000,source:'desktop'},{id:'other-session',title:'Other conversation',updated_at:null,source:'cli'}];
const reply={id:1,preview:'Ship the reviewed build after verification.',created_at:1793400100};
export async function selectorCases(page,adapter,api,sourceBank,proof){
 const prefix='/api/plugins/conversation-bookmarks';
 let mode='normal',requests=[],writes=[];
 await page.route('**'+prefix+'/sources/**',async route=>{
  const url=new URL(route.request().url());requests.push(url);
  const q=url.searchParams.get('q'),response=url.pathname.endsWith('/responses');
  if(mode==='error')return route.fulfill({status:503,json:{detail:'Choices temporarily unavailable'}});
  if(q==='slow')await new Promise(r=>setTimeout(r,600));
  const items=q==='none'?[]:response?(url.pathname.includes('other-session')?[{...reply,id:2,preview:'Other assistant reply'}]:q==='slow'?[{...reply,id:3,preview:'STALE RESPONSE'}]:Number(url.searchParams.get('offset'))>0?[{...reply,id:4,preview:'Older assistant reply'}]:[reply]):q==='slow'?[{...choices[0],id:'stale',title:'STALE CONVERSATION'}]:Number(url.searchParams.get('offset'))>0?[{id:'older-session',title:'Older conversation',updated_at:null}]:choices;
  await route.fulfill({json:{items,has_more:!q&&Number(url.searchParams.get('offset'))===0,window:{limit:response?500:1000,truncated:q!=='complete'}}});
 });
 // Observe native transport mutations without substituting their results.
 page.on('request',r=>{if(r.url().includes(prefix+'/entries')&&['POST','PUT','DELETE'].includes(r.method()))writes.push({method:r.method(),body:r.postDataJSON()});});
 const choose=async(label,name)=>{const box=page.getByRole('dialog').getByRole('combobox',{name:label,exact:true});await box.click();await page.getByRole('option',{name,exact:false}).click();};
 const editor=()=>page.getByRole('dialog');
 const tooltip=async(name,text)=>{
  const button=editor().getByRole('button',{name,exact:true});
  const trigger=await button.isDisabled()?editor().locator(`[aria-label="${name} unavailable"]`):button;
  await page.mouse.move(0,0);await editor().getByLabel('Search conversations',{exact:true}).focus();await expect(page.getByRole('tooltip')).toHaveCount(0);await trigger.scrollIntoViewIfNeeded();await trigger.hover();await expect(page.locator('[role=tooltip]:not([data-state=closed])')).toBeVisible();await expect(page.locator('[role=tooltip]:not([data-state=closed])')).toHaveText(text);
  await page.screenshot({path:join(proof,`tooltip-${adapter}-${name.replace(' ','-')}.png`),fullPage:true});
  await page.mouse.move(0,0);await editor().getByLabel('Search conversations',{exact:true}).focus();await expect(page.getByRole('tooltip')).toHaveCount(0);
  // Real keyboard input establishes the host's input-modality gate.
  for(let n=0;n<20&&!await trigger.evaluate(el=>el===document.activeElement);n++)await page.keyboard.press('Tab');
  await expect(trigger).toBeFocused();await expect(page.locator('[role=tooltip]:not([data-state=closed])')).toBeVisible();await expect(page.locator('[role=tooltip]:not([data-state=closed])')).toHaveText(text);
  await page.keyboard.press('Escape');await expect(page.locator('[role=tooltip]:not([data-state=closed])')).toHaveCount(0);await expect(editor()).toBeVisible();
  await editor().getByLabel('Search conversations',{exact:true}).focus();
 };
 await page.getByRole('tab',{name:'Bookmarks',exact:true}).click();
 await page.getByRole('button',{name:'Save bookmark',exact:true}).click();
 await expect(editor().getByRole('combobox',{name:'Response (optional)',exact:true})).toContainText('Entire conversation');
 await expect(editor().getByRole('button',{name:'Save bookmark',exact:true})).toBeDisabled();
 await expect(editor().getByText('Session ID',{exact:true})).toHaveCount(0);
 await choose('Choose a conversation','Release planning');
 await expect(editor().getByLabel('Title',{exact:true})).toHaveValue('Release planning');
 await expect(editor().getByLabel('Note',{exact:true})).toHaveValue('');
 await tooltip('Previous conversations','Search filter covers the most recent 1000 conversations. Older conversations are not included.');
 await expect(editor().getByRole('button',{name:'Next conversations'})).toBeEnabled();
 await expect(editor().getByRole('button',{name:'Next conversations'})).toHaveText('Next');
 await tooltip('Next conversations','Search filter covers the most recent 1000 conversations. Older conversations are not included.');
 await editor().getByRole('button',{name:'Next conversations'}).click();
 await expect.poll(()=>requests.some(u=>u.searchParams.get('offset')==='30')).toBe(true);
 await expect(editor().getByRole('button',{name:'Previous conversations'})).toBeEnabled();
 await choose('Choose a conversation','Older conversation');
 await expect(editor().getByLabel('Title',{exact:true})).toHaveValue('Release planning');
 await editor().getByRole('button',{name:'Previous conversations'}).click();
 await choose('Choose a conversation','Release planning');
 await choose('Response (optional)','Ship the reviewed build');
 await editor().getByRole('button',{name:'Next responses'}).click();
 await expect.poll(()=>requests.some(u=>u.pathname.endsWith('/responses')&&u.searchParams.get('offset')==='30')).toBe(true);
 await choose('Response (optional)','Older assistant reply');
 await editor().getByRole('button',{name:'Previous responses'}).click();
 await choose('Response (optional)','Ship the reviewed build');
 mode='error';await editor().getByLabel('Search responses',{exact:true}).fill('fail');
 await expect(editor().getByRole('button',{name:'Retry responses'})).toBeVisible();
 mode='normal';await editor().getByRole('button',{name:'Retry responses'}).click();
 await expect(editor().getByRole('button',{name:'Retry responses'})).toHaveCount(0);
 await editor().getByLabel('Search responses',{exact:true}).fill('none');await expect(editor().getByText('No matches',{exact:true})).toBeVisible();
 await tooltip('Next responses','Search filter covers the most recent 500 assistant responses. Older assistant responses are not included.');
 await editor().getByLabel('Search responses',{exact:true}).fill('complete');
 await tooltip('Next responses','Search filter covers up to 500 recent assistant responses. All available assistant responses are included.');

 // A response search must not submit the metadata form when its clear action
 // is activated (the native SearchField's clear control is inside the form).
 await editor().getByLabel('Search responses',{exact:true}).fill('ship');
 await editor().getByLabel('Search responses',{exact:true}).press('Enter');await page.waitForTimeout(250);await expect(editor()).toBeVisible();expect(writes).toHaveLength(0);await expect(editor().getByLabel('Search responses',{exact:true})).toHaveValue('ship');
 if(adapter==='desktop'){await editor().locator('[aria-label="Response (optional) choices"]').getByRole('button',{name:/Clear/}).click();await expect(editor()).toBeVisible();expect(writes).toHaveLength(0);}
 else await editor().getByLabel('Search responses',{exact:true}).fill('');
 await choose('Choose a conversation','Other conversation');
 await expect(editor().getByRole('combobox',{name:'Response (optional)',exact:true})).toContainText('Entire conversation');
 await choose('Choose a conversation','Release planning');
 await editor().getByLabel('Search responses',{exact:true}).fill('slow');
 await expect.poll(()=>requests.some(u=>u.pathname.endsWith('/responses')&&u.searchParams.get('q')==='slow')).toBe(true);
 await choose('Choose a conversation','Other conversation');
 await page.waitForTimeout(700);
 await editor().getByRole('combobox',{name:'Response (optional)',exact:true}).click();
 await expect(page.getByRole('option',{name:/STALE RESPONSE/})).toHaveCount(0);
 await page.keyboard.press('Escape');
 await expect(editor()).toBeVisible();
 await choose('Choose a conversation','Release planning');
 await editor().getByLabel('Search conversations',{exact:true}).fill('slow');
 await expect.poll(()=>requests.some(u=>u.pathname==prefix+'/sources/sessions'&&u.searchParams.get('q')==='slow')).toBe(true);
 await editor().getByLabel('Search conversations',{exact:true}).fill('none');
 await expect(editor().getByText('No matches',{exact:true})).toBeVisible();
 await page.waitForTimeout(700);
 await expect(editor().getByText('No matches',{exact:true})).toBeVisible();
 await expect(editor().getByRole('combobox',{name:'Choose a conversation',exact:true})).toContainText('Release planning');
 await tooltip('Previous conversations','Search filter covers the most recent 1000 conversations. Older conversations are not included.');
 mode='error';await editor().getByLabel('Search conversations',{exact:true}).fill('fail');
 await expect(editor().getByRole('button',{name:'Retry conversations'})).toBeVisible();
 mode='normal';await editor().getByRole('button',{name:'Retry conversations'}).click();
 await expect(editor().getByRole('button',{name:'Retry conversations'})).toHaveCount(0);
 await editor().getByLabel('Title',{exact:true}).fill('Selector saved');
 // Metadata remains null by default even after response resets; note stays blank.
 await editor().getByRole('button',{name:'Save bookmark',exact:true}).click();
 await expect(editor()).toHaveCount(0);
 const saved=(await api('conversation-bookmarks','/entries')).items.find(x=>x.title==='Selector saved');
 expect(saved.message_id).toBe(null);expect(saved.note).toBe('');expect(saved.session_id).toBe(session);
 await api('conversation-bookmarks',`/entries/${saved.id}?revision=${saved.revision}`,{method:'DELETE'});
 // Old/pruned/out-of-window source refs remain selected and survive metadata edits.
 const old=await api('conversation-bookmarks','/entries',{method:'POST',body:JSON.stringify({title:'Old reference',session_id:'pruned-session',message_id:44,note:'My original note'})});
 sourceBank.prune();
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await page.getByRole('button',{name:'Old reference',exact:true}).click();await editor().getByRole('button',{name:'Edit bookmark'}).click();
 mode='normal';await editor().getByLabel('Search conversations',{exact:true}).fill('none');await editor().getByLabel('Search responses',{exact:true}).fill('none');
 await expect(editor().getByText('No matches',{exact:true})).toHaveCount(2);
 await expect(editor().getByRole('combobox',{name:'Choose a conversation',exact:true})).toContainText('Saved conversation');
 await expect(editor().getByRole('combobox',{name:'Response (optional)',exact:true})).toContainText('Saved response');
 await editor().getByLabel('Note',{exact:true}).fill('My edited note');
 let release,seen;const held=new Promise(r=>release=r),entered=new Promise(r=>seen=r);
 await page.route('**'+prefix+'/entries/'+old.id+'*',async route=>{if(route.request().method()==='PUT'){seen();await held;}await route.continue();});
 await editor().getByRole('button',{name:'Save changes'}).click();await entered;
 await expect(editor().getByLabel('Note',{exact:true})).toBeDisabled();
 await page.keyboard.press('Escape');await expect(editor()).toBeVisible();
 release();await expect(editor()).toHaveCount(0);
 const reread=await api('conversation-bookmarks','/entries/'+old.id);expect(reread.session_id).toBe('pruned-session');expect(reread.message_id).toBe(44);expect(reread.source_status).toBe('session_missing');expect(reread.note).toBe('My edited note');
 await api('conversation-bookmarks',`/entries/${old.id}?revision=${reread.revision}`,{method:'DELETE'});
 await page.unroute('**'+prefix+'/entries/'+old.id+'*');
 await page.unroute('**'+prefix+'/sources/**');
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 expect(writes.filter(w=>w.method==='POST')).toHaveLength(1);
 sourceBank.restore();
 // No source mocks for this smoke: real backend enumeration → native choices
 // → real creation/readback, with only assistant visible text in the picker.
 await page.getByRole('button',{name:'Save bookmark',exact:true}).click();
 await choose('Choose a conversation','Native source conversation');
 await choose('Response (optional)','Native assistant preview from the real source API.');
 for(const width of [360,1440]){
  await page.setViewportSize({width,height:1100});
  expect(await editor().evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.screenshot({path:join(proof,`selector-${adapter}-${width}.png`),fullPage:true});
 }

 await editor().getByLabel('Title',{exact:true}).fill('Native selectors verified');
 await editor().getByRole('button',{name:'Save bookmark',exact:true}).click();await expect(editor()).toHaveCount(0);
 const native=(await api('conversation-bookmarks','/entries')).items.find(x=>x.title==='Native selectors verified');
 expect(native.session_id).toBe(session);expect(native.message_id).toBe(1);expect(native.note).toBe('');
 await api('conversation-bookmarks',`/entries/${native.id}?revision=${native.revision}`,{method:'DELETE'});
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 console.log('PASS selectors',adapter,'default/null, title, notes, pagination, search races, response reset, errors/retry/empty, old refs, pending save');
}
