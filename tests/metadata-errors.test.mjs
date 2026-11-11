import test from 'node:test';
import assert from 'node:assert/strict';
import {metadataFeedback} from '../ui/metadata-errors.js';

const fallback = {field: null, tagIndex: null, message: 'Details could not be validated. Review your entries and try again.'};
const cases = [
  ['title/type', 'title', null, 'Enter text for Title.'],
  ['description/type', 'description', null, 'Enter text for Description.'],
  ['tags/type', 'tags', null, 'Enter tags as text.'],
  ['tags[0]/type', 'tags', 0, 'Enter text for Tag 1.'],
  ['title/scalar_limit', 'title', null, 'Use 1–160 characters for Title.'],
  ['description/scalar_limit', 'description', null, 'Use at most 4,000 characters for Description.'],
  ['tags/scalar_limit', 'tags', null, 'Use at most 20 tags.'],
  ['tags[19]/scalar_limit', 'tags', 19, 'Use 1–40 characters for Tag 20.'],
  ['title/control', 'title', null, 'Delete and retype the affected text in Title.'],
  ['description/control', 'description', null, 'Delete and retype the affected text in Description.'],
  ['tags[2]/control', 'tags', 2, 'Delete and retype the affected text in Tag 3.'],
  ['title/edge_whitespace', 'title', null, 'Remove starting or ending whitespace from Title.'],
  ['tags[2]/edge_whitespace', 'tags', 2, 'Remove starting or ending whitespace from Tag 3.'],
  ['tags[2]/blank', 'tags', 2, 'Enter non-whitespace text for Tag 3.'],
  ['tags/duplicate', 'tags', null, 'Remove repeated tags, including capitalization variants.'],
  ['tags[2]/duplicate', 'tags', 2, 'Remove repeated tags, including capitalization variants.'],
  ['title/generated_value', 'title', null, 'Enter Title yourself or Generate again.'],
  ['description/generated_value', 'description', null, 'Enter Description yourself or Generate again.'],
  ['tags/generated_value', 'tags', null, 'Enter Tags yourself or Generate again.'],
  ['tags[2]/generated_value', 'tags', 2, 'Enter Tag 3 yourself or Generate again.'],
  ['title/missing', 'title', null, 'Enter Title; Description and Tags may be empty.'],
  ['description/missing', 'description', null, 'Enter Description; Description and Tags may be empty.'],
  ['tags/missing', 'tags', null, 'Enter Tags; Description and Tags may be empty.'],
];
for (const [reason, field, tagIndex, message] of cases) {
  test(`safe field feedback for ${reason}`, () => {
    assert.deepEqual(metadataFeedback({code: 'metadata_invalid', message: `Invalid metadata: ${reason}`}), {field, tagIndex, message});
  });
}

test('unknown, malformed and inapplicable errors never echo server content', () => {
  for (const message of ['secret/path/token', 'Invalid metadata: tags[20]/blank',
    'Invalid metadata: tags[01]/blank', 'Invalid metadata: tags[-1]/blank',
    'Invalid metadata: description/blank', 'Invalid metadata: description/edge_whitespace',
    'Invalid metadata: title/duplicate', 'Invalid metadata: tags/control',
    'Invalid metadata: tags[0]/missing', 'Invalid metadata: title/blank\n',
    'Invalid metadata: title/blank EXTRA', 'Invalid metadata: title/unknown', null, 42]) {
    assert.deepEqual(metadataFeedback({code: 'metadata_invalid', message}), fallback);
  }
  for (const error of [null, undefined, {}, {code: 'other', message: 'Invalid metadata: title/blank'}]) {
    assert.deepEqual(metadataFeedback(error), fallback);
  }
});

test('a known validation error identifies the field with safe corrective copy', () => {
  assert.deepEqual(metadataFeedback({code: 'metadata_invalid', message: 'Invalid metadata: title/blank'}), {
    field: 'title', tagIndex: null, message: 'Enter non-whitespace text for Title.',
  });
});
