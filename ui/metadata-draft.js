// Local form state only: these identity keys are fences, not authentication.
// Server metadata validation, cancellation and durable Save remain adapter duties.
const FIELDS = Object.freeze(['description', 'tags', 'title']);
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const valid = (field, value) => field === 'tags'
  ? Array.isArray(value) && value.every(item => typeof item === 'string')
  : typeof value === 'string';
const copy = value => Array.isArray(value) ? Object.freeze([...value]) : value;
const record = value => Object.freeze(value);
const eligible = (state, field) => state.values[field].length === 0 || state.provenance[field] === 'default';

export function createDraft(ownerKey, sourceKey, values = {}, provenance = {}) {
  if (typeof ownerKey !== 'string' || !ownerKey || typeof sourceKey !== 'string' || !sourceKey) {
    throw new TypeError('Explicit form identity required');
  }
  const initial = {}, origins = {};
  for (const field of FIELDS) {
    const value = own(values, field) ? values[field] : field === 'tags' ? [] : '';
    const origin = own(provenance, field) ? provenance[field] : 'default';
    if (!valid(field, value) || !['default', 'user'].includes(origin)) throw new TypeError('Invalid field state');
    initial[field] = copy(value);
    origins[field] = origin;
  }
  return record({ownerKey, sourceKey, values: record(initial), provenance: record(origins), revision: 0, pending: null});
}

export function editField(state, field, value) {
  if (!FIELDS.includes(field) || !valid(field, value)) throw new TypeError('Invalid field edit');
  return record({...state, values: record({...state.values, [field]: copy(value)}),
    provenance: record({...state.provenance, [field]: 'user'}), revision: state.revision + 1});
}

export function beginGeneration(state) {
  const requested = FIELDS.filter(field => eligible(state, field));
  if (state.pending || !requested.length) return {state, capture: null, request: null};
  const supplied = Object.fromEntries(FIELDS.filter(field => !requested.includes(field))
    .map(field => [field, copy(state.values[field])]));
  const request = record({requested_fields: Object.freeze(requested), supplied_metadata: record(supplied)});
  // Object identity separates independently created drafts even with equal keys.
  const capture = record({ownerKey: state.ownerKey, sourceKey: state.sourceKey, revision: state.revision, request});
  return {state: record({...state, pending: capture}), capture, request};
}

export function invalidateGeneration(state) {
  // This only fences UI application; it does NOT certify remote work has stopped.
  return record({...state, revision: state.revision + 1, pending: null});
}

export function applyGeneration(state, capture, generated) {
  const current = capture && state.pending === capture;
  const settled = current ? record({...state, pending: null}) : state;
  if (!current || state.ownerKey !== capture.ownerKey || state.sourceKey !== capture.sourceKey
      || state.revision !== capture.revision) return {state: settled, applied: false, reason: 'stale'};
  const fields = capture.request.requested_fields;
  if (!generated || typeof generated !== 'object' || Array.isArray(generated)
      || Object.keys(generated).length !== fields.length
      || !fields.every(field => own(generated, field) && valid(field, generated[field]))) {
    return {state: settled, applied: false, reason: 'invalid_result'};
  }
  const values = {...state.values}, provenance = {...state.provenance};
  for (const field of fields) {
    values[field] = copy(generated[field]);
    provenance[field] = 'default';
  }
  return {state: record({...settled, values: record(values), provenance: record(provenance),
    revision: state.revision + 1}), applied: true, reason: null};
}
