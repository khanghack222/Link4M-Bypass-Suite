/**
 * Catch-all inbox for signup verification.
 *
 * Email Routing sends every `*@yourdomain` message here; the worker stores the
 * subject, sender and raw body in KV for 24 h. The CLI polls:
 *
 *   GET /inbox?to=alias@yourdomain
 *   Authorization: Bearer <MAIL_SECRET>
 *
 * Bind a KV namespace as INBOX and set MAIL_SECRET:
 *
 *   wrangler kv namespace create INBOX
 *   wrangler secret put MAIL_SECRET
 *   wrangler deploy
 */

const MAX_BODY = 64 * 1024;
const TTL = 24 * 60 * 60;

export default {
  async email(message, env) {
    const raw = await new Response(message.raw).text();
    const record = {
      at: Date.now(),
      from: message.from,
      to: message.to,
      subject: message.headers.get("subject") || "",
      text: extractText(raw).slice(0, MAX_BODY),
    };
    const key = `inbox:${message.to.toLowerCase()}`;
    const existing = JSON.parse((await env.INBOX.get(key)) || "[]");
    existing.push(record);
    // Keep the last 20 messages per address.
    await env.INBOX.put(key, JSON.stringify(existing.slice(-20)), {
      expirationTtl: TTL,
    });
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/inbox") {
      return new Response("not found", { status: 404 });
    }
    const auth = request.headers.get("authorization") || "";
    if (auth !== `Bearer ${env.MAIL_SECRET}`) {
      return new Response("forbidden", { status: 403 });
    }
    const to = (url.searchParams.get("to") || "").toLowerCase();
    if (!to) {
      return Response.json({ messages: [] });
    }
    const rows = JSON.parse((await env.INBOX.get(`inbox:${to}`)) || "[]");
    return Response.json({ messages: rows.reverse() });
  },
};

/** Pull the text/plain part out of a raw MIME message without dependencies. */
function extractText(raw) {
  const split = raw.split(/\r?\n\r?\n/);
  if (split.length < 2) return raw;
  const body = split.slice(1).join("\n\n");
  const plain = body.match(
    /Content-Type:\s*text\/plain[^\n]*\n(?:[^\n]+\n)*\n([\s\S]*?)(?:\n--|\nContent-Type:|$)/i
  );
  const source = plain ? plain[1] : body;
  return decodeQuotedPrintable(source)
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/[ \t]+/g, " ")
    .trim();
}

function decodeQuotedPrintable(text) {
  return text
    .replace(/=\r?\n/g, "")
    .replace(/=([0-9A-F]{2})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}
