/**
 * Contract tests for bot_discord.js helpers, timeout values, and provider URL matching.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const bot = require("../bot_discord.js");

test("bot_discord.js contract - TASK_TIMEOUT_MS", () => {
    assert.equal(bot.TASK_TIMEOUT_MS, 480000, "TASK_TIMEOUT_MS must be 480 seconds (480,000 ms)");
});

test("bot_discord.js contract - extractDestinationUrl", () => {
    // Standard success payload from engine-rs
    const payload1 = { status: "success", destination_url: "https://mediafire.com/download/file123" };
    assert.equal(bot.extractDestinationUrl(payload1), "https://mediafire.com/download/file123");

    // Fallback key: destination
    const payload2 = { status: "ok", destination: "https://mega.nz/file/abc" };
    assert.equal(bot.extractDestinationUrl(payload2), "https://mega.nz/file/abc");

    // Fallback key: final_url
    const payload3 = { status: "success", final_url: "https://drive.google.com/open?id=xyz" };
    assert.equal(bot.extractDestinationUrl(payload3), "https://drive.google.com/open?id=xyz");

    // Fallback key: finalUrl (camelCase)
    const payload4 = { finalUrl: "https://example.com/target" };
    assert.equal(bot.extractDestinationUrl(payload4), "https://example.com/target");

    // Rejection on invalid / missing destination
    assert.equal(bot.extractDestinationUrl(null), null);
    assert.equal(bot.extractDestinationUrl({}), null);
    assert.equal(bot.extractDestinationUrl({ status: "failed", error: "solve timeout" }), null);
    assert.equal(bot.extractDestinationUrl({ destination_url: "not-a-url" }), null);
    assert.equal(bot.extractDestinationUrl("https://example.com"), null);
});

test("bot_discord.js contract - isLink4M provider URL detection", () => {
    // Valid Link4M hostnames
    assert.equal(bot.isLink4M("https://link4m.net/go/abc123"), true);
    assert.equal(bot.isLink4M("http://link4m.com/go/xyz"), true);
    assert.equal(bot.isLink4M("https://sub.link4m.org/go/item"), true);
    assert.equal(bot.isLink4M("https://link4m.co/go/test"), true);

    // Non-Link4M domains
    assert.equal(bot.isLink4M("https://gtraffic.io/123"), false);
    assert.equal(bot.isLink4M("https://layma.net/code"), false);
    assert.equal(bot.isLink4M("https://google.com"), false);
    assert.equal(bot.isLink4M(null), false);
    assert.equal(bot.isLink4M(""), false);
});

test("bot_discord.js contract - Provider Registry coverage", () => {
    const providers = bot.loadProviderRegistry();
    assert.ok(Array.isArray(providers), "Providers must return an array");
    assert.ok(providers.length >= 6, "Must define at least 6 primary provider configurations");

    const keys = providers.map(p => p.key);
    assert.ok(keys.includes("LINK4M"), "Must include LINK4M");
    assert.ok(keys.includes("OCTOLINK"), "Must include OCTOLINK");
    assert.ok(keys.includes("BBMKTS"), "Must include BBMKTS");
    assert.ok(keys.includes("GTRAFFIC"), "Must include GTRAFFIC");
    assert.ok(keys.includes("LAYMA"), "Must include LAYMA");
    assert.ok(keys.includes("TRAFFICVN"), "Must include TRAFFICVN");

    // Verify key provider host associations
    const bbmkts = providers.find(p => p.key === "BBMKTS");
    assert.ok(bbmkts.hosts.includes("bbmkts.com") || bbmkts.hosts.includes("yeumoney.com"), "BBMKTS hosts must include bbmkts.com or yeumoney.com");

    const octolink = providers.find(p => p.key === "OCTOLINK");
    assert.ok(octolink.hosts.includes("octolink.vip") || octolink.hosts.includes("link999.app"), "OCTOLINK hosts must include octolink.vip or link999.app");

    const gtraffic = providers.find(p => p.key === "GTRAFFIC");
    assert.ok(gtraffic.hosts.includes("gtraffic.io"), "GTRAFFIC hosts must include gtraffic.io");
});
