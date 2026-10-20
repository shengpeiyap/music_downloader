// Sort displayed library results by track title without changing the queue or
// the underlying track indices. Numeric-aware collation keeps 2 before 10.
window.sortLibraryTracks = function (tracks) {
  const collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
  return tracks.slice().sort((a, b) => collator.compare(a.title || '', b.title || '') ||
    collator.compare(a.artist || '', b.artist || '') ||
    collator.compare(a.album || '', b.album || '') ||
    collator.compare(a.folderPath || '', b.folderPath || ''));
};
