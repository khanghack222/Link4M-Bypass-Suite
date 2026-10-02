import os, re

target = "bot_discord.js"
with open(target, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False

# We want to replace from "// 2. Giao diện Console ANSI Realtime" to the end of executeBypassTask
# Let's inspect where it starts
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "// 2. Giao diện Console ANSI Realtime" in line:
        start_idx = i
    if start_idx != -1 and "client.once(\"ready\"" in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    replacement = """    // 2. Giao diện tiến trình bảo mật công nghệ & tinh gọn
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
            const m = line.match(/Countdown duration\\s*=\\s*(\\d+)s/);
            if (m) countdownSec = parseInt(m[1], 10);
            currentStep = 3;
            stepPercent = Math.max(stepPercent, 50);
            stepTitle = `Đang đồng bộ tiến trình bảo mật (${countdownSec || 45}s)...`;
            cleanText = `[*] Đang xử lý đếm ngược: ${countdownSec}s`;
        } else if (line.includes("Remaining:")) {
            const m = line.match(/Remaining:\\s*(\\d+)s/);
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
            `${currentStep === 1 ? "🌀" : currentStep > 1 ? "✨" : "▫️"} ╭──✦ \\`[01/04]\\` **Phân tích liên kết & máy chủ**`,
            `${currentStep === 2 ? "🌀" : currentStep > 2 ? "✨" : "▫️"} ├──✦ \\`[02/04]\\` **Tiếp nhận cổng bảo mật**`,
            `${currentStep === 3 ? "🌀" : currentStep > 3 ? "✨" : "▫️"} ├──✦ \\`[03/04]\\` **Xử lý tiến trình đếm ngược** ${countdownSec !== null ? `\\`(${countdownSec}s)\\`` : ""}`,
            `${currentStep === 4 ? "🌀" : currentStep > 4 ? "✨" : "▫️"} ╰──✦ \\`[04/04]\\` **Xác minh & mở khóa đích**`
        ].join("\\n");

        return new EmbedBuilder()
            .setColor(0x00F0FF)
            .setTitle("⚡ LINK4M ULTRA BYPASS")
            .setDescription(
                `${renderProgressBar(stepPercent, 14)}\\n\\n` +
                `**Tiến trình:**\\n${stageBadges}\\n\\n` +
                `\\`\\`\\`prolog\\n${statusLogs.join("\\n")}\\n\\`\\`\\``
            )
            .addFields(
                { name: "🔗 Link gốc", value: `\\`${targetUrl.length > 55 ? targetUrl.slice(0, 52) + '...' : targetUrl}\\``, inline: false },
                { name: "⏱ Thời gian chạy", value: `\\`${elapsed}s\\``, inline: true },
                { name: "🚀 Trạng thái", value: `\\`${stepTitle}\\``, inline: true }
            )
            .setFooter({ text: `Yêu cầu bởi ${userTag} • Link4M Ultra Suite`, iconURL: userAvatar })
            .setTimestamp();
    };

    // Vòng lặp cập nhật mượt mà (Heartbeat Ticker mỗi 1.8s)
    let isTaskRunning = true;
    const ticker = setInterval(async () => {
        if (!isTaskRunning) return;
        if (currentStep === 3 && stepPercent < 85) {
            stepPercent = Math.min(85, stepPercent + 2);
            if (countdownSec && countdownSec > 0) countdownSec = Math.max(1, countdownSec - 1);
        }
        try {
            await updateMessage({ embeds: [buildLiveEmbed()] });
        } catch (e) {}
    }, 1800);

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
                    { name: "🔗 Link gốc", value: `\\`\\`\\`${targetUrl}\\`\\`\\``, inline: false },
                    { name: "🎯 Link đích", value: `[👉 BẤM VÀO ĐÂY ĐỂ MỞ LINK NGAY](${result.destinationUrl})\\n\\`\\`\\`${result.destinationUrl}\\`\\`\\``, inline: false },
                    { name: "⏱ Thời gian", value: `\\`${result.duration} giây\\``, inline: true },
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
                    { name: "🔗 Link đầu vào", value: `\\`${targetUrl}\\``, inline: false },
                    { name: "⏱ Thời gian chạy", value: `\\`${result.duration}s\\``, inline: true },
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
                .setDescription(`Đã có sự cố ngoài ý muốn xảy ra: \\`${err.message}\\``)
                .setFooter({ text: `Yêu cầu bởi ${userTag}`, iconURL: userAvatar })
                .setTimestamp();
            await updateMessage({ embeds: [errEmbed], components: [] });
        } catch (e) {}
    }
}

// ==========================================
"""
    final_content = "".join(lines[:start_idx]) + replacement + "".join(lines[end_idx:])
    with open(target, "w", encoding="utf-8") as f:
        f.write(final_content)
    print("SUCCESS")
else:
    print(f"FAILED to locate boundaries: start={start_idx}, end={end_idx}")
