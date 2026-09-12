#!/usr/bin/env python3
"""生成带哈希锁定的 KouriChat 安装脚本。

用法（在仓库根目录）：
    python tools/gen_install.py \
        --main dist/kourichat-1.5.0.2-py3-none-any.whl \
        --elixir dist/elixir-0.1.0-py3-none-any.whl

默认会自动挑选 `dist/kourichat-*.whl` 与根目录/`dist` 下最新的
`elixir-*.whl`，产出：

    dist/install.ps1        Windows / PowerShell 安装脚本
    dist/install.sh         Linux / macOS 安装脚本
    dist/requirements.lock  全量依赖哈希锁（uv export --generate-hashes 等价的
                             `--require-hashes` 锁文件，含本地 elixir wheel）

安装脚本流程（生成物内）：
    1. 检查 Python（缺失/版本不足 → 报错并提示官网安装）
    2. 检查 uv（缺失 → 官方安装脚本自动安装）
    3. 校验 主 wheel / elixir wheel / requirements.lock 的 SHA256
    4. `uv pip install --require-hashes -r requirements.lock`（含主 wheel）
    5. 生成 `kourichat` 命令 shim 并打印 PATH 指引
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_latest(patterns: list[str]) -> Path:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(REPO.glob(pattern))
        candidates.extend((REPO / "dist").glob(pattern))
    if not candidates:
        raise SystemExit(f"未找到匹配文件：{patterns}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def export_lock() -> str:
    """用 uv 从 uv.lock 导出全量依赖（含 elixir 本地 wheel）+ 哈希。"""
    cmd = ["uv", "export", "--frozen", "--no-dev", "--no-emit-project",
           "--format", "requirements-txt"]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(
            "uv export 失败，请先在本仓库执行 `uv lock` 并确认 uv.lock 最新。\n"
            + (proc.stderr or proc.stdout))
    return proc.stdout


def replace_elixir_block(lock: str, wheel: Path, digest: str) -> str:
    """把 uv export 里的 elixir 引用替换为本次传入 wheel 的路径与哈希。"""
    lines = lock.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.search(r"\belixir-[^\s\\]*\.whl", line):
            start = i
            break
    if start is None:
        raise SystemExit("uv export 输出中未找到 elixir wheel 行；"
                         "请确认 uv.lock 中 elixir 使用本地 path source。")
    end = start + 1
    while end < len(lines) and (
            lines[end].startswith((" ", "\t")) or not lines[end].strip()):
        end += 1
    block = [f"./{wheel.name} --hash=sha256:{digest}", "    # via kourichat", ""]
    return "\n".join(lines[:start] + block + lines[end:]) + "\n"


def ensure_hashed(lock: str) -> None:
    """粗校验：锁文件必须含哈希，且覆盖 elixir 本地 wheel。"""
    if "--hash=sha256:" not in lock:
        raise SystemExit("依赖锁不含 --hash=sha256，生成失败")
    if "elixir-" not in lock:
        raise SystemExit("依赖锁缺少 elixir wheel 行")
def build_lock(main: Path, main_sha: str, elixir: Path, elixir_sha: str) -> str:
    lock = export_lock()
    if not lock.endswith("\n"):
        lock += "\n"
    lock = replace_elixir_block(lock, elixir, elixir_sha)
    lock = lock.rstrip("\n") + f"\n./{main.name} --hash=sha256:{main_sha}\n"
    ensure_hashed(lock)
    return lock


PS_TEMPLATE = r'''#Requires -Version 5.1
<#
  KouriChat @@VERSION@@ 安装脚本（哈希锁定）
  由 tools/gen_install.py 生成，请勿手改。
  用法：
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Uninstall,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "KouriChat")
)

$ErrorActionPreference = "Stop"
$PythonMin    = "@@PYTHON_MIN@@"
$MainWheel    = "@@MAIN_WHEEL@@"
$MainSha256   = "@@MAIN_SHA@@"
$ElixirWheel  = "@@ELIXIR_WHEEL@@"
$ElixirSha256 = "@@ELIXIR_SHA@@"
$LockFile     = "@@LOCK_FILE@@"
$LockSha256   = "@@LOCK_SHA@@"

$Root = $PSScriptRoot
if (-not $Root) { $Root = (Get-Location).Path }
$Root = (Resolve-Path -Path $Root).Path

function Write-Info($m)  { Write-Host "[信息] $m" -ForegroundColor Cyan }
function Write-Ok($m)    { Write-Host "[通过] $m" -ForegroundColor Green }
function Write-Note($m)  { Write-Host "[注意] $m" -ForegroundColor Yellow }
function Fail($m)        { Write-Host "[错误] $m" -ForegroundColor Red; exit 1 }

$isWin = ($env:OS -eq "Windows_NT") -or $IsWindows

if ($Uninstall) {
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
        Write-Ok "已卸载：$InstallDir"
    } else {
        Write-Note "未找到安装目录：$InstallDir"
    }
    exit 0
}

Write-Info "KouriChat @@VERSION@@ 安装程序"
Write-Info "安装目录：$InstallDir"
Write-Info "Python 最低版本：$PythonMin"

# ---------- 1) 检查 Python ----------
function Test-PyVersion([string]$ver) {
    $p = $ver.Trim().Split(".")
    $r = $PythonMin.Split(".")
    if ($p.Count -lt 2) { return $false }
    if ([int]$p[0] -gt [int]$r[0]) { return $true }
    return ([int]$p[0] -eq [int]$r[0]) -and ([int]$p[1] -ge [int]$r[1])
}

$pyExe = $null; $pyArgs = @(); $pyVersion = $null
foreach ($c in @(
        @{ Exe = "py";      Args = @("-3.14") },
        @{ Exe = "py";      Args = @("-3") },
        @{ Exe = "python";  Args = @() },
        @{ Exe = "python3"; Args = @() })) {
    try {
        $callArgs = @($c.Args) + @("-c", "import sys;print('%d.%d' % sys.version_info[:2])")
        $out = & $c.Exe @callArgs 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $v = ($out | Select-Object -First 1).ToString().Trim()
            if (Test-PyVersion $v) { $pyExe = $c.Exe; $pyArgs = $c.Args; $pyVersion = $v; break }
            if (-not $pyVersion) { $pyVersion = $v }
        }
    } catch { }
}
if (-not $pyExe) {
    if ($pyVersion) {
        Fail "检测到 Python $pyVersion，但要求 >= $PythonMin。请先安装：https://www.python.org/downloads/"
    }
    Fail "未检测到 Python。请先安装 Python $PythonMin+：https://www.python.org/downloads/（Windows 安装时勾选 Add to PATH）"
}
Write-Ok "Python $pyVersion（$pyExe $($pyArgs -join ' ')）"

# ---------- 2) 检查 / 安装 uv ----------
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    if ($DryRun) {
        Write-Note "uv 未安装（DryRun 跳过安装；实际运行会从官方脚本安装）"
    } else {
        Write-Info "未检测到 uv，正在从官方安装..."
        try {
            Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" | Invoke-Expression
        } catch {
            Fail "uv 安装失败：$($_.Exception.Message)`n请手动安装：https://docs.astral.sh/uv/getting-started/installation/"
        }
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        $uv = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uv) { Fail "uv 安装后仍不可用，请重开终端后重试。" }
    }
} else {
    Write-Ok "uv 已安装：$(& uv --version)"
}

# ---------- 3) SHA256 校验 ----------
function Assert-Hash([string]$path, [string]$expected, [string]$label) {
    if (-not (Test-Path $path)) { Fail "缺少文件：$path" }
    $actual = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLower()
    if ($actual -ne $expected.ToLower()) {
        Fail "$label 哈希不匹配！`n  期望：$expected`n  实际：$actual`n  文件可能被篡改或损坏。"
    }
    Write-Ok "$label 哈希校验通过"
}

Assert-Hash (Join-Path $Root $MainWheel)   $MainSha256   "主程序 wheel（$MainWheel）"
Assert-Hash (Join-Path $Root $ElixirWheel) $ElixirSha256 "elixir wheel（$ElixirWheel）"
Assert-Hash (Join-Path $Root $LockFile)    $LockSha256   "依赖锁（$LockFile）"

if ($DryRun) { Write-Ok "DryRun 完成：Python / uv / 哈希校验均通过，未执行安装。"; exit 0 }

# ---------- 4) 哈希锁定安装 ----------
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$InstallDir = (Resolve-Path -Path $InstallDir).Path
$venv = Join-Path $InstallDir "venv"
Write-Info "创建虚拟环境：$venv"
& uv venv --python $pyVersion $venv
if ($LASTEXITCODE -ne 0) { Fail "uv venv 失败" }

if ($isWin) { $venvPython = Join-Path $venv "Scripts\python.exe" } else { $venvPython = Join-Path $venv "bin/python" }
Push-Location $Root
try {
    Write-Info "以 --require-hashes 安装（全量依赖哈希锁定）..."
    & uv pip install --python $venvPython --require-hashes -r (Join-Path $Root $LockFile)
    if ($LASTEXITCODE -ne 0) { Fail "依赖安装失败（可能被哈希校验拒绝）" }
} finally { Pop-Location }

# ---------- 5) 生成 kourichat 命令 ----------
if ($isWin) {
    $exe  = Join-Path $venv "Scripts\kourichat.exe"
    $shim = Join-Path $InstallDir "kourichat.cmd"
    "@echo off`r`n`"$exe`" %*" | Set-Content -Encoding ASCII -Path $shim
} else {
    $exe  = Join-Path $venv "bin/kourichat"
    $shim = Join-Path $InstallDir "kourichat"
    "#!/usr/bin/env sh`nexec `"$exe`" `"`$@`"" | Set-Content -Encoding ASCII -Path $shim
    if (Get-Command chmod -ErrorAction SilentlyContinue) { & chmod +x $shim }
}
Write-Ok "已生成命令：$shim"
Write-Ok "安装完成！"
Write-Host ""
Write-Host "运行方式（任选其一）：" -ForegroundColor White
Write-Host "  1) 直接：`"$InstallDir\kourichat.cmd`" run"
Write-Host "  2) 把 $InstallDir 加入 PATH 后：kourichat run"
Write-Host "首次运行会自动生成 kourichat.toml，浏览器打开 http://127.0.0.1:8080" -ForegroundColor Gray
Write-Host "卸载：powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall" -ForegroundColor Gray
'''


BASH_TEMPLATE = r'''#!/usr/bin/env bash
# KouriChat @@VERSION@@ 安装脚本（哈希锁定）
# 由 tools/gen_install.py 生成，请勿手改。
# 用法： ./install.sh [--dry-run] [--uninstall]
set -euo pipefail

PYTHON_MIN="@@PYTHON_MIN@@"
MAIN_WHEEL="@@MAIN_WHEEL@@"
MAIN_SHA="@@MAIN_SHA@@"
ELIXIR_WHEEL="@@ELIXIR_WHEEL@@"
ELIXIR_SHA="@@ELIXIR_SHA@@"
LOCK_FILE="@@LOCK_FILE@@"
LOCK_SHA="@@LOCK_SHA@@"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${KOURICHAT_HOME:-$HOME/.local/share/kourichat}"
DRY_RUN=0

info() { printf '\033[36m[信息]\033[0m %s\n' "$1"; }
ok()   { printf '\033[32m[通过]\033[0m %s\n' "$1"; }
note() { printf '\033[33m[注意]\033[0m %s\n' "$1"; }
fail() { printf '\033[31m[错误]\033[0m %s\n' "$1" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --uninstall) rm -rf "$INSTALL_DIR"; ok "已卸载：$INSTALL_DIR"; exit 0 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) fail "未知参数：$arg" ;;
  esac
done

info "KouriChat @@VERSION@@ 安装程序"
info "安装目录：$INSTALL_DIR"
info "Python 最低版本：$PYTHON_MIN"

# ---------- 1) 检查 Python ----------
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys;print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    if [ -n "$ver" ]; then
      maj="${ver%%.*}"; min="${ver##*.}"
      req_maj="${PYTHON_MIN%%.*}"; req_min="${PYTHON_MIN##*.}"
      if [ "$maj" -gt "$req_maj" ] || { [ "$maj" -eq "$req_maj" ] && [ "$min" -ge "$req_min" ]; }; then
        PY="$cand"; PY_VER="$ver"; break
      fi
      note "检测到 $cand 版本 $ver，低于要求的 $PYTHON_MIN"
    fi
  fi
done
[ -n "$PY" ] || fail "未检测到 Python >= $PYTHON_MIN。请先安装：https://www.python.org/downloads/"
ok "Python $PY_VER（$PY）"

# ---------- 2) 检查 / 安装 uv ----------
if ! command -v uv >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then
    note "uv 未安装（dry-run 跳过安装；实际会从官方脚本安装）"
  else
    info "未检测到 uv，正在从官方安装..."
    command -v curl >/dev/null 2>&1 || fail "缺少 curl，无法自动安装 uv：https://docs.astral.sh/uv/getting-started/installation/"
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv 安装失败"
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv 安装后仍不可用，请重开终端"
  fi
else
  ok "uv 已安装：$(uv --version)"
fi

# ---------- 3) SHA256 校验 ----------
sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}';
  else fail "缺少 sha256sum/shasum，无法校验哈希"; fi
}
assert_hash() {
  [ -f "$1" ] || fail "缺少文件：$1"
  actual="$(sha256_file "$1")"
  [ "$actual" = "$2" ] || fail "$3 哈希不匹配！期望 $2，实际 $actual"
  ok "$3 哈希校验通过"
}
assert_hash "$ROOT/$MAIN_WHEEL" "$MAIN_SHA" "主程序 wheel（$MAIN_WHEEL）"
assert_hash "$ROOT/$ELIXIR_WHEEL" "$ELIXIR_SHA" "elixir wheel（$ELIXIR_WHEEL）"
assert_hash "$ROOT/$LOCK_FILE" "$LOCK_SHA" "依赖锁（$LOCK_FILE）"

if [ "$DRY_RUN" -eq 1 ]; then ok "dry-run 完成：Python / uv / 哈希校验均通过，未执行安装。"; exit 0; fi

# ---------- 4) 哈希锁定安装 ----------
mkdir -p "$INSTALL_DIR"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"
VENV="$INSTALL_DIR/venv"
info "创建虚拟环境：$VENV"
uv venv --python "$PY_VER" "$VENV"
info "以 --require-hashes 安装（全量依赖哈希锁定）..."
(cd "$ROOT" && uv pip install --python "$VENV/bin/python" --require-hashes -r "$ROOT/$LOCK_FILE") \
  || fail "依赖安装失败（可能被哈希校验拒绝）"

# ---------- 5) 生成 kourichat 命令 ----------
SHIM="$INSTALL_DIR/kourichat"
printf '#!/usr/bin/env sh\nexec "%s" "$@"\n' "$VENV/bin/kourichat" > "$SHIM"
chmod +x "$SHIM"
ok "已生成命令：$SHIM"
ok "安装完成！"
echo
echo "运行方式（任选其一）："
echo "  1) 直接：$SHIM run"
echo "  2) 把 $INSTALL_DIR 加入 PATH 后：kourichat run"
echo "首次运行会自动生成 kourichat.toml，浏览器打开 http://127.0.0.1:8080"
echo "卸载：$0 --uninstall"
'''


def render(template: str, tokens: dict[str, str]) -> str:
    out = template
    for key, value in tokens.items():
        out = out.replace(f"@@{key}@@", value)
    if "@@" in out:
        leftover = sorted(set(re.findall(r"@@[A-Z_]+@@", out)))
        raise SystemExit(f"模板存在未替换占位符：{leftover}")
    return out


def detect_version(main_name: str) -> str:
    m = re.search(r"kourichat-(.+?)-py3", main_name)
    return m.group(1) if m else "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成带哈希锁定的 KouriChat 安装脚本")
    ap.add_argument("--main", help="主程序 wheel（缺省取 dist/kourichat-*.whl 最新）")
    ap.add_argument("--elixir", help="elixir wheel（缺省自动查找）")
    ap.add_argument("--out-dir", default=str(REPO / "dist"), help="输出目录（默认 dist/）")
    ap.add_argument("--shell", choices=["powershell", "bash", "both"],
                    default="both", help="生成哪种安装脚本（默认 both）")
    ap.add_argument("--python-min", default="3.14", help="要求的最低 Python 版本（默认 3.14）")
    args = ap.parse_args()

    main_wheel = (Path(args.main).resolve() if args.main
                  else pick_latest(["kourichat-*.whl"]))
    elixir_wheel = (Path(args.elixir).resolve() if args.elixir
                    else pick_latest(["elixir-*.whl"]))
    for p in (main_wheel, elixir_wheel):
        if not p.is_file() or p.suffix != ".whl":
            raise SystemExit(f"不是有效的 wheel 文件：{p}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    for src in (main_wheel, elixir_wheel):
        dst = out_dir / src.name
        if dst.resolve() != src.resolve():
            shutil.copy2(src, dst)

    main_sha = sha256(out_dir / main_wheel.name)
    elixir_sha = sha256(out_dir / elixir_wheel.name)
    lock = build_lock(main_wheel, main_sha, elixir_wheel, elixir_sha)
    lock_path = out_dir / "requirements.lock"
    lock_path.write_text(lock, encoding="utf-8")
    lock_sha = sha256(lock_path)

    tokens = {
        "VERSION": detect_version(main_wheel.name),
        "PYTHON_MIN": args.python_min,
        "MAIN_WHEEL": main_wheel.name,
        "MAIN_SHA": main_sha,
        "ELIXIR_WHEEL": elixir_wheel.name,
        "ELIXIR_SHA": elixir_sha,
        "LOCK_FILE": lock_path.name,
        "LOCK_SHA": lock_sha,
    }

    made: list[Path] = [lock_path]
    if args.shell in ("powershell", "both"):
        p = out_dir / "install.ps1"
        p.write_text(render(PS_TEMPLATE, tokens), encoding="utf-8-sig")
        made.append(p)
    if args.shell in ("bash", "both"):
        p = out_dir / "install.sh"
        p.write_text(render(BASH_TEMPLATE, tokens), encoding="utf-8")
        made.append(p)

    print("已生成：")
    for p in made:
        print(f"  {p}  ({p.stat().st_size} bytes)")
    print()
    print(f"主程序 wheel : {main_wheel.name}  sha256={main_sha}")
    print(f"elixir wheel : {elixir_wheel.name}  sha256={elixir_sha}")
    print(f"依赖锁       : {lock_path.name}  sha256={lock_sha}  "
          f"({len(lock.splitlines())} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
