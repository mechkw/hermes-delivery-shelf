import test from 'node:test';
import assert from 'node:assert/strict';
import {createDraft, editField, beginGeneration, applyGeneration, invalidateGeneration} from '../ui/metadata-draft.js';

const draft = (values = {}, provenance = {}) => createDraft('owner-A', 'source-A', values, provenance);
const answer = {description: 'Suggested description', tags: ['report'], title: 'Suggested title'};

test('Generate requests empty/default fields and preserves typed bytes', () => {
  let state = draft({title: 'Default title'});
  state = editField(state, 'title', 'Default title');
  const started = beginGeneration(state);
  assert.deepEqual(started.request, {requested_fields: ['description', 'tags'], supplied_metadata: {title: 'Default title'}});
  const result = applyGeneration(started.state, started.capture, {description: answer.description, tags: answer.tags});
  assert.equal(result.applied, true);
  assert.deepEqual(result.state.values, {...answer, title: 'Default title'});
});

test('suggestions remain default until edited; clearing makes a field eligible', () => {
  let started = beginGeneration(draft());
  let state = applyGeneration(started.state, started.capture, answer).state;
  assert.deepEqual(beginGeneration(state).request.requested_fields, ['description', 'tags', 'title']);
  state = editField(state, 'description', answer.description);
  assert.equal(state.provenance.description, 'user');
  state = editField(state, 'description', '');
  assert.ok(beginGeneration(state).request.requested_fields.includes('description'));
});

test('nonempty whitespace is user input, not silently stripped', () => {
  const state = draft({title: ' ', description: '\t', tags: [' x ']}, {title: 'user', description: 'user', tags: 'user'});
  assert.equal(beginGeneration(state).request, null);
  assert.deepEqual(state.values, {title: ' ', description: '\t', tags: [' x ']});
});

test('any edit during a request discards the entire response', () => {
  const started = beginGeneration(draft());
  const edited = editField(started.state, 'title', 'My title');
  const result = applyGeneration(edited, started.capture, answer);
  assert.equal(result.applied, false);
  assert.equal(result.reason, 'stale');
  assert.deepEqual(result.state.values, {title: 'My title', description: '', tags: []});
  assert.equal(result.state.pending, null);
});

test('edit then restore the original text still invalidates the response', () => {
  const started = beginGeneration(draft());
  const edited = editField(editField(started.state, 'title', 'temporary'), 'title', '');
  assert.equal(applyGeneration(edited, started.capture, answer).applied, false);
});

test('reset source/owner, cancel and duplicate delivery cannot apply old results', () => {
  const started = beginGeneration(draft());
  for (const state of [draft(), createDraft('owner-B', 'source-A'), createDraft('owner-A', 'source-B'), invalidateGeneration(started.state)]) {
    assert.equal(applyGeneration(state, started.capture, answer).applied, false);
  }
  const done = applyGeneration(started.state, started.capture, answer);
  assert.equal(applyGeneration(done.state, started.capture, answer).applied, false);
});

test('in-flight generation cannot start a second request', () => {
  const started = beginGeneration(draft());
  assert.equal(beginGeneration(started.state).request, null);
});

test('malformed or extra response fields cannot partially overwrite the form', () => {
  for (const value of [{title: 'Only title'}, {...answer, extra: true}, {...answer, tags: 'report'}, {...answer, description: null}]) {
    const started = beginGeneration(draft());
    const result = applyGeneration(started.state, started.capture, value);
    assert.equal(result.applied, false);
    assert.equal(result.reason, 'invalid_result');
    assert.deepEqual(result.state.values, {title: '', description: '', tags: []});
  }
});

test('caller mutations cannot alter retained values or generation requests', () => {
  const tags = ['typed'];
  const state = draft({tags}, {tags: 'user'});
  tags.push('changed');
  const started = beginGeneration(state);
  assert.deepEqual(started.request.supplied_metadata.tags, ['typed']);
  assert.throws(() => started.request.supplied_metadata.tags.push('changed'), TypeError);
  assert.deepEqual(state.values.tags, ['typed']);
});
