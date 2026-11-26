#!/usr/bin/env bash
# Cập nhật engine-rs từ GitHub — không cần clone, không đè file bạn đã sửa.
#
# So sánh 3 chiều: file local | manifest của bản đã cài | bản mới trên GitHub.
#   local == bản mới        -> bỏ qua
#   local == manifest       -> bạn chưa sửa, ghi đè bằng bản mới (có backup)
#   local != manifest       -> bạn đã sửa, GIỮ NGUYÊN, bản mới đưa vào
#                              _local/update-conflicts/<thời-gian>/
#
# Chỉ quản lý engine-rs/. Không chạm data/, models/, target/, legacy/, src/,
# service/, .env, proxies.txt. Không tự xoá file bạn tạo ngoài manifest.
#
#   ./scripts/update-engine.sh              # xem trước (dry-run)
#   ./scripts/update-engine.sh --apply      # áp dụng + build release
#   ./scripts/update-engine.sh --check      # exit 10 nếu có bản mới (cron)
#   ./scripts/update-engine.sh --apply -y --restart --no-build

set -euo pipefail

SLUG="${L4M_REPO_SLUG:-khanghack222/Link4M-Bypass-Suite}"
BRANCH="${L4M_BRANCH:-main}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.l4m-version"
MANIFEST="$ROOT/.l4m-engine-manifest"
BACKUP_ROOT="$ROOT/_local/update-backup"
CONFLICT_ROOT="$ROOT/_local/update-conflicts"

APPLY=0
ASSUME_YES=0
BUILD=1
RESTART=0
CHECK=0

usage() {
    sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1 ;;
        --yes|-y) ASSUME_YES=1 ;;
        --no-build) BUILD=0 ;;
        --restart) RESTART=1 ;;
        --check) CHECK=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Tham số lạ: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

die() { echo "LỖI: $*" >&2; exit 1; }

command -v tar >/dev/null 2>&1 || die "thiếu tar"
command -v awk >/dev/null 2>&1 || die "thiếu awk"
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    die "cần curl hoặc wget"
fi

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

count_lines() {
    if [ -f "$1" ]; then wc -l < "$1" | tr -d ' '; else echo 0; fi
}

# --- bản đang cài và bản trên GitHub -------------------------------------

current_sha="$(cat "$STATE" 2>/dev/null | tr -d '[:space:]' || true)"

remote_sha=""
if command -v git >/dev/null 2>&1; then
    remote_sha="$(git ls-remote "https://github.com/$SLUG.git" "refs/heads/$BRANCH" 2>/dev/null | awk 'NR==1 {print $1}')" || true
fi
if [ -z "$remote_sha" ]; then
    remote_sha="$(
        curl -fsSL --connect-timeout 15 \
            "https://api.github.com/repos/$SLUG/commits/$BRANCH" 2>/dev/null \
        | sed -n 's/^[[:space:]]*"sha":[[:space:]]*"\([0-9a-f]\{40\}\)".*/\1/p' \
        | head -1
    )" || true
fi
[ -n "$remote_sha" ] || die "không đọc được sha mới từ GitHub (kiểm tra mạng/proxy)"

if [ "$CHECK" -eq 1 ]; then
    if [ "$current_sha" = "$remote_sha" ]; then
        echo "engine-rs đã ở bản mới nhất: ${remote_sha:0:12}"
        exit 0
    fi
    echo "có bản mới: ${current_sha:0:12} -> ${remote_sha:0:12}"
    exit 10
fi

if [ "$current_sha" = "$remote_sha" ] && [ "$APPLY" -eq 0 ]; then
    echo "engine-rs đã ở bản mới nhất: ${remote_sha:0:12}"
    exit 0
fi

# --- tải bản mới, chỉ lấy engine-rs/ -------------------------------------

TMP="$(mktemp -d "${TMPDIR:-/tmp}/l4m-update.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

ARCHIVE="$TMP/src.tar.gz"
URL="https://codeload.github.com/$SLUG/tar.gz/$remote_sha"
echo "Tải $SLUG@${remote_sha:0:12} ..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --connect-timeout 15 -o "$ARCHIVE" "$URL" \
        || die "tải archive thất bại"
else
    wget -q -O "$ARCHIVE" "$URL" || die "tải archive thất bại"
fi

mkdir -p "$TMP/new"
tar -xzf "$ARCHIVE" -C "$TMP/new" --strip-components=1
NEW="$TMP/new"
[ -d "$NEW/engine-rs" ] || die "archive không có engine-rs/"

is_excluded() {
    case "$1" in
        engine-rs/data/*|engine-rs/models/*|engine-rs/target/*) return 0 ;;
    esac
    return 1
}

# --- lập kế hoạch 3 chiều -------------------------------------------------

: > "$TMP/add.list"
: > "$TMP/update.list"
: > "$TMP/same.list"
: > "$TMP/conflict.list"
: > "$TMP/delete.list"
: > "$TMP/keep.list"

while IFS= read -r -d '' file; do
    rel="${file#"$NEW"/}"
    is_excluded "$rel" && continue
    new_hash="$(hash_file "$file")"

    if [ ! -e "$ROOT/$rel" ]; then
        printf '%s\t%s\n' "$new_hash" "$rel" >> "$TMP/add.list"
        continue
    fi

    local_hash="$(hash_file "$ROOT/$rel")"
    if [ "$local_hash" = "$new_hash" ]; then
        printf '%s\t%s\n' "$new_hash" "$rel" >> "$TMP/same.list"
        continue
    fi

    base_hash=""
    if [ -f "$MANIFEST" ]; then
        base_hash="$(awk -v p="$rel" '$2==p {print $1; exit}' "$MANIFEST")"
    fi

    if [ -n "$base_hash" ] && [ "$local_hash" = "$base_hash" ]; then
        printf '%s\t%s\n' "$new_hash" "$rel" >> "$TMP/update.list"
    else
        printf '%s\t%s\n' "$new_hash" "$rel" >> "$TMP/conflict.list"
    fi
done < <(find "$NEW/engine-rs" -type f -print0)

if [ -f "$MANIFEST" ]; then
    while IFS=$'\t' read -r base_hash rel; do
        [ -n "${rel:-}" ] || continue
        case "$rel" in engine-rs/*) ;; *) continue ;; esac
        is_excluded "$rel" && continue
        [ -e "$NEW/$rel" ] && continue
        [ -e "$ROOT/$rel" ] || continue
        local_hash="$(hash_file "$ROOT/$rel")"
        if [ "$local_hash" = "$base_hash" ]; then
            printf '%s\t%s\n' "$base_hash" "$rel" >> "$TMP/delete.list"
        else
            printf '%s\t%s\n' "$base_hash" "$rel" >> "$TMP/keep.list"
        fi
    done < "$MANIFEST"
fi

add_n="$(count_lines "$TMP/add.list")"
update_n="$(count_lines "$TMP/update.list")"
same_n="$(count_lines "$TMP/same.list")"
delete_n="$(count_lines "$TMP/delete.list")"
keep_n="$(count_lines "$TMP/keep.list")"
conflict_n="$(count_lines "$TMP/conflict.list")"

echo
echo "Bản đang cài: ${current_sha:-chưa rõ}"
echo "Bản mới:      $remote_sha"
echo
echo "Thêm mới:      $add_n"
echo "Cập nhật:      $update_n"
echo "Không đổi:     $same_n"
echo "Xoá:           $delete_n"
echo "Giữ file sửa:  $keep_n"
echo "Xung đột:      $conflict_n"

print_list() {
    local list="$1" label="$2" shown=0 limit=40
    [ -s "$list" ] || return 0
    echo
    echo "$label:"
    while IFS=$'\t' read -r _ rel; do
        [ -n "${rel:-}" ] || continue
        echo "  $rel"
        shown=$((shown + 1))
        if [ "$shown" -ge "$limit" ]; then
            echo "  ..."
            break
        fi
    done < "$list"
}

print_list "$TMP/add.list" "Thêm"
print_list "$TMP/update.list" "Ghi đè (bạn chưa sửa)"
print_list "$TMP/delete.list" "Xoá (bạn chưa sửa)"
print_list "$TMP/keep.list" "Giữ vì bạn đã sửa"
print_list "$TMP/conflict.list" "Xung đột — giữ bản của bạn"

write_metadata() {
    {
        while IFS= read -r -d '' file; do
            rel="${file#"$NEW"/}"
            is_excluded "$rel" && continue
            printf '%s\t%s\n' "$(hash_file "$file")" "$rel"
        done < <(find "$NEW/engine-rs" -type f -print0)
    } | sort -k2 > "$TMP/manifest.new"
    mv "$TMP/manifest.new" "$MANIFEST"
    printf '%s\n' "$remote_sha" > "$STATE"
}

STAMP="$(date +%Y%m%d-%H%M%S)"

copy_conflicts() {
    local target="$CONFLICT_ROOT/$STAMP"
    mkdir -p "$target"
    while IFS=$'\t' read -r _ rel; do
        [ -n "${rel:-}" ] || continue
        mkdir -p "$target/$(dirname "$rel")"
        cp -p "$NEW/$rel" "$target/$rel"
    done < "$TMP/conflict.list"
    echo "$target"
}

if [ "$add_n" -eq 0 ] && [ "$update_n" -eq 0 ] && [ "$delete_n" -eq 0 ]; then
    if [ "$APPLY" -eq 1 ]; then
        write_metadata
        echo
        echo "Không có thay đổi mã nguồn; đã ghi mốc ${remote_sha:0:12}."
        if [ "$conflict_n" -gt 0 ]; then
            target="$(copy_conflicts)"
            echo "Bản mới của file bạn đã sửa nằm trong: $target"
        fi
    else
        echo
        echo "Không có thay đổi mã nguồn."
    fi
    [ "$conflict_n" -eq 0 ] || exit 3
    exit 0
fi

if [ "$APPLY" -eq 0 ]; then
    echo
    echo "Chưa ghi gì. Chạy lại với --apply để áp dụng."
    [ "$conflict_n" -eq 0 ] || exit 3
    exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
    [ -t 0 ] || die "không có TTY; thêm --yes để chạy không hỏi"
    printf 'Áp dụng %s thay đổi? [y/N] ' "$((add_n + update_n + delete_n))"
    read -r answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) echo "Huỷ."; exit 0 ;;
    esac
fi

# --- áp dụng, có backup và rollback khi build fail ------------------------

BACKUP="$BACKUP_ROOT/$STAMP"
CONFLICTS="$CONFLICT_ROOT/$STAMP"
mkdir -p "$BACKUP" "$CONFLICTS"
: > "$TMP/applied.list"

backup_local() {
    local rel="$1"
    if [ -e "$ROOT/$rel" ]; then
        mkdir -p "$BACKUP/$(dirname "$rel")"
        cp -p "$ROOT/$rel" "$BACKUP/$rel"
        printf '%s|1\n' "$rel" >> "$TMP/applied.list"
    else
        printf '%s|0\n' "$rel" >> "$TMP/applied.list"
    fi
}

echo
echo "Áp dụng (backup: $BACKUP)"
while IFS=$'\t' read -r _ rel; do
    [ -n "${rel:-}" ] || continue
    backup_local "$rel"
    mkdir -p "$ROOT/$(dirname "$rel")"
    cp -p "$NEW/$rel" "$ROOT/$rel"
    echo "  + $rel"
done < <(cat "$TMP/add.list" "$TMP/update.list")

while IFS=$'\t' read -r _ rel; do
    [ -n "${rel:-}" ] || continue
    backup_local "$rel"
    rm -f "$ROOT/$rel"
    echo "  - $rel"
done < "$TMP/delete.list"

if [ -s "$TMP/conflict.list" ]; then
    while IFS=$'\t' read -r _ rel; do
        [ -n "${rel:-}" ] || continue
        mkdir -p "$CONFLICTS/$(dirname "$rel")"
        cp -p "$NEW/$rel" "$CONFLICTS/$rel"
    done < "$TMP/conflict.list"
fi

if [ "$BUILD" -eq 1 ]; then
    if command -v cargo >/dev/null 2>&1; then
        echo
        echo "Build engine-rs release ..."
        if ! ( cd "$ROOT/engine-rs" \
            && PATH="$ROOT/.venv/bin:$PATH" \
               WHISPER_DONT_GENERATE_BINDINGS=1 \
               cargo build --release ); then
            echo "Build fail — khôi phục bản cũ ..." >&2
            while IFS='|' read -r rel had; do
                [ -n "${rel:-}" ] || continue
                if [ "$had" = 1 ]; then
                    mkdir -p "$ROOT/$(dirname "$rel")"
                    cp -p "$BACKUP/$rel" "$ROOT/$rel"
                else
                    rm -f "$ROOT/$rel"
                fi
            done < "$TMP/applied.list"
            echo "Đã rollback. .l4m-version không đổi." >&2
            exit 1
        fi
    else
        echo "Không thấy cargo — bỏ qua build (dùng --no-build để tắt hẳn)." >&2
    fi
fi

write_metadata

if [ "$RESTART" -eq 1 ]; then
    echo
    if command -v systemctl >/dev/null 2>&1 \
        && systemctl list-unit-files 2>/dev/null | grep -q '^l4m-engine\.service'; then
        if [ "$(id -u)" -eq 0 ]; then
            systemctl restart l4m-engine
        else
            sudo systemctl restart l4m-engine
        fi
        echo "Đã restart l4m-engine."
    else
        echo "Không thấy unit l4m-engine.service."
        echo "Chạy tay: cd \"$ROOT/engine-rs\" && ./target/release/l4m-engine"
    fi
fi

echo
echo "Xong: ${remote_sha:0:12}"

if [ "$conflict_n" -gt 0 ]; then
    echo
    echo "Có $conflict_n file bạn đã sửa nên KHÔNG bị ghi đè."
    echo "Bản mới của các file đó nằm trong: $CONFLICTS"
    echo "So hai bản rồi merge tay; lần update sau chúng vẫn được giữ."
    exit 3
fi

exit 0
