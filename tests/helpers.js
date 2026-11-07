// Test helpers (not a test file itself).
const fs = require('node:fs');
const path = require('node:path');

const CODE_DIR = path.join(__dirname, '..', 'n8n', 'code');
const SHEET_DIR = path.join(__dirname, '..', 'sheet');

/**
 * Load n8n snippets the way they are pasted: concatenated, in order, into one
 * scope. Returns the exports of each file, merged. This also catches duplicate
 * declarations between snippets that share a Code node.
 */
function loadSnippets(...names) {
  const merged = {};
  const parts = names.map((name) => fs.readFileSync(path.join(CODE_DIR, name), 'utf8'));
  // Run all files in one function scope; collect each file's module.exports as it is assigned.
  const module = {};
  let exportsSeen = {};
  Object.defineProperty(module, 'exports', {
    get: () => exportsSeen,
    set: (value) => { exportsSeen = value; Object.assign(merged, value); },
  });
  new Function('module', parts.join('\n;\n'))(module);
  return merged;
}

/** Minimal CSV parser (quoted fields, commas inside quotes) returning row objects. */
function readCsv(name) {
  const text = fs.readFileSync(path.join(SHEET_DIR, name), 'utf8').replace(/\r\n/g, '\n').trim();
  const rows = text.split('\n').map((line) => {
    const out = [];
    let cur = '';
    let quoted = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (ch === '"') quoted = false;
        else cur += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ',') { out.push(cur); cur = ''; }
      else cur += ch;
    }
    out.push(cur);
    return out;
  });
  const [header, ...body] = rows;
  return body.map((cells) => Object.fromEntries(header.map((h, i) => [h, cells[i] ?? ''])));
}

module.exports = { loadSnippets, readCsv };
