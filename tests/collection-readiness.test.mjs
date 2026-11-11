import test from 'node:test';
import assert from 'node:assert/strict';
import {chromium,expect} from '@playwright/test';
import {refreshCollection} from './review-browser.mjs';

// A deterministic harness-contract fixture, not product UI acceptance. Native
// React/backend reproduction is retained separately with the diagnosis evidence.
for(const id of ['conversation-bookmarks','delivery-shelf'])test(`Refresh owns the completed ${id} reload, not a visible old card`,async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  const bookmarks=id==='conversation-bookmarks',owner=bookmarks?'cb-bookmarks':'ds-shelf',toolbar=bookmarks?'cb-toolbar':'ds-toolbar';
  const settled=bookmarks?'1 bookmark':'1 delivery',loading=bookmarks?'Loading bookmarks…':'Loading your shelf…';
  await page.setContent(`<section class="${owner}"><div class="${toolbar}"><span>${settled}</span><button>Refresh</button></div><article><button>Old title</button></article></section>`);
  await page.evaluate(({loading,settled})=>{
   window.phase='idle';window.begin=()=>{document.querySelector('span').textContent=loading;document.querySelector('article').remove();window.phase='loading';};
   window.complete=()=>{document.querySelector('span').textContent=settled;document.querySelector('section').insertAdjacentHTML('beforeend','<article><button>Old title</button></article>');window.phase='settled';};
   document.querySelector('.cb-toolbar button,.ds-toolbar button').onclick=()=>window.phase='scheduled';
  },{loading,settled});
  let finished=false;const refresh=refreshCollection(page,id).then(()=>{finished=true;});
  await page.waitForFunction(()=>window.phase==='scheduled');
  await expect(page.getByRole('button',{name:'Old title',exact:true})).toBeVisible();
  assert.equal(finished,false,'old visible card cannot satisfy Refresh readiness');
  await page.evaluate(()=>window.begin());
  await expect(page.getByRole('button',{name:'Old title',exact:true})).toHaveCount(0);
  assert.equal(finished,false,'loading is not completion');
  await page.evaluate(()=>window.complete());
  await refresh;
  const card=page.getByRole('button',{name:'Old title',exact:true});await card.scrollIntoViewIfNeeded();await expect(card).toBeInViewport({ratio:1});
  assert.equal(finished,true);
  // Replacing the owner is not completion of the observed collection reload.
  const replaced=assert.rejects(refreshCollection(page,id));
  await page.waitForFunction(()=>window.phase==='scheduled');
  await page.evaluate(()=>{const section=document.querySelector('section');section.replaceWith(section.cloneNode(true));});
  await replaced;
 }finally{await browser.close();}
});


// Explicit regression: both render commits finish before the helper's first
// readiness poll. No timer, sleep, retry, geometry relaxation or product edit.
for(const id of ['conversation-bookmarks','delivery-shelf'])test(`Refresh retains a fast ${id} loading/count cycle before its first poll`,async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  const bookmarks=id==='conversation-bookmarks',owner=bookmarks?'cb-bookmarks':'ds-shelf',toolbar=bookmarks?'cb-toolbar':'ds-toolbar';
  const settled=bookmarks?'1 bookmark':'1 delivery',loading=bookmarks?'Loading bookmarks…':'Loading your shelf…';
  await page.setContent(`<section class="${owner}"><div class="${toolbar}"><span>${settled}</span><button>Refresh</button></div><article><button>Current title</button></article></section>`);
  await page.evaluate(({loading,settled})=>{
   window.commits=[];document.querySelector('button').onclick=()=>{
    document.querySelector('span').textContent=loading;window.commits.push('loading');
    queueMicrotask(()=>{document.querySelector('span').textContent=settled;window.commits.push('settled');});
   };
  },{loading,settled});
  const realWait=page.waitForFunction.bind(page);let polled=false;
  page.waitForFunction=async(...args)=>{
   await realWait(()=>window.commits.length===2);
   assert.deepEqual(await page.evaluate(()=>window.commits),['loading','settled']);
   polled=true;return realWait(...args);
  };
  await refreshCollection(page,id);assert.equal(polled,true);
  const card=page.getByRole('button',{name:'Current title',exact:true});await card.scrollIntoViewIfNeeded();await expect(card).toBeInViewport({ratio:1});
 }finally{await browser.close();}
});
