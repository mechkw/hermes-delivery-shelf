// Server validation remains authoritative. Never echo arbitrary server prose.
const FALLBACK = 'Details could not be validated. Review your entries and try again.';
const fallback = () => ({field: null, tagIndex: null, message: FALLBACK});
const RULES = {
  type: (kind, label) => kind === 'tags' ? 'Enter tags as text.' : `Enter text for ${label}.`,
  scalar_limit: (kind, label) => ({title: 'Use 1–160 characters for Title.',
    description: 'Use at most 4,000 characters for Description.', tags: 'Use at most 20 tags.',
    tag: `Use 1–40 characters for ${label}.`})[kind],
  control: (kind, label) => kind !== 'tags' ? `Delete and retype the affected text in ${label}.` : null,
  edge_whitespace: (kind, label) => ['title', 'tag'].includes(kind) ? `Remove starting or ending whitespace from ${label}.` : null,
  blank: (kind, label) => ['title', 'tag'].includes(kind) ? `Enter non-whitespace text for ${label}.` : null,
  duplicate: kind => ['tags', 'tag'].includes(kind) ? 'Remove repeated tags, including capitalization variants.' : null,
  generated_value: (kind, label) => `Enter ${label} yourself or Generate again.`,
  missing: (kind, label) => kind !== 'tag' ? `Enter ${label}; Description and Tags may be empty.` : null,
};

export function metadataFeedback(error) {
  if (error?.code !== 'metadata_invalid' || typeof error.message !== 'string') return fallback();
  const match = /^Invalid metadata: (title|description|tags(?:\[([0-9]|1[0-9])\])?)\/(type|scalar_limit|control|edge_whitespace|blank|duplicate|generated_value|missing)$/.exec(error.message);
  // JavaScript's $ can match before a final newline: require the entire input.
  if (!match || match[0] !== error.message) return fallback();
  const tagIndex = match[2] === undefined ? null : Number(match[2]);
  const field = tagIndex === null ? match[1] : 'tags';
  const kind = tagIndex === null ? field : 'tag';
  const label = kind === 'tag' ? `Tag ${tagIndex + 1}` : {title: 'Title', description: 'Description', tags: 'Tags'}[field];
  const message = RULES[match[3]](kind, label);
  return message ? {field, tagIndex, message} : fallback();
}
