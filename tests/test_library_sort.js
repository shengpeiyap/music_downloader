const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const librarySort = fs.readFileSync(path.join(__dirname, '..', 'library_sort.js'), 'utf8');
const window = {};
vm.runInNewContext(librarySort, {window, Intl});

const tracks = [
  {id: 'ten', title: 'Track 10', artist: 'A'},
  {id: 'two', title: 'Track 2', artist: 'A'},
  {id: 'same-z', title: 'Alpha', artist: 'Z'},
  {id: 'same-a', title: 'alpha', artist: 'A'},
];
const sorted = window.sortLibraryTracks(tracks);

assert.deepEqual(sorted.map(track => track.id), ['same-a', 'same-z', 'two', 'ten']);
assert.deepEqual(tracks.map(track => track.id), ['ten', 'two', 'same-z', 'same-a']);
