"""CatPawOpen bundle export helpers for Miraplay."""

import hashlib
import json


SITE_KEY = "local_video_aggregator"
SITE_NAME = "本地视频聚合"
SITE_TYPE = 3


def build_catopen_bundle(remote_base):
    runtime = _build_runtime_script(remote_base)
    # Miraplay/CatPawOpen expects an index.js that defines websiteBundle().
    return "globalThis.websiteBundle = function() { return " + json.dumps(runtime, ensure_ascii=False) + "; };"


def _build_runtime_script(remote_base):
    base = str(remote_base or "").rstrip("/")
    base_json = json.dumps(base, ensure_ascii=False)
    key_json = json.dumps(SITE_KEY, ensure_ascii=False)
    name_json = json.dumps(SITE_NAME, ensure_ascii=False)
    type_json = str(int(SITE_TYPE))
    return f"""(function() {{
  const exports = {{}};
  const module = {{ exports }};
  const REMOTE_BASE = {base_json};
  const SITE_KEY = {key_json};
  const SITE_NAME = {name_json};
  const SITE_TYPE = {type_json};
  const SITE_PREFIX = '/spider/' + SITE_KEY + '/' + SITE_TYPE;
  let server = null;
  let httpMod = null;
  let httpsMod = null;

  async function loadModules() {{
    if (!httpMod) httpMod = await import('node:http');
    if (!httpsMod) httpsMod = await import('node:https');
    return {{ httpMod, httpsMod }};
  }}

  async function requestText(url, options, body) {{
    const mods = await loadModules();
    const request = String(url).startsWith('https://') ? mods.httpsMod.request : mods.httpMod.request;
    return await new Promise((resolve, reject) => {{
      const req = request(url, options || {{}}, (resp) => {{
        let chunks = '';
        resp.setEncoding('utf8');
        resp.on('data', (chunk) => {{
          chunks += chunk;
        }});
        resp.on('end', () => {{
          if (resp.statusCode && resp.statusCode >= 400) {{
            reject(new Error('HTTP ' + resp.statusCode + ' ' + url));
            return;
          }}
          resolve(chunks);
        }});
      }});
      req.on('error', reject);
      if (body) req.write(body);
      req.end();
    }});
  }}

  async function requestJson(url, options, body) {{
    const text = await requestText(url, options, body);
    return JSON.parse(text || '{{}}');
  }}

  function readBody(req) {{
    return new Promise((resolve) => {{
      let raw = '';
      req.setEncoding('utf8');
      req.on('data', (chunk) => {{
        raw += chunk;
      }});
      req.on('end', () => {{
        if (!raw) {{
          resolve({{}});
          return;
        }}
        try {{
          resolve(JSON.parse(raw));
        }} catch (_err) {{
          resolve({{}});
        }}
      }});
    }});
  }}

  function sendJson(res, payload, status) {{
    const text = JSON.stringify(payload);
    res.writeHead(status || 200, {{
      'Content-Type': 'application/json; charset=utf-8',
      'Content-Length': Buffer.byteLength(text),
      'Access-Control-Allow-Origin': '*',
    }});
    res.end(text);
  }}

  async function fetchCms(query) {{
    return await requestJson(REMOTE_BASE + '/api/tvbox/cms' + (query || ''), {{
      method: 'GET',
      headers: {{
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
      }},
    }});
  }}

  async function home() {{
    const data = await fetchCms('');
    return {{
      class: Array.isArray(data.class) ? data.class : [],
    }};
  }}

  async function category(body) {{
    const page = Number(body.page || 1) || 1;
    const typeId = encodeURIComponent(body.id || '__all__');
    const data = await fetchCms('?t=' + typeId + '&pg=' + page);
    return {{
      page: Number(data.page || page) || page,
      pagecount: Number(data.pagecount || 0) || 0,
      total: Number(data.total || 0) || 0,
      list: Array.isArray(data.list) ? data.list : [],
    }};
  }}

  async function detail(body) {{
    const ids = Array.isArray(body.id) ? body.id : [body.id];
    const results = [];
    for (const id of ids) {{
      if (!id) continue;
      const data = await fetchCms('?ids=' + encodeURIComponent(id));
      if (data && Array.isArray(data.list) && data.list.length) {{
        results.push(data.list[0]);
      }}
    }}
    return {{
      list: results,
    }};
  }}

  async function play(body) {{
    return {{
      parse: 0,
      url: body.id || '',
    }};
  }}

  async function search(body) {{
    const wd = encodeURIComponent(body.wd || '');
    const page = Number(body.page || 1) || 1;
    const data = await fetchCms('?wd=' + wd + '&pg=' + page);
    return {{
      page: Number(data.page || page) || page,
      pagecount: Number(data.pagecount || 0) || 0,
      total: Number(data.total || 0) || 0,
      list: Array.isArray(data.list) ? data.list : [],
    }};
  }}

  async function route(req, res) {{
    const url = new URL(req.url, 'http://127.0.0.1');
    if (req.method === 'GET' && url.pathname === '/check') {{
      sendJson(res, {{ run: !server || !server.stop }});
      return;
    }}
    if (req.method === 'GET' && url.pathname === '/config') {{
      sendJson(res, {{
        video: {{
          sites: [{{
            key: SITE_KEY,
            name: SITE_NAME,
            type: SITE_TYPE,
            api: SITE_PREFIX,
          }}],
        }},
        read: {{ sites: [] }},
        comic: {{ sites: [] }},
        music: {{ sites: [] }},
        pan: {{ sites: [] }},
        color: [],
      }});
      return;
    }}
    if (req.method !== 'POST') {{
      sendJson(res, {{ error: 'not found' }}, 404);
      return;
    }}

    const body = await readBody(req);
    try {{
      if (url.pathname === SITE_PREFIX + '/init') {{
        sendJson(res, {{}});
        return;
      }}
      if (url.pathname === SITE_PREFIX + '/home') {{
        sendJson(res, await home());
        return;
      }}
      if (url.pathname === SITE_PREFIX + '/category') {{
        sendJson(res, await category(body));
        return;
      }}
      if (url.pathname === SITE_PREFIX + '/detail') {{
        sendJson(res, await detail(body));
        return;
      }}
      if (url.pathname === SITE_PREFIX + '/play') {{
        sendJson(res, await play(body));
        return;
      }}
      if (url.pathname === SITE_PREFIX + '/search') {{
        sendJson(res, await search(body));
        return;
      }}
    }} catch (error) {{
      sendJson(res, {{ error: error && error.message ? error.message : String(error) }}, 500);
      return;
    }}

    sendJson(res, {{ error: 'not found' }}, 404);
  }}

  module.exports.start = async function start(_config) {{
    const mods = await loadModules();
    server = mods.httpMod.createServer((req, res) => {{
      route(req, res);
    }});
    server.stop = false;
    const originalAddress = server.address.bind(server);
    server.address = function() {{
      const result = originalAddress();
      if (result && typeof result === 'object') {{
        result.url = 'http://' + result.address + ':' + result.port;
        result.dynamic = 'js2p://_WEB_';
      }}
      return result;
    }};
    await new Promise((resolve) => {{
      server.listen(0, '127.0.0.1', resolve);
    }});
  }};

  module.exports.stop = async function stop() {{
    if (!server) return;
    server.stop = true;
    await new Promise((resolve) => server.close(resolve));
    server = null;
  }};

  return module.exports;
}})();"""


def build_catopen_md5(bundle_text):
    payload = bundle_text.encode("utf-8")
    return hashlib.md5(payload).hexdigest()
