// Shared page helpers and desktop API routing.
const $ = id => document.getElementById(id);
// Text injected into areas the page translator leaves alone (lyrics, track lists) goes through here.
const ui = text => (window.translateUi ? window.translateUi(text) : text);
function friendlyMessage(value) {
  // Show users a plain sentence: drop exception class prefixes such as "ValueError: ".
  let text = String(value && value.message !== undefined ? value.message : (value || '')).trim();
  text = text.replace(/^(?:[A-Za-z_][\w.]*\.)?[A-Za-z_]\w*(?:Error|Exception):\s*/, '');
  if (/Failed to fetch|NetworkError|Load failed/i.test(text)) return '网络连接失败，请检查网络后重试。';
  if (/confirm you.{0,3}re not a bot|sign in to confirm/i.test(text)) return 'YouTube 暂时要求验证身份（移动网络或共享网络上常见）。请换一个 Wi‑Fi 或稍后重试，也可以连接电脑后再下载。';
  return text;
}
const escapeHTML = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function responseFilename(response, fallback) {
  const header = response.headers.get('Content-Disposition') || '';
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (!encoded) return fallback;
  try { return decodeURIComponent(encoded[1]); } catch (_) { return fallback; }
}
async function saveApiResponse(response, fallbackName) {
  const filename = responseFilename(response, fallbackName);
  if (window.AndroidMusic) {
    await new Promise((resolve, reject) => {
      window.androidDownloadPending = {resolve, reject};
      AndroidMusic.createDownload(filename, response.headers.get('Content-Type') || 'application/octet-stream');
    });
    try {
      const reader = response.body.getReader();
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        for (let offset = 0; offset < value.length; offset += 192 * 1024) {
          const piece = value.subarray(offset, Math.min(offset + 192 * 1024, value.length));
          let binary = '';
          for (let i = 0; i < piece.length; i++) binary += String.fromCharCode(piece[i]);
          const error = AndroidMusic.writeDownloadChunk(window.btoa(binary));
          if (error) throw new Error(error);
        }
      }
      const finishError = AndroidMusic.finishDownload();
      if (finishError) throw new Error(finishError);
      return filename;
    } catch (error) {
      AndroidMusic.cancelDownload();
      throw error;
    }
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  return filename;
}
function shouldProcessOnAndroid() { return !!window.AndroidMusic && !androidApiConnected; }
function requestMusicDeskApi(path, options) {
  if (window.AndroidMusic && /^\/api\//.test(path)) {
    if (!androidApiConnected || !androidApiConfig || !androidApiConfig.url || !androidApiConfig.token) {
      return Promise.reject(new Error('此功能已锁定。请先连接电脑上的 MusicDesk 服务，确认 API 匹配后再使用。'));
    }
    const headers = {...(options && options.headers || {}), Authorization: `Bearer ${androidApiConfig.token}`};
    return fetch(`${androidApiConfig.url}${path}`, {...options, headers}).then(response => {
      if (response.status === 401) {
        androidApiConnected = false;
        updateApiConnectionMessage(false, '配对密钥无效或已过期；功能已锁定，请重新连接。');
      }
      return response;
    }).catch(error => {
      if (error instanceof TypeError) {
        androidApiConnected = false;
        updateApiConnectionMessage(false, '电脑服务无法访问；在线功能已锁定。请确认电脑服务运行中且手机和电脑在同一 Wi‑Fi。');
      }
      throw error;
    });
  }
  return fetch(path, options);
}
