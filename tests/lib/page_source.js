// Read a page together with every local script and stylesheet it loads (mirrors
// tools/page_assets.py). Code is being split out of index.html into web/*.js, and the
// regression tests look functions up by name; they must keep finding them after a move.
const fs = require('node:fs');
const path = require('node:path');

function localAssets(html) {
  const refs = [];
  const tag = /<script\b[^>]*\bsrc="([^"]+)"|<link\b[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"/g;
  let match;
  while ((match = tag.exec(html))) {
    const ref = match[1] || match[2];
    if (!/^(?:[a-z]+:)?\/\//i.test(ref) && !refs.includes(ref)) refs.push(ref);
  }
  return refs;
}

function readPage(pagePath) {
  const html = fs.readFileSync(pagePath, 'utf8');
  const parts = [html];
  for (const ref of localAssets(html)) {
    parts.push(`\n/* ---- ${ref} ---- */\n` + fs.readFileSync(path.join(path.dirname(pagePath), ref), 'utf8'));
  }
  return parts.join('');
}

module.exports = {localAssets, readPage};
