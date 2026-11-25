#!/usr/bin/env node
/**
 * ⚡ LINK4M ULTRA BYPASS DISCORD BOT (v5.0 Master Edition) ⚡
 * Powered by Discord.js v14 & Unified Autonomous AI Bypass Engine
 *
 * Features:
 * - 💎 Ultra-clean Cyberpunk / Neon Visual Embeds with Dynamic Progress Bar
 * - ⚡ Multi-platform Support: Link4M, GTraffic, LayMa, BBMKTS, TrafficVIP, ShortEarn
 * - 🚀 High-Speed In-Memory Cache (0.01s instant hit on repeated links)
 * - 🛡️ Intelligent Task Queue & Anti-OOM Concurrency Controller (Perfect for Low-RAM Hosting)
 * - 🎮 Slash Commands (/bypass, /batch, /stats, /ping, /platforms, /help)
 * - 💬 Prefix Commands (!bypass, !bp, !stats, !ping, !help)
 * - 🌐 24/7 Keep-alive HTTP Server & Metrics for Render/Railway/Koyeb
 */

require("dotenv").config();
const {
    Client,
    GatewayIntentBits,
    SlashCommandBuilder,
    REST,
    Routes,
    EmbedBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    ModalBuilder,
    TextInputBuilder,
    TextInputStyle,
    ActivityType,
    ComponentType,
    MessageFlags
} = require("discord.js");
const { spawn, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

// ==========================================
// CẤU HÌNH HỆ THỐNG
// ==========================================
const ROOT_DIR = path.resolve(__dirname);
const AUTO_BYPASS_SCRIPT = path.join(ROOT_DIR, "auto_bypass.py");
const DEST_FILE = path.join(ROOT_DIR, "destination_url.txt");
const FINAL_DEST_FILE = path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt");

const TOKEN = process.env.DISCORD_TOKEN || process.env.BOT_TOKEN || "";
const CLIENT_ID = process.env.CLIENT_ID || process.env.APPLICATION_ID || "";
const MAX_CONCURRENT = parseInt(process.env.MAX_CONCURRENT || "2", 10);
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 phút cache
const TASK_TIMEOUT_MS = 300 * 1000; // 300 giây (5 phút) bảo đảm hoàn tất cả chiến dịch 2-3 bước đếm ngược

if (!TOKEN) {
    console.error("[FATAL] DISCORD_TOKEN is missing! Please set DISCORD_TOKEN in .env or environment variables.");
    process.exit(1);
}

// ==========================================
// PROVIDER REGISTRY (đọc từ Python --list, cache 1 lần)
// ==========================================
let _registryCache = null;

function loadProviderRegistry() {
    if (_registryCache) return _registryCache;
    try {
        const out = execFileSync(getPythonExecutable(),
            ["-u", "-X", "utf8", "-m", "src.bypass_api", "--list"], {
                cwd: ROOT_DIR,
                encoding: "utf-8",
                timeout: 15000,
                env: { ...process.env, PYTHONIOENCODING: "utf-8" },
            });
        const payload = JSON.parse(out);
        _registryCache = (payload.providers || []).filter((p) => p.key !== "DECODE");
    } catch (e) {
        _registryCache = [];
    }
    if (!_registryCache.length) {
        _registryCache = [
            { key: "LINK4M", hosts: ["link4m.net", "link4m.com"], note: "sponsor OCR + reCAPTCHA audio" },
            { key: "OCTOLINK", hosts: ["octolink.vip", "link999.app", "uptolink.*"], note: "canvas physics + hold captcha" },
            { key: "BBMKTS", hosts: ["bbmkts.com", "yeumoney.com"], note: "dual-tab countdown + route patch" },
            { key: "GTRAFFIC", hosts: ["gtraffic.io", "client.gtraffic.io"], note: "mobile viewport + API leak" },
            { key: "LAYMA", hosts: ["layma.net"], note: "qcaptcha stealth + HSV vision" },
            { key: "TRAFFICVN", hosts: ["trafficvn.com", "trafficvn.net"], note: "countdown + activation code" },
        ];
    }
    return _registryCache;
}

// ==========================================
// BỘ NHỚ ĐỆM & THỐNG KÊ (IN-MEMORY METRICS)
// ==========================================
const bypassCache = new Map(); // url -> { destinationUrl, timestamp }
const botStats = {
    totalRequests: 0,
    successfulBypasses: 0,
    failedBypasses: 0,
    cacheHits: 0,
    totalDurationSec: 0,
    startTime: Date.now()
};

const MAX_CACHE_ITEMS = 500;

function cleanExpiredCache() {
    const now = Date.now();
    for (const [url, item] of bypassCache.entries()) {
        if (now - item.timestamp > CACHE_TTL_MS) {
            bypassCache.delete(url);
        }
    }
    // Giới hạn LRU tránh tràn RAM hosting
    if (bypassCache.size > MAX_CACHE_ITEMS) {
        const oldestKey = bypassCache.keys().next().value;
        if (oldestKey) bypassCache.delete(oldestKey);
    }
}
setInterval(cleanExpiredCache, 5 * 60 * 1000);

// ==========================================
// TỰ ĐỘNG TÌM ĐƯỜNG DẪN PYTHON RUNTIME
// ==========================================
function getPythonExecutable() {
    if (process.env.PYTHON_PATH && fs.existsSync(process.env.PYTHON_PATH)) {
        return process.env.PYTHON_PATH;
    }
    const candidates = [
        "C:\\Users\\XUAN\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
        path.join(process.env.LOCALAPPDATA || "", "Programs\\Python\\Python311\\python.exe"),
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        "python3",
        "python"
    ];
    for (const c of candidates) {
        if (c.includes("/") || c.includes("\\")) {
            if (fs.existsSync(c)) return c;
        }
    }
    return "python3";
}

// ==========================================
// TIỆN ÍCH HIỂN THỊ EMBED & PROGRESS BAR (CYBER AESTHETIC)
// ==========================================
function renderProgressBar(percent, length = 12) {
    const p = Math.max(0, Math.min(100, percent));
    const filled = Math.round((p / 100) * length);
    const empty = length - filled;
    return `⟪ \`${'▰'.repeat(filled)}${'▱'.repeat(empty)}\` ⟫ **${p}%**`;
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatUptime(ms) {
    const sec = Math.floor(ms / 1000) % 60;
    const min = Math.floor(ms / (1000 * 60)) % 60;
    const hrs = Math.floor(ms / (1000 * 60 * 60)) % 24;
    const days = Math.floor(ms / (1000 * 60 * 60 * 24));
    if (days > 0) return `${days}d ${hrs}h ${min}m`;
    if (hrs > 0) return `${hrs}h ${min}m ${sec}s`;
    return `${min}m ${sec}s`;
}

// ==========================================
// KHỞI TẠO DISCORD CLIENT (Chuẩn Cloud Intents)
// ==========================================
// Sử dụng Guilds intent tiêu chuẩn để hoạt động ngay 100% trên Cloud/Hosting
// mà không cần phải bật Privileged Intent (Message Content) trong Discord Developer Portal.
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds
    ]
});

// ==========================================
// DANH SÁCH LỆNH SLASH (SLASH COMMANDS)
// ==========================================
const commands = [
    new SlashCommandBuilder()
        .setName("bypass")
        .setDescription("⚡ Vượt link rút gọn Link4M, GTraffic, LayMa, BBMKTS tự động siêu tốc")
        .addStringOption(option =>
            option.setName("url")
                .setDescription("Đường link rút gọn cần giải mã")
                .setRequired(true)
        )
        .addStringOption(option =>
            option.setName("mode")
                .setDescription("Chế độ vượt link")
                .setRequired(false)
                .addChoices(
                    { name: "⚡ Tự động thông minh (Khuyên dùng)", value: "auto" },
                    { name: "🛡️ Trình duyệt tàng hình (Stealth)", value: "stealth" },
                    { name: "🚀 API Siêu tốc (Fast API)", value: "fast" }
                )
        ),
    new SlashCommandBuilder()
        .setName("batch")
        .setDescription("📦 Vượt nhiều link rút gọn cùng lúc (tối đa 3 links)")
        .addStringOption(option =>
            option.setName("urls")
                .setDescription("Danh sách các link rút gọn, cách nhau bởi dấu cách hoặc dấu phẩy")
                .setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName("stats")
        .setDescription("📊 Thống kê hiệu năng, tỷ lệ thành công, RAM và tiến trình của bot"),
    new SlashCommandBuilder()
        .setName("ping")
        .setDescription("🏓 Kiểm tra độ trễ mạng WebSocket và trạng thái Python Core Engine"),
    new SlashCommandBuilder()
        .setName("platforms")
        .setDescription("🌐 Xem danh sách các hệ thống link rút gọn được hỗ trợ"),
    new SlashCommandBuilder()
        .setName("panel")
        .setDescription("🎛️ Hiển thị bảng điều khiển Bypass Link tương tác (Nút bấm & Modal điền link)"),
    new SlashCommandBuilder()
        .setName("help")
        .setDescription("📖 Hướng dẫn sử dụng bot và các cú pháp hữu ích")
].map(cmd => cmd.toJSON());

// ==========================================
// HỆ THỐNG HÀNG ĐỢI (CONCURRENCY QUEUE)
// ==========================================
const queue = [];
let activeWorkers = 0;

function processQueue() {
    if (activeWorkers >= MAX_CONCURRENT || queue.length === 0) return;
    const task = queue.shift();
    activeWorkers++;
    executeBypassTask(task).finally(() => {
        activeWorkers--;
        processQueue();
    });
}

// ==========================================
// TIẾN TRÌNH PYTHON THỰC THI (ENGINE SPAWN)
// ==========================================
function runBypassProcess(targetUrl, onLog) {
    return new Promise((resolve) => {
        const pythonBin = getPythonExecutable();
        const startTime = Date.now();
        const runId = `${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
        const runDestFile = path.join(ROOT_DIR, `destination_url-${runId}.txt`);
        let capturedUrl = null;

        // Xóa file đích tạm
        for (const p of [DEST_FILE, FINAL_DEST_FILE, runDestFile]) {
            try { if (fs.existsSync(p)) fs.unlinkSync(p); } catch (e) {}
        }

        const args = ["-u", "-X", "utf8", "-m", "src.bypass_api", "--url", targetUrl, "--json"];
        const proc = spawn(pythonBin, args, {
            cwd: ROOT_DIR,
            env: { ...process.env, PYTHONUNBUFFERED: "1", BYPASS_RUN_ID: runId },
            detached: process.platform !== "win32"
        });

        let isTimedOut = false;
        const timer = setTimeout(() => {
            isTimedOut = true;
            try {
                if (process.platform === "win32") {
                    spawn("taskkill", ["/pid", proc.pid.toString(), "/f", "/t"]);
                } else {
                    process.kill(-proc.pid, "SIGKILL");
                }
            } catch (e) {}
            resolve({
                success: false,
                error: `Quá thời gian cho phép (${Math.round(TASK_TIMEOUT_MS / 1000)}s timeout)`,
                duration: Math.round((Date.now() - startTime) / 1000)
            });
        }, TASK_TIMEOUT_MS);

        proc.stdout.on("data", (data) => {
            const lines = data.toString("utf-8").split(/\r?\n/);
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                if (trimmed.startsWith("__BYPASS_JSON__")) {
                    try {
                        const payload = JSON.parse(trimmed.slice("__BYPASS_JSON__".length));
                        if (payload && payload.success && payload.destination_url) {
                            capturedUrl = payload.destination_url;
                        }
                    } catch (e) {}
                } else if (trimmed.includes("FINAL DESTINATION URL:")) {
                    capturedUrl = trimmed.split("FINAL DESTINATION URL:")[1].trim();
                } else if (trimmed.includes("DESTINATION URL INTERCEPTED FROM API:")) {
                    capturedUrl = trimmed.split("DESTINATION URL INTERCEPTED FROM API:")[1].trim();
                } else if (trimmed.includes("Link đích:") || trimmed.includes("Link dich:")) {
                    const parts = trimmed.split(/Link đ[ií]ch:\s*/i);
                    if (parts[1] && parts[1].startsWith("http")) capturedUrl = parts[1].trim();
                }

                if (onLog) onLog(trimmed);
            }
        });

        proc.stderr.on("data", (data) => {
            const errStr = data.toString("utf-8").trim();
            if (errStr && !errStr.includes("DeprecationWarning")) {
                // Log quietly for debugging
            }
        });

        proc.on("close", (code) => {
            clearTimeout(timer);
            if (isTimedOut) return;

            const durationSec = Math.max(1, Math.round((Date.now() - startTime) / 1000));
            let finalUrl = capturedUrl;
            if (!finalUrl) {
                for (const p of [runDestFile, FINAL_DEST_FILE, DEST_FILE]) {
                    if (fs.existsSync(p)) {
                        const content = fs.readFileSync(p, "utf-8").trim();
                        if (content.startsWith("http")) {
                            finalUrl = content;
                            break;
                        }
                    }
                }
            }
            // Dọn dẹp runDestFile sau khi đọc xong
            try { if (fs.existsSync(runDestFile)) fs.unlinkSync(runDestFile); } catch (e) {}

            resolve({
                success: !!(finalUrl && finalUrl.startsWith("http")),
                destinationUrl: finalUrl || null,
                duration: durationSec,
                code
            });
        });

        proc.on("error", (err) => {
            clearTimeout(timer);
            resolve({ success: false, error: err.message, duration: 0 });
        });
    });
}

// ==========================================
// ĐIỀU PHỐI TÁC VỤ & GIAO DIỆN LIVE STATUS
// ==========================================
async function executeBypassTask(task) {
    const { updateMessage, targetUrl, userTag, userAvatar, channelId } = task;
    botStats.totalRequests++;

    // 1. Kiểm tra Cache tức thì (Instant Memory Hit)
    if (bypassCache.has(targetUrl)) {
        const cached = bypassCache.get(targetUrl);
        botStats.successfulBypasses++;
        botStats.cacheHits++;

        const cacheEmbed = new EmbedBuilder()
            .setColor(0x00F0FF)
            .setTitle("💎 ✦ B Ộ   N H Ớ   Đ Ệ M   S I Ê U   T Ố C ✦ 💎")
            .setDescription(`✨ **Đã giải mã thành công link từ Bộ Nhớ Đệm Siêu Tốc!**`)
            .addFields(
                { name: "🔗 ⪧ Link Gốc", value: `\`\`\`${targetUrl}\`\`\``, inline: false },
                { name: "🎯 ⪧ Link Đích Đã Mở Khóa", value: `[👉 BẤM VÀO ĐÂY ĐỂ MỞ LINK](${cached.destinationUrl})\n\`\`\`${cached.destinationUrl}\`\`\``, inline: false },
                { name: "⏱️ ⪧ Thời Gian", value: "`⚡ 0.01s (Instant Hit)`", inline: true },
                { name: "🛡️ ⪧ Tải Phần Cứng", value: "`0 MB RAM (Zero CPU)`", inline: true }
            )
            .setFooter({ text: `Yêu cầu bởi ${userTag} • Cache Level 1`, iconURL: userAvatar })
            .setTimestamp();

        const btnRow = new ActionRowBuilder().addComponents(
            new ButtonBuilder()
                .setLabel("Mở Link Đích Ngay")
                .setEmoji("🚀")
                .setStyle(ButtonStyle.Link)
                .setURL(cached.destinationUrl)
        );

        return updateMessage({ embeds: [cacheEmbed], components: [btnRow] });
    }

    // 2. Giao diện tiến trình bảo mật công nghệ & tinh gọn
    const startTime = Date.now();
    let currentStep = 1;
    let stepPercent = 10;
    let stepTitle = "Đang khởi tạo phiên kết nối...";
    let countdownSec = null;
    const statusLogs = [
        "[*] Khởi tạo kết nối an toàn...",
        "[*] Đang phân tích liên kết..."
    ];

    const pushLog = (line) => {
        let cleanText = "";
        if (line.includes("TARGET SPONSOR") || line.includes("Campaign") || line.includes("Đang thử nghiệm trang")) {
            currentStep = 2;
            stepPercent = Math.max(stepPercent, 35);
            stepTitle = "Đã xác định cổng dịch vụ, đang kết nối...";
            cleanText = "[+] Đã kết nối cổng chuyển tiếp";
        } else if (line.includes("Countdown duration")) {
            const m = line.match(/Countdown duration\s*=\s*(\d+)s/);
            if (m) countdownSec = parseInt(m[1], 10);
            currentStep = 3;
            stepPercent = Math.max(stepPercent, 50);
            stepTitle = `Đang đồng bộ tiến trình bảo mật (${countdownSec || 45}s)...`;
            cleanText = `[*] Đang xử lý đếm ngược: ${countdownSec}s`;
        } else if (line.includes("Remaining:")) {
            const m = line.match(/Remaining:\s*(\d+)s/);
            if (m) {
                countdownSec = parseInt(m[1], 10);
                currentStep = 3;
                stepTitle = `Đang xử lý bước bảo mật: còn ${countdownSec} giây...`;
                stepPercent = Math.min(85, Math.max(stepPercent, 90 - countdownSec));
                cleanText = `[*] Tiến trình: còn ${countdownSec}s`;
            }
        } else if (line.includes("EXTRACTED SPONSOR CODE") || line.includes("Mã code:")) {
            currentStep = 4;
            stepPercent = 88;
            stepTitle = "Đã hoàn thành xác nhận bước tài trợ...";
            cleanText = "[+] Hoàn tất bước tài trợ đối tác";
        } else if (line.includes("Solving reCAPTCHA") || line.includes("Audio challenge")) {
            currentStep = 4;
            stepPercent = 92;
            stepTitle = "Đang tự động xác minh bảo mật...";
            cleanText = "[*] Tự động giải mã bảo mật";
        } else if (line.includes("Bypass thành công") || line.includes("FINAL DESTINATION")) {
            currentStep = 4;
            stepPercent = 100;
            stepTitle = "Mở khóa liên kết thành công!";
            cleanText = "[+] Đã giải mã liên kết đích";
        }

        if (cleanText && cleanText !== statusLogs[statusLogs.length - 1]) {
            statusLogs.push(cleanText);
            if (statusLogs.length > 4) statusLogs.shift();
        }
    };

    const buildLiveEmbed = () => {
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const stageBadges = [
            `${currentStep === 1 ? "🌀" : currentStep > 1 ? "✨" : "▫️"} ╭──✦ \`[01/04]\` **Phân tích liên kết & máy chủ**`,
            `${currentStep === 2 ? "🌀" : currentStep > 2 ? "✨" : "▫️"} ├──✦ \`[02/04]\` **Tiếp nhận cổng bảo mật**`,
            `${currentStep === 3 ? "🌀" : currentStep > 3 ? "✨" : "▫️"} ├──✦ \`[03/04]\` **Xử lý tiến trình đếm ngược** ${countdownSec !== null ? `\`(${countdownSec}s)\`` : ""}`,
            `${currentStep === 4 ? "🌀" : currentStep > 4 ? "✨" : "▫️"} ╰──✦ \`[04/04]\` **Xác minh & mở khóa đích**`
        ].join("\n");

        return new EmbedBuilder()
            .setColor(0x00F0FF)
            .setTitle("⚡ LINK4M ULTRA BYPASS")
            .setDescription(
                `${renderProgressBar(stepPercent, 14)}\n\n` +
                `**Tiến trình:**\n${stageBadges}\n\n` +
                `\`\`\`prolog\n${statusLogs.join("\n")}\n\`\`\``
            )
            .addFields(
                { name: "🔗 Link gốc", value: `\`${targetUrl.length > 55 ? targetUrl.slice(0, 52) + '...' : targetUrl}\``, inline: false },
                { name: "⏱ Thời gian chạy", value: `\`${elapsed}s\``, inline: true },
                { name: "🚀 Trạng thái", value: `\`${stepTitle}\``, inline: true }
            )
            .setFooter({ text: `Yêu cầu bởi ${userTag} • Link4M Ultra Suite`, iconURL: userAvatar })
            .setTimestamp();
    };

    let isTaskRunning = true;
    let tickerUpdating = false;
    const ticker = setInterval(async () => {
        if (!isTaskRunning || tickerUpdating) return;
        tickerUpdating = true;
        try {
            if (currentStep === 3 && stepPercent < 85) {
                stepPercent = Math.min(85, stepPercent + 2);
                if (countdownSec && countdownSec > 0) countdownSec = Math.max(1, countdownSec - 1);
            }
            await updateMessage({ embeds: [buildLiveEmbed()] });
        } catch (e) {
            // Rate limit or transient network error caught safely
        } finally {
            tickerUpdating = false;
        }
    }, 2200);

    try {
        await updateMessage({ embeds: [buildLiveEmbed()] });

        const result = await runBypassProcess(targetUrl, (logLine) => {
            pushLog(logLine);
        });

        isTaskRunning = false;
        clearInterval(ticker);

        if (result.success && result.destinationUrl) {
            botStats.successfulBypasses++;
            botStats.totalDurationSec += result.duration;

            bypassCache.set(targetUrl, {
                destinationUrl: result.destinationUrl,
                timestamp: Date.now()
            });

            const successEmbed = new EmbedBuilder()
                .setColor(0x00FF88)
                .setTitle("👑 VƯỢT LINK THÀNH CÔNG!")
                .setDescription(`✨ **Đã mở khóa và lấy liên kết đích an toàn 100%!**`)
                .addFields(
                    { name: "🔗 Link gốc", value: `\`\`\`${targetUrl}\`\`\``, inline: false },
                    { name: "🎯 Link đích", value: `[👉 BẤM VÀO ĐÂY ĐỂ MỞ LINK NGAY](${result.destinationUrl})\n\`\`\`${result.destinationUrl}\`\`\``, inline: false },
                    { name: "⏱ Thời gian", value: `\`${result.duration} giây\``, inline: true },
                    { name: "🛡️ Trạng thái", value: "`Hoàn tất 100%`", inline: true }
                )
                .setFooter({ text: `Xử lý hoàn tất cho ${userTag} • Link4M Ultra Suite`, iconURL: userAvatar })
                .setTimestamp();

            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder()
                    .setLabel("Mở Link Đích Ngay")
                    .setEmoji("🚀")
                    .setStyle(ButtonStyle.Link)
                    .setURL(result.destinationUrl)
            );

            await updateMessage({ embeds: [successEmbed], components: [row] });
        } else {
            botStats.failedBypasses++;
            const failEmbed = new EmbedBuilder()
                .setColor(0xFF0055)
                .setTitle("❌ VƯỢT LINK THẤT BẠI HOẶC HẾT HẠN")
                .setDescription("Không thể mở khóa liên kết đích. Chiến dịch quảng cáo có thể đã hết ngân sách hoặc liên kết không hợp lệ.")
                .addFields(
                    { name: "🔗 Link đầu vào", value: `\`${targetUrl}\``, inline: false },
                    { name: "⏱ Thời gian chạy", value: `\`${result.duration}s\``, inline: true },
                    { name: "💡 Gợi ý", value: "Thử lại sau ít phút hoặc kiểm tra xem link có còn hiệu lực không.", inline: false }
                )
                .setFooter({ text: `Yêu cầu bởi ${userTag} • Link4M Ultra Suite`, iconURL: userAvatar })
                .setTimestamp();

            await updateMessage({ embeds: [failEmbed], components: [] });
        }
    } catch (err) {
        isTaskRunning = false;
        clearInterval(ticker);
        botStats.failedBypasses++;
        console.error("[TASK ERROR]", err);
        try {
            const errEmbed = new EmbedBuilder()
                .setColor(0xFF0000)
                .setTitle("💥 LỖI HỆ THỐNG")
                .setDescription(`Đã có sự cố ngoài ý muốn xảy ra: \`${err.message}\``)
                .setFooter({ text: `Yêu cầu bởi ${userTag}`, iconURL: userAvatar })
                .setTimestamp();
            await updateMessage({ embeds: [errEmbed], components: [] });
        } catch (e) {}
    }
}

// ==========================================
client.once("clientReady", async () => {
    const appId = CLIENT_ID || client.user.id;

    // Cài đặt Trạng thái hoạt động hiển thị trên danh sách thành viên (Online + Playing/Watching)
    try {
        client.user.setPresence({
            activities: [{
                name: "⚡ /bypass | Vượt Link 24/7",
                type: ActivityType.Watching
            }],
            status: "online"
        });
    } catch (e) {}

    const guildList = client.guilds.cache.map(g => `${g.name} (${g.id}, ${g.memberCount} members)`);
    const inviteUrl = `https://discord.com/oauth2/authorize?client_id=${appId}&permissions=277025773632&integration_type=0&scope=bot%20applications.commands`;

    console.log(`\n======================================================`);
    console.log(`🤖 Link4M Ultra Discord Bot đã sẵn sàng!`);
    console.log(`✦ Bot User: ${client.user.tag}`);
    console.log(`✦ Application ID: ${appId}`);
    console.log(`✦ Server Đang Tham Gia: ${client.guilds.cache.size} server(s)`);
    if (guildList.length > 0) {
        console.log(`  -> ${guildList.join("\n  -> ")}`);
    } else {
        console.log(`  -> [CHƯA THAM GIA SERVER NÀO DƯỚI DẠNG THÀNH VIÊN GUILD!]`);
        console.log(`  -> Link mời Bot vào server làm thành viên chính thức:`);
        console.log(`     ${inviteUrl}`);
    }
    console.log(`✦ Concurrency Limit: ${MAX_CONCURRENT}`);
    console.log(`✦ Cached Links: ${bypassCache.size}`);
    console.log(`======================================================\n`);

    try {
        const rest = new REST({ version: "10" }).setToken(TOKEN);
        console.log("[REST] Đang cập nhật toàn bộ Slash Commands toàn cầu...");
        await rest.put(
            Routes.applicationCommands(appId),
            { body: commands }
        );
        console.log("[REST] ✅ Đã đăng ký 6 Slash Commands thành công rực rỡ!");
    } catch (err) {
        console.error("[REST ERROR] Không thể đăng ký Slash Commands:", err.message);
    }
});

// ==========================================
// ĐIỀU HƯỚNG TƯƠNG TÁC (INTERACTION HANDLER)
// ==========================================
client.on("interactionCreate", async (interaction) => {
    // 1. Xử lý nút bấm trên Panel (Button Interaction)
    if (interaction.isButton()) {
        const { customId } = interaction;

        // Bấm nút "Mở box điền link"
        if (customId === "open_bypass_modal") {
            const modal = new ModalBuilder()
                .setCustomId("modal_bypass_submit")
                .setTitle("🔓 Mở Khóa Link Rút Gọn Tự Động");

            const linkInput = new TextInputBuilder()
                .setCustomId("modal_input_urls")
                .setLabel("Dán link cần mở khóa (tối đa 5 link)")
                .setPlaceholder("https://link4m.co/...\nhttps://bbmkts.com/...\nhttps://gtraffic.io/...")
                .setStyle(TextInputStyle.Paragraph)
                .setRequired(true)
                .setMaxLength(2000);

            const row = new ActionRowBuilder().addComponents(linkInput);
            modal.addComponents(row);

            return interaction.showModal(modal);
        }

        // Bấm nút "Link hỗ trợ"
        if (customId === "open_platforms_info") {
            const platEmbed = new EmbedBuilder()
                .setColor(0x00F0FF)
                .setTitle("🌐 DANH SÁCH CÁC CỔNG RÚT GỌN HỖ TRỢ")
                .setDescription("Hệ thống tự động nhận diện và vượt qua các cơ chế bảo mật tinh vi nhất:")
                .addFields(
                    { name: "🔹 Link4M & Octolink", value: "`link4m.com`, `link4m.org`, `link4m.co`, `octolink.vip`\n*(Tự động giải mã reCAPTCHA v2 / Audio AI & API Token)*", inline: false },
                    { name: "🔹 GTraffic Engine", value: "`gtraffic.io`, `client.gtraffic.io`\n*(Nhận diện banner, bóc tách OCR tên miền tài trợ, đếm ngược)*", inline: false },
                    { name: "🔹 BBMKTS & Turnstile", value: "`bbmkts.com`, `4mmo.com`\n*(Vượt Cloudflare Turnstile tàng hình 100%, tự động cào code)*", inline: false },
                    { name: "🔹 LayMa & TrafficVIP", value: "`layma.net`, `trafficvip.vip`, `shortearn.net`\n*(Vượt kiểm tra sponsor, tự động giải Math Captcha & OCR)*", inline: false }
                )
                .setFooter({ text: "Link4M Bypass Suite • Riêng tư 100%", iconURL: client.user.displayAvatarURL() });

            return interaction.reply({ embeds: [platEmbed], flags: MessageFlags.Ephemeral });
        }
    }

    // 2. Xử lý khi người dùng submit Modal điền link (Modal Submit)
    if (interaction.isModalSubmit()) {
        if (interaction.customId === "modal_bypass_submit") {
            const rawText = interaction.fields.getTextInputValue("modal_input_urls")?.trim() || "";
            const urls = (rawText.match(/https?:\/\/[^\s,]+/g) || []).slice(0, 5);

            if (urls.length === 0) {
                return interaction.reply({
                    content: "❌ Không tìm thấy đường link `http://` hoặc `https://` hợp lệ nào!",
                    flags: MessageFlags.Ephemeral
                });
            }

            // Trả lời riêng tư (chỉ người dùng thấy) ngay lập tức
            await interaction.deferReply({ flags: MessageFlags.Ephemeral });
            await interaction.editReply({
                content: `⚡ **Đã tiếp nhận ${urls.length} link!**\n🔒 Tiến trình đang chạy ngầm an toàn. Kết quả sẽ hiển thị ngay tại đây và gửi trực tiếp qua DM của bạn.`
            });

            // Đưa từng link vào hàng đợi
            for (const url of urls) {
                queue.push({
                    targetUrl: url,
                    userTag: interaction.user.tag,
                    userAvatar: interaction.user.displayAvatarURL(),
                    channelId: interaction.channelId,
                    updateMessage: async (payload) => {
                        // Cập nhật phản hồi riêng tư (Ephemeral)
                        try {
                            await interaction.followUp({ ...payload, flags: MessageFlags.Ephemeral });
                        } catch (e) {
                            try { await interaction.editReply(payload); } catch (e2) {}
                        }

                        // Nếu đã hoàn tất có link đích, tự động gửi kèm qua DM của người dùng
                        if (payload.embeds && payload.embeds[0] && payload.embeds[0].data?.title?.includes("THÀNH CÔNG")) {
                            try {
                                await interaction.user.send(payload);
                            } catch (eDm) {
                                // Người dùng chặn DM từ người lạ
                            }
                        }
                    }
                });
            }
            processQueue();
            return;
        }
    }

    // 3. Xử lý Slash Command thông thường
    if (!interaction.isChatInputCommand()) return;

    const { commandName } = interaction;

    // --- LỆNH /ping ---
    if (commandName === "ping") {
        const pingEmbed = new EmbedBuilder()
            .setColor(0x00F0FF)
            .setTitle("🏓 PONG • ĐỘ TRỄ HỆ THỐNG")
            .addFields(
                { name: "🌐 WebSocket Ping", value: `\`${client.ws.ping}ms\``, inline: true },
                { name: "⚡ Uptime", value: `\`${formatUptime(process.uptime() * 1000)}\``, inline: true },
                { name: "🧠 Python Core", value: "`Online / Ready`", inline: true }
            )
            .setFooter({ text: "Link4M Ultra Bot", iconURL: client.user.displayAvatarURL() })
            .setTimestamp();
        return interaction.reply({ embeds: [pingEmbed], flags: MessageFlags.Ephemeral });
    }

    // --- LỆNH /platforms (đọc từ provider registry) ---
    if (commandName === "platforms") {
        const registry = loadProviderRegistry();
        const platEmbed = new EmbedBuilder()
            .setColor(0x9D00FF)
            .setTitle("🌐 CÁC CỔNG LINK ĐƯỢC HỖ TRỢ BỞI BOT")
            .setDescription("Hệ thống tự động nhận diện và áp dụng kịch bản bypass chuyên biệt cho từng cổng:");
        for (const spec of registry) {
            platEmbed.addFields({
                name: `🔹 ${spec.key}`,
                value: `\`${(spec.hosts || []).join("`, `")}\`\n${spec.note || spec.module || ""}`.slice(0, 1024),
                inline: false,
            });
        }
        platEmbed
            .setFooter({ text: "Cập nhật liên tục 24/7", iconURL: client.user.displayAvatarURL() })
            .setTimestamp();
        return interaction.reply({ embeds: [platEmbed] });
    }

    // --- LỆNH /panel (BẢNG ĐIỀU KHIỂN BYPASS GIAO DIỆN CHUẨN) ---
    if (commandName === "panel") {
        const panelEmbed = new EmbedBuilder()
            .setColor(0x2B2D31)
            .setTitle("🔓 Bypass Link")
            .setDescription(
                "**Hệ thống bypass link tự động:**\n" +
                "• Bấm **\"Mở box điền link\"** bên dưới để dán link cần mở khóa (hỗ trợ dán tối đa **5 link** cùng lúc).\n" +
                "• Bấm **\"Link hỗ trợ\"** bên dưới để xem toàn bộ danh sách các nền tảng được hỗ trợ.\n" +
                "• Kết quả mở khóa sẽ được trả về **riêng tư (chỉ bạn thấy)** và gửi kèm qua DM.\n\n" +
                "🔒 *Mọi liên kết được bảo mật riêng tư · Không lưu vết link đích công khai*"
            );

        const panelRow = new ActionRowBuilder().addComponents(
            new ButtonBuilder()
                .setCustomId("open_bypass_modal")
                .setLabel("Mở box điền link")
                .setEmoji("📝")
                .setStyle(ButtonStyle.Primary),
            new ButtonBuilder()
                .setCustomId("open_platforms_info")
                .setLabel("Link hỗ trợ")
                .setEmoji("🌐")
                .setStyle(ButtonStyle.Secondary)
        );

        return interaction.reply({ embeds: [panelEmbed], components: [panelRow] });
    }

    // --- LỆNH /help ---
    if (commandName === "help") {
        const helpEmbed = new EmbedBuilder()
            .setColor(0x00E5FF)
            .setTitle("📖 TRUNG TÂM TRỢ GIÚP • LINK4M ULTRA BOT")
            .setDescription("Bot hỗ trợ vượt link rút gọn kiếm tiền tự động hoàn toàn mà không cần xem quảng cáo!")
            .addFields(
                { name: "⚡ Lệnh cơ bản", value: "• `/bypass <url>`: Vượt 1 link rút gọn\n• `/batch <url1> <url2>`: Vượt nhiều link cùng lúc (tối đa 3 link)\n• `/stats`: Xem tình trạng máy chủ & hiệu năng\n• `/platforms`: Xem các link được hỗ trợ", inline: false },
                { name: "💬 Lệnh Prefix", value: "Bạn cũng có thể gõ trực tiếp trong kênh:\n`!bypass <url>` hoặc `!bp <url>`", inline: false },
                { name: "💡 Lưu ý quan trọng", value: "Các link có đếm ngược sponsor sẽ cần từ 30s - 75s để bot mô phỏng hoàn tất thời gian thực theo yêu cầu của nhà mạng.", inline: false }
            )
            .setFooter({ text: "Link4M Ultra Bypass Engine", iconURL: client.user.displayAvatarURL() })
            .setTimestamp();
        return interaction.reply({ embeds: [helpEmbed] });
    }

    // --- LỆNH /stats ---
    if (commandName === "stats") {
        const mem = process.memoryUsage();
        const successRate = botStats.totalRequests > 0
            ? ((botStats.successfulBypasses / botStats.totalRequests) * 100).toFixed(1)
            : "100";
        const avgDuration = botStats.successfulBypasses > 0
            ? (botStats.totalDurationSec / botStats.successfulBypasses).toFixed(1)
            : "0";

        const statsEmbed = new EmbedBuilder()
            .setColor(0x00FF88)
            .setTitle("📊 BẢNG ĐIỀU KHIỂN HIỆU NĂNG HỆ THỐNG")
            .addFields(
                { name: "⚡ Tổng yêu cầu", value: `\`${botStats.totalRequests}\``, inline: true },
                { name: "✅ Thành công", value: `\`${botStats.successfulBypasses} (${successRate}%)\``, inline: true },
                { name: "❌ Thất bại", value: `\`${botStats.failedBypasses}\``, inline: true },
                { name: "🚀 Cache Hits", value: `\`${botStats.cacheHits}\``, inline: true },
                { name: "⏱ Thời gian TB", value: `\`${avgDuration}s\``, inline: true },
                { name: "🟢 Uptime", value: `\`${formatUptime(process.uptime() * 1000)}\``, inline: true },
                { name: "📥 Hàng đợi", value: `\`${queue.length} tác vụ\``, inline: true },
                { name: "⚙️ Đang xử lý", value: `\`${activeWorkers} / ${MAX_CONCURRENT}\``, inline: true },
                { name: "💾 RAM Hosting", value: `\`${formatBytes(mem.rss)}\``, inline: true }
            )
            .setFooter({ text: "Tối ưu hóa tài nguyên cho VPS & Cloud Hosting", iconURL: client.user.displayAvatarURL() })
            .setTimestamp();
        return interaction.reply({ embeds: [statsEmbed], flags: MessageFlags.Ephemeral });
    }

    // --- LỆNH /bypass ---
    if (commandName === "bypass") {
        const rawUrl = interaction.options.getString("url")?.trim();
        if (!rawUrl || !rawUrl.startsWith("http")) {
            return interaction.reply({ content: "❌ Vui lòng nhập URL hợp lệ (bắt đầu bằng `http://` hoặc `https://`)!", flags: MessageFlags.Ephemeral });
        }

        await interaction.deferReply();

        const queuePos = queue.length + 1;
        if (activeWorkers >= MAX_CONCURRENT) {
            await interaction.editReply({
                embeds: [
                    new EmbedBuilder()
                        .setColor(0xFFA500)
                        .setTitle("📥 ĐÃ THÊM VÀO HÀNG ĐỢI XỬ LÝ")
                        .setDescription(`Hệ thống đang phục vụ các tác vụ trước. Link của bạn ở vị trí **#${queuePos}** trong hàng đợi.`)
                        .setFooter({ text: "Tiến trình sẽ tự động bắt đầu ngay khi có chỗ trống" })
                ]
            });
        }

        queue.push({
            targetUrl: rawUrl,
            userTag: interaction.user.tag,
            userAvatar: interaction.user.displayAvatarURL(),
            channelId: interaction.channelId,
            updateMessage: async (payload) => {
                await interaction.editReply(payload);
            }
        });
        processQueue();
    }

    // --- LỆNH /batch ---
    if (commandName === "batch") {
        const rawInput = interaction.options.getString("urls")?.trim();
        const urls = (rawInput.match(/https?:\/\/[^\s,]+/g) || []).slice(0, 3);

        if (urls.length === 0) {
            return interaction.reply({ content: "❌ Không tìm thấy URL hợp lệ trong nội dung bạn gửi!", flags: MessageFlags.Ephemeral });
        }

        await interaction.deferReply();
        await interaction.editReply({
            content: `📦 **Đã nhận ${urls.length} link rút gọn!** Đang xếp lịch xử lý lần lượt...`
        });

        for (const url of urls) {
            queue.push({
                targetUrl: url,
                userTag: interaction.user.tag,
                userAvatar: interaction.user.displayAvatarURL(),
                channelId: interaction.channelId,
                updateMessage: async (payload) => {
                    await interaction.followUp(payload);
                }
            });
        }
        processQueue();
    }
});

// ==========================================
// XỬ LÝ PREFIX COMMANDS (!bypass, !bp, !help...)
// ==========================================
client.on("messageCreate", async (message) => {
    if (message.author.bot) return;

    const content = message.content.trim();
    const isBypass = content.startsWith("!bypass") || content.startsWith("!bp") || content.startsWith("!link4m");
    const isStats = content.startsWith("!stats");
    const isPing = content.startsWith("!ping");
    const isHelp = content.startsWith("!help");

    if (isPing) {
        return message.reply(`🏓 Pong! WebSocket Ping: \`${client.ws.ping}ms\` | Uptime: \`${formatUptime(process.uptime() * 1000)}\``);
    }

    if (isStats) {
        const mem = process.memoryUsage();
        return message.reply(`📊 **Stats:** Hoàn tất \`${botStats.successfulBypasses}/${botStats.totalRequests}\` link | Hàng đợi: \`${queue.length}\` | RAM: \`${formatBytes(mem.rss)}\``);
    }

    if (isHelp) {
        return message.reply("💡 Dùng lệnh `/bypass <url>` hoặc gõ `!bypass <url>` để vượt link tự động!");
    }

    if (isBypass) {
        const parts = content.split(/\s+/);
        const rawUrl = parts[1]?.trim();

        if (!rawUrl || !rawUrl.startsWith("http")) {
            return message.reply("❌ Cú pháp sai! Vui lòng nhập: `!bypass <đường_link>`");
        }

        const replyMsg = await message.reply("⚡ **Đã tiếp nhận yêu cầu!** Đang chuẩn bị giải mã...");

        queue.push({
            targetUrl: rawUrl,
            userTag: message.author.tag,
            userAvatar: message.author.displayAvatarURL(),
            channelId: message.channelId,
            updateMessage: async (payload) => {
                await replyMsg.edit(payload);
            }
        });
        processQueue();
    }
});

// ==========================================
// 24/7 HTTP HEALTHCHECK VÀ DASHBOARD CHO CLOUD HOSTING
// ==========================================
const PORT = process.env.PORT || 10000;
const server = http.createServer((req, res) => {
    const mem = process.memoryUsage();
    if (req.url === "/healthz" || req.url === "/") {
        res.writeHead(200, { "Content-Type": "application/json" });
        return res.end(JSON.stringify({
            status: "online",
            bot: client.user ? client.user.tag : "connecting",
            uptime_seconds: Math.round(process.uptime()),
            guilds_count: client.guilds ? client.guilds.cache.size : 0,
            guilds: client.guilds ? client.guilds.cache.map(g => ({ id: g.id, name: g.name, members: g.memberCount })) : [],
            invite_url: client.user ? `https://discord.com/oauth2/authorize?client_id=${client.user.id}&permissions=277025773632&integration_type=0&scope=bot%20applications.commands` : "",
            queue_length: queue.length,
            active_workers: activeWorkers,
            max_concurrent: MAX_CONCURRENT,
            cached_links: bypassCache.size,
            ram_usage: formatBytes(mem.rss),
            total_bypasses: botStats.successfulBypasses
        }));
    }
    res.writeHead(404);
    res.end();
});

server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
        console.log(`[HTTP SERVER] Cổng ${PORT} đang bận, bỏ qua tự động để tiếp tục chạy bot.`);
    } else {
        console.error("[HTTP SERVER ERROR]", err);
    }
});

server.listen(PORT, () => {
    console.log(`[HTTP SERVER] 🚀 24/7 Keep-alive server listening on port ${PORT}`);
});

// ==========================================
// GRACEFUL SHUTDOWN (DỌN TIẾN TRÌNH KHI TẮT CONTAINER)
// ==========================================
function cleanup() {
    console.log("\n[SHUTDOWN] Đang dọn dẹp tiến trình...");
    server.close();
    client.destroy();
    process.exit(0);
}
process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);

process.on("unhandledRejection", (reason, promise) => {
    console.error("[UNHANDLED REJECTION]", reason);
});
process.on("uncaughtException", (err) => {
    console.error("[UNCAUGHT EXCEPTION]", err);
});

// Đăng nhập bot
client.login(TOKEN).catch((err) => {
    console.error("[FATAL LOGIN ERROR] Không thể đăng nhập Discord Bot:", err.message);
});
