#!/usr/bin/env node
/**
 * ⚡ LINK4M & UNIVERSAL SHORTLINK DISCORD BOT (Node.js) ⚡
 * Powered by Discord.js v14 & Unified Autonomous Bypass Engine
 * 
 * Supports:
 * - Slash Commands: /bypass <url>
 * - Prefix Commands: !bypass <url>
 * - Real-time Embed Status & Live Progress
 * - Concurrency Queue Protection (Prevents RAM/CPU Spikes on Hosting)
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
    ButtonStyle 
} = require("discord.js");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT_DIR = path.resolve(__dirname);
const AUTO_BYPASS_SCRIPT = path.join(ROOT_DIR, "auto_bypass.py");
const DEST_FILE = path.join(ROOT_DIR, "destination_url.txt");
const FINAL_DEST_FILE = path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt");

const TOKEN = process.env.DISCORD_TOKEN || process.env.BOT_TOKEN || "";
const CLIENT_ID = process.env.CLIENT_ID || process.env.APPLICATION_ID || "1182983270556774420";
const MAX_CONCURRENT = parseInt(process.env.MAX_CONCURRENT || "2", 10);

if (!TOKEN) {
    console.error("[FATAL] Chưa cấu hình DISCORD_TOKEN trong biến môi trường hoặc file .env!");
    process.exit(1);
}

// Tìm đường dẫn thực thi Python
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

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ]
});

// Định nghĩa Slash Command
const commands = [
    new SlashCommandBuilder()
        .setName("bypass")
        .setDescription("Vượt link rút gọn Link4M, BBMKTS, GTraffic, LayMa tự động bằng AI")
        .addStringOption(option =>
            option.setName("url")
                .setDescription("Đường link rút gọn cần vượt")
                .setRequired(true)
        ),
    new SlashCommandBuilder()
        .setName("status")
        .setDescription("Xem trạng thái hoạt động của bot và hàng đợi hiện tại")
].map(cmd => cmd.toJSON());

// Hàng đợi Bypass để bảo vệ tài nguyên Server
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

function runBypassProcess(targetUrl, onLog) {
    return new Promise((resolve) => {
        const pythonBin = getPythonExecutable();
        const startTime = Date.now();
        let capturedUrl = null;

        // Xóa file kết quả cũ
        for (const p of [DEST_FILE, FINAL_DEST_FILE]) {
            try { if (fs.existsSync(p)) fs.unlinkSync(p); } catch (e) {}
        }

        const args = ["-u", "-X", "utf8", AUTO_BYPASS_SCRIPT, targetUrl, "--headless"];
        const proc = spawn(pythonBin, args, {
            cwd: ROOT_DIR,
            env: { ...process.env, PYTHONUNBUFFERED: "1" }
        });

        proc.stdout.on("data", (data) => {
            const lines = data.toString("utf-8").split(/\r?\n/);
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                if (trimmed.includes("FINAL DESTINATION URL:")) {
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
                console.error(`[PY_ERR] ${errStr.slice(0, 150)}`);
            }
        });

        proc.on("close", (code) => {
            const durationSec = Math.round((Date.now() - startTime) / 1000);
            let finalUrl = capturedUrl;
            if (!finalUrl) {
                for (const p of [FINAL_DEST_FILE, DEST_FILE]) {
                    if (fs.existsSync(p)) {
                        const content = fs.readFileSync(p, "utf-8").trim();
                        if (content.startsWith("http")) {
                            finalUrl = content;
                            break;
                        }
                    }
                }
            }
            resolve({
                success: !!(finalUrl && finalUrl.startsWith("http")),
                destinationUrl: finalUrl || null,
                duration: durationSec,
                code
            });
        });

        proc.on("error", (err) => {
            console.error("[SPAWN ERROR]", err);
            resolve({ success: false, error: err.message, duration: 0 });
        });
    });
}

async function executeBypassTask(task) {
    const { updateMessage, targetUrl, userTag } = task;
    let currentStatus = "Khởi chạy phiên duyệt ảo...";
    let lastEditTime = Date.now();

    const makeEmbed = (desc, color = 0x00E5FF, fields = []) => {
        return new EmbedBuilder()
            .setColor(color)
            .setTitle("⚡ LINK4M UNIVERSAL AUTO BYPASS")
            .setDescription(desc)
            .addFields(
                { name: "🔗 Link gốc", value: `\`${targetUrl.length > 60 ? targetUrl.slice(0, 57) + '...' : targetUrl}\``, inline: false },
                ...fields
            )
            .setFooter({ text: `Yêu cầu bởi ${userTag} • Engine v4.2 Autonomous`, iconURL: client.user.displayAvatarURL() })
            .setTimestamp();
    };

    const throttledUpdate = async (statusText) => {
        currentStatus = statusText;
        if (Date.now() - lastEditTime > 3000) {
            lastEditTime = Date.now();
            try {
                await updateMessage({
                    embeds: [makeEmbed(`⏳ **Tiến trình:** ${currentStatus}`, 0xFFA500)]
                });
            } catch (e) {}
        }
    };

    try {
        await updateMessage({
            embeds: [makeEmbed("⏳ **Đang xử lý trong hàng đợi...** Vui lòng đợi trong giây lát!", 0xFFA500)]
        });

        const result = await runBypassProcess(targetUrl, (logLine) => {
            if (logLine.includes("TARGET SPONSOR") || logLine.includes("Đang thử nghiệm trang")) {
                throttledUpdate("Đã phát hiện đối tác tài trợ, đang truy cập...");
            } else if (logLine.includes("Countdown duration")) {
                const m = logLine.match(/Countdown duration\s*=\s*(\d+)s/);
                throttledUpdate(`Đang đếm ngược sponsor (${m ? m[1] + 's' : 'Bước 1'})...`);
            } else if (logLine.includes("Remaining:")) {
                const m = logLine.match(/Remaining:\s*(\d+)s/);
                if (m && parseInt(m[1]) % 15 === 0) {
                    throttledUpdate(`Đang đếm ngược sponsor: còn ${m[1]}s...`);
                }
            } else if (logLine.includes("EXTRACTED SPONSOR CODE")) {
                throttledUpdate("Đã lấy mã tài trợ, đang giải reCAPTCHA...");
            } else if (logLine.includes("Solving reCAPTCHA") || logLine.includes("Audio challenge")) {
                throttledUpdate("Đang giải mã Google reCAPTCHA v2 bằng Whisper AI...");
            }
        });

        if (result.success && result.destinationUrl) {
            const successEmbed = new EmbedBuilder()
                .setColor(0x00FF88)
                .setTitle("🏆 VƯỢT LINK THÀNH CÔNG RỰC RỠ!")
                .setDescription(`Link đích đã được giải mã và mở khóa hoàn tất!`)
                .addFields(
                    { name: "🔗 Link gốc", value: `\`${targetUrl}\``, inline: false },
                    { name: "🎯 Link đích", value: `[👉 Bấm vào đây để mở link](${result.destinationUrl})\n\`\`\`${result.destinationUrl}\`\`\``, inline: false },
                    { name: "⏱ Thời gian hoàn thành", value: `\`${result.duration} giây\``, inline: true },
                    { name: "🛡️ Chế độ bảo mật", value: "`A05 / Cloud AI Bypass`", inline: true }
                )
                .setFooter({ text: `Hoàn tất cho ${userTag}`, iconURL: client.user.displayAvatarURL() })
                .setTimestamp();

            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder()
                    .setLabel("Mở Link Đích Ngay")
                    .setStyle(ButtonStyle.Link)
                    .setURL(result.destinationUrl)
            );

            await updateMessage({ embeds: [successEmbed], components: [row] });
        } else {
            const failEmbed = new EmbedBuilder()
                .setColor(0xFF3366)
                .setTitle("❌ VƯỢT LINK THẤT BẠI HOẶC HẾT HẠN")
                .setDescription("Không thể trích xuất được link đích. Có thể chiến dịch quảng cáo đã kết thúc hoặc link bị lỗi.")
                .addFields(
                    { name: "🔗 Link gốc", value: `\`${targetUrl}\``, inline: false },
                    { name: "⏱ Thời gian chạy", value: `\`${result.duration}s\``, inline: true }
                )
                .setFooter({ text: `Yêu cầu bởi ${userTag}`, iconURL: client.user.displayAvatarURL() })
                .setTimestamp();

            await updateMessage({ embeds: [failEmbed], components: [] });
        }
    } catch (err) {
        console.error("[TASK ERROR]", err);
        try {
            await updateMessage({
                embeds: [makeEmbed(`❌ **Đã xảy ra lỗi hệ thống:** ${err.message}`, 0xFF0000)],
                components: []
            });
        } catch (e) {}
    }
}

// Đăng ký Slash Command khi Bot Ready
client.once("ready", async () => {
    console.log(`\n======================================================`);
    console.log(`🤖 Discord Bot đã đăng nhập thành công: ${client.user.tag}`);
    console.log(`✦ Client ID: ${CLIENT_ID}`);
    console.log(`✦ Max Concurrent Jobs: ${MAX_CONCURRENT}`);
    console.log(`======================================================\n`);

    try {
        const rest = new REST({ version: "10" }).setToken(TOKEN);
        console.log("[REST] Đang đăng ký Global Slash Commands...");
        await rest.put(
            Routes.applicationCommands(CLIENT_ID),
            { body: commands }
        );
        console.log("[REST] Đã đăng ký Slash Commands (/bypass, /status) thành công!");
    } catch (err) {
        console.error("[REST ERROR] Không thể đăng ký Slash Commands:", err.message);
    }
});

// Xử lý Slash Command
client.on("interactionCreate", async (interaction) => {
    if (!interaction.isChatInputCommand()) return;

    if (interaction.commandName === "status") {
        const statusEmbed = new EmbedBuilder()
            .setColor(0x00E5FF)
            .setTitle("📊 Trạng Thái Hệ Thống Bot")
            .addFields(
                { name: "⚡ Tác vụ đang chạy", value: `\`${activeWorkers} / ${MAX_CONCURRENT}\``, inline: true },
                { name: "📥 Hàng đợi", value: `\`${queue.length} tác vụ\``, inline: true },
                { name: "🟢 Uptime", value: `\`${Math.round(process.uptime())}s\``, inline: true }
            )
            .setTimestamp();
        return interaction.reply({ embeds: [statusEmbed], ephemeral: true });
    }

    if (interaction.commandName === "bypass") {
        const rawUrl = interaction.options.getString("url")?.trim();
        if (!rawUrl || !rawUrl.startsWith("http")) {
            return interaction.reply({ content: "❌ Vui lòng nhập URL hợp lệ (bắt đầu bằng `http://` hoặc `https://`)!", ephemeral: true });
        }

        await interaction.deferReply();

        queue.push({
            targetUrl: rawUrl,
            userTag: interaction.user.tag,
            updateMessage: async (payload) => {
                await interaction.editReply(payload);
            }
        });
        processQueue();
    }
});

// Xử lý Prefix Command (!bypass <url>)
client.on("messageCreate", async (message) => {
    if (message.author.bot) return;

    const content = message.content.trim();
    if (content.startsWith("!bypass") || content.startsWith("!link4m")) {
        const parts = content.split(/\s+/);
        const rawUrl = parts[1]?.trim();

        if (!rawUrl || !rawUrl.startsWith("http")) {
            return message.reply("❌ Vui lòng nhập link theo cú pháp: `!bypass <đường_link>`");
        }

        const replyMsg = await message.reply("⚡ Đang tiếp nhận yêu cầu vượt link...");

        queue.push({
            targetUrl: rawUrl,
            userTag: message.author.tag,
            updateMessage: async (payload) => {
                await replyMsg.edit(payload);
            }
        });
        processQueue();
    }
});

// Keep-alive HTTP Server cho Render Web Service (Free Tier)
const http = require("http");
const PORT = process.env.PORT || 10000;
const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
        status: "online",
        bot: client.user ? client.user.tag : "connecting",
        uptime: Math.round(process.uptime()),
        queue: queue.length,
        activeWorkers
    }));
});

server.listen(PORT, () => {
    console.log(`[HTTP] Keep-alive Web Service listening on port ${PORT}`);
});

client.login(TOKEN);
