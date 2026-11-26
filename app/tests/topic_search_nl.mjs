// Runs web/words.js in a fresh context and ranks Dutch searches against the guides as the Dutch interface gets them.
// Usage: node topic_search_nl.mjs <words.js> <cases.json>; cases: {stop: [...], topics: [...], queries: [...]}.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const [, , wordsFile, casesFile] = process.argv;
const ctx = vm.createContext({});
vm.runInContext(readFileSync(wordsFile, 'utf8'), ctx, { filename: 'words.js' });
const W = ctx.SearchWords;
const c = JSON.parse(readFileSync(casesFile, 'utf8'));
const stop = new Set(c.stop);
const out = {};
for (const q of c.queries) out[q] = W.rankTopics(q, c.topics, stop).map(o => [o.t.id, o.c ? o.c.id : null]);
console.log(JSON.stringify(out));
