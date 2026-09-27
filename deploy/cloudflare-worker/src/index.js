const ALLOWED_FILES = new Set(["epg.xml", "epg.xml.gz", "playlist.m3u", "status.json"]);

function response(message, status) {
  return new Response(message, {
    status,
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return response("Method not allowed", 405);
    }
    if (url.pathname === "/healthz") {
      return response("ok", 200);
    }

    // Public URL: /v1/<delivery-token>/<profile>/<filename>
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length !== 4 || parts[0] !== "v1") {
      return response("Not found", 404);
    }
    const [, suppliedToken, profile, filename] = parts;
    if (!env.DELIVERY_TOKEN || suppliedToken !== env.DELIVERY_TOKEN) {
      return response("Not found", 404);
    }
    if (!/^[a-zA-Z0-9_-]{1,64}$/.test(profile) || !ALLOWED_FILES.has(filename)) {
      return response("Not found", 404);
    }

    const prefix = (env.OBJECT_PREFIX || "v1").replace(/^\/+|\/+$/g, "");
    const object = await env.EPG_BUCKET.get(`${prefix}/${profile}/${filename}`);
    if (!object) {
      return response("Not generated yet", 404);
    }
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("cache-control", "public, max-age=60, stale-while-revalidate=300");
    if (filename.endsWith(".gz")) {
      headers.set("content-type", "application/gzip");
      headers.delete("content-encoding");
    }
    return new Response(request.method === "HEAD" ? null : object.body, { headers });
  },
};
