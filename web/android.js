// Promise adapters for asynchronous AndroidMusic bridge calls.
window.onAndroidDownloadReady = error => {
  const pending = window.androidDownloadPending;
  window.androidDownloadPending = null;
  if (!pending) return;
  if (error) pending.reject(new Error(error)); else pending.resolve();
};

function downloadWithAndroidYtDlp(source, metadata) {
  return new Promise((resolve, reject) => {
    let settled = false;
    window.onAndroidNativeDownloadComplete = (error, filename, warning, lyricsStatus) => {
      if (settled) return;
      settled = true;
      window.onAndroidNativeDownloadComplete = null;
      if (error) reject(new Error(error));
      else resolve({filename, warning, lyricsStatus: lyricsStatus || ''});
    };
    try {
      const error = AndroidMusic.downloadWithYtDlp(source, JSON.stringify(metadata || {}));
      if (error) {
        settled = true;
        window.onAndroidNativeDownloadComplete = null;
        reject(new Error(error));
      }
    } catch (error) {
      settled = true;
      window.onAndroidNativeDownloadComplete = null;
      reject(error);
    }
  });
}

function lookupWithAndroidMusicBrainz(query) {
  return new Promise((resolve, reject) => {
    let settled = false;
    window.onAndroidNativeMetadataComplete = (error, metadata) => {
      if (settled) return;
      settled = true;
      window.onAndroidNativeMetadataComplete = null;
      if (error) reject(new Error(error));
      else {
        try { resolve(JSON.parse(metadata)); }
        catch (_) { reject(new Error('MusicBrainz 返回了无法读取的曲目信息。')); }
      }
    };
    try {
      const error = AndroidMusic.searchMusicBrainz(query);
      if (error) {
        settled = true;
        window.onAndroidNativeMetadataComplete = null;
        reject(new Error(error));
      }
    } catch (error) {
      settled = true;
      window.onAndroidNativeMetadataComplete = null;
      reject(error);
    }
  });
}

function lookupLyricsOnAndroid(title, artist) {
  return new Promise((resolve, reject) => {
    let settled = false;
    window.onAndroidNativeLyricsComplete = (error, result) => {
      if (settled) return;
      settled = true;
      window.onAndroidNativeLyricsComplete = null;
      if (error) reject(new Error(error));
      else {
        try { resolve(JSON.parse(result)); }
        catch (_) { reject(new Error('LRCLIB 返回了无法读取的歌词。')); }
      }
    };
    try {
      const error = AndroidMusic.lookupLyrics(title, artist || '');
      if (error) {
        settled = true;
        window.onAndroidNativeLyricsComplete = null;
        reject(new Error(error));
      }
    } catch (error) {
      settled = true;
      window.onAndroidNativeLyricsComplete = null;
      reject(error);
    }
  });
}

function lookupWithAndroidYtDlp(source) {
  return new Promise((resolve, reject) => {
    let settled = false;
    window.onAndroidNativeMetadataComplete = (error, metadata) => {
      if (settled) return;
      settled = true;
      window.onAndroidNativeMetadataComplete = null;
      if (error) reject(new Error(error));
      else {
        try { resolve(JSON.parse(metadata)); }
        catch (_) { reject(new Error('手机端返回了无法读取的曲目信息。')); }
      }
    };
    try {
      const error = AndroidMusic.lookupWithYtDlp(source);
      if (error) {
        settled = true;
        window.onAndroidNativeMetadataComplete = null;
        reject(new Error(error));
      }
    } catch (error) {
      settled = true;
      window.onAndroidNativeMetadataComplete = null;
      reject(error);
    }
  });
}

async function searchAndroidKeywordWithFallback(query) {
  try {
    return {metadata: await lookupWithAndroidMusicBrainz(query), provider: 'MusicBrainz'};
  } catch (musicBrainzError) {
    try {
      const metadata = await lookupWithAndroidYtDlp(`ytsearch1:${query}`);
      return {metadata, provider: 'yt-dlp', musicBrainzError};
    } catch (ytDlpError) {
      const mbMessage = musicBrainzError && musicBrainzError.message ? musicBrainzError.message : String(musicBrainzError);
      const ytMessage = ytDlpError && ytDlpError.message ? ytDlpError.message : String(ytDlpError);
      throw new Error(`MusicBrainz 搜索失败（${mbMessage}）；yt-dlp 备用搜索也失败（${ytMessage}）。`);
    }
  }
}

function fetchCandidatesOnAndroid(query) {
  return new Promise((resolve, reject) => {
    window.onAndroidCandidatesComplete = (error, result) => {
      window.onAndroidCandidatesComplete = null;
      if (error) reject(new Error(error));
      else { try { resolve(JSON.parse(result).candidates || []); } catch (_) { reject(new Error('无法读取匹配结果')); } }
    };
    try {
      const error = AndroidMusic.searchCandidates(query);
      if (error) { window.onAndroidCandidatesComplete = null; reject(new Error(error)); }
    } catch (error) { window.onAndroidCandidatesComplete = null; reject(error); }
  });
}
