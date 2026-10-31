// The former standalone harness mocked host controls and asserted retired
// raw-ID/44px styling. Its metadata regressions now live in metadata-browser.mjs
// alongside selector-browser.mjs, both run through real components and loaders.
// Keep this npm test:browser entrypoint; paired sources are preflighted by runner.
process.env.SAVED_SCENARIOS ||= 'both';
await import('./saved-browser.mjs');
