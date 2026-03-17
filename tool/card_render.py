"""
Grok 搜索结果卡片渲染器

基于 PIL/Pillow 纯本地渲染，将搜索结果渲染为分区面板风格的深色卡片图片。
支持 Markdown 子集：标题、列表、代码块、引用、粗体、行内代码。
"""

from __future__ import annotations

import logging
import os
import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# Module-level logger, can be overridden via set_logger()
_module_logger = logging.getLogger(__name__)


def set_logger(logger: logging.Logger) -> None:
    """Set the logger used by card_render (call before init_fonts)."""
    global _module_logger
    _module_logger = logger


# ─── 主题配色 ────────────────────────────────────────────────

THEME_DARK = {
    "bg": (15, 17, 21),
    "panel": (24, 28, 36),
    "panel_border": (45, 52, 64),
    "text": (230, 235, 240),
    "dim": (140, 150, 160),
    "accent": (0, 220, 180),
    "bold": (255, 255, 255),
    "code_bg": (18, 20, 26),
    "code_text": (180, 220, 255),
    "inline_code_bg": (35, 40, 52),
    "inline_code_text": (180, 220, 255),
    "quote_bar": (0, 220, 180),
    "quote_text": (160, 170, 180),
    "bullet": (0, 220, 180),
    "link": (100, 180, 255),
    "source_idx": (0, 220, 180),
    "source_panel": (20, 22, 28),
}

THEME_LIGHT = {
    "bg": (245, 245, 248),
    "panel": (255, 255, 255),
    "panel_border": (210, 215, 225),
    "text": (30, 35, 50),
    "dim": (80, 90, 110),
    "accent": (0, 160, 130),
    "bold": (10, 10, 20),
    "code_bg": (238, 240, 246),
    "code_text": (40, 80, 160),
    "inline_code_bg": (228, 232, 240),
    "inline_code_text": (40, 80, 160),
    "quote_bar": (0, 160, 130),
    "quote_text": (90, 100, 120),
    "bullet": (0, 160, 130),
    "link": (30, 100, 200),
    "source_idx": (0, 160, 130),
    "source_panel": (240, 242, 248),
}


def _get_theme(theme: str = "auto") -> dict[str, tuple]:
    """获取主题配色。theme='auto' 时根据本地时间自动切换 (7:00-18:00 浅色)"""
    if theme == "light":
        return THEME_LIGHT
    if theme == "dark":
        return THEME_DARK
    from datetime import datetime

    hour = datetime.now().hour
    return THEME_LIGHT if 7 <= hour < 18 else THEME_DARK


# 模块级引用，render_search_card 调用时会根据 theme 参数重新指向
THEME: dict[str, tuple] = THEME_DARK

# ─── 字体管理 ───────────────────────────────────────────────

_FONT_DOWNLOAD_URL = (
    "https://mirrors.tuna.tsinghua.edu.cn/github-release/be5invis/Sarasa-Gothic/"
    "Sarasa%20Gothic%2C%20Version%201.0.36/SarasaTermSlabSC-TTF-1.0.36.7z"
)
_DEFAULT_FONT_REGULAR = "SarasaTermSlabSC-Regular.ttf"
_DEFAULT_FONT_BOLD = "SarasaTermSlabSC-Bold.ttf"

# 运行时字体路径（由 init_fonts 设置）
_font_regular_path: str = ""
_font_bold_path: str = ""
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_fonts_ready = False


def _find_fonts_in_dir(font_dir: str) -> tuple[str, str] | None:
    """在目录中查找可用字体对 (regular, bold)，返回 (regular_path, bold_path) 或 None"""
    if not os.path.isdir(font_dir):
        return None
    ttf_files = [f for f in os.listdir(font_dir) if f.lower().endswith(".ttf")]
    if not ttf_files:
        return None

    regular = bold = None
    for f in sorted(ttf_files):
        fl = f.lower()
        if "bold" in fl:
            bold = bold or os.path.join(font_dir, f)
        elif any(k in fl for k in ("regular", "normal", "medium")):
            regular = regular or os.path.join(font_dir, f)

    if not regular and not bold and ttf_files:
        regular = bold = os.path.join(font_dir, ttf_files[0])
    elif regular and not bold:
        bold = regular
    elif bold and not regular:
        regular = bold

    return (regular, bold) if regular and bold else None


def _extract_7z(archive_path: str, output_dir: str, _log: logging.Logger) -> None:
    """Extract a 7z archive. Tries system 7z binary first, then py7zr."""
    import subprocess

    for cmd in ("7z", "7za"):
        try:
            result = subprocess.run(
                [cmd, "x", archive_path, f"-o{output_dir}", "-y"],
                capture_output=True,
                timeout=120,
            )
            if result.returncode == 0:
                _log.info(f"使用 {cmd} 解压成功")
                return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    _log.info("系统未安装 7z，尝试使用 py7zr 解压 ...")
    try:
        import py7zr
    except ImportError:
        from pip._internal.cli.main import main as pip_main

        pip_main(["install", "py7zr", "-q"])
        import py7zr

    with py7zr.SevenZipFile(archive_path, "r") as z:
        z.extractall(path=output_dir)


def _download_fonts(font_dir: str) -> None:
    """从清华镜像下载字体 7z 包并解压"""
    import shutil
    import tempfile
    import threading
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _log = _module_logger
    _NUM_THREADS = 4

    os.makedirs(font_dir, exist_ok=True)
    archive_path = os.path.join(font_dir, "_font_download.7z")

    if not os.path.exists(archive_path):
        _log.info("正在从清华镜像下载字体 ...")

        supports_range = False
        total_size = 0
        try:
            probe = urllib.request.Request(_FONT_DOWNLOAD_URL)
            probe.add_header("Range", "bytes=0-0")
            probe_resp = urllib.request.urlopen(probe, timeout=30)
            if probe_resp.status == 206:
                content_range = probe_resp.headers.get("Content-Range", "")
                if "/" in content_range:
                    total_size = int(content_range.split("/")[-1])
                    supports_range = True
            probe_resp.close()
        except Exception:
            pass

        if supports_range and total_size > 1024 * 1024:
            _log.info(
                f"文件大小: {total_size / 1024 / 1024:.1f}MB, "
                f"使用 {_NUM_THREADS} 线程下载"
            )
            chunk_ranges = []
            chunk_sz = total_size // _NUM_THREADS
            for i in range(_NUM_THREADS):
                start = i * chunk_sz
                end = (
                    (total_size - 1)
                    if i == _NUM_THREADS - 1
                    else (start + chunk_sz - 1)
                )
                chunk_ranges.append((i, start, end))

            downloaded_lock = threading.Lock()
            downloaded_bytes = [0]
            last_logged = [-1]

            def _download_chunk(idx: int, byte_start: int, byte_end: int) -> str:
                part_file = os.path.join(font_dir, f"_chunk_{idx}.part")
                r = urllib.request.Request(_FONT_DOWNLOAD_URL)
                r.add_header("Range", f"bytes={byte_start}-{byte_end}")
                response = urllib.request.urlopen(r, timeout=180)
                buf_size = 64 * 1024
                with open(part_file, "wb") as f:
                    while True:
                        buf = response.read(buf_size)
                        if not buf:
                            break
                        f.write(buf)
                        with downloaded_lock:
                            downloaded_bytes[0] += len(buf)
                            pct = int(downloaded_bytes[0] / total_size * 100)
                            if pct // 10 > last_logged[0] // 10:
                                dl_mb = downloaded_bytes[0] / 1024 / 1024
                                tot_mb = total_size / 1024 / 1024
                                _log.info(
                                    f"字体下载进度: {pct}% ({dl_mb:.1f}/{tot_mb:.1f}MB)"
                                )
                                last_logged[0] = pct
                return part_file

            part_files = [None] * _NUM_THREADS
            try:
                with ThreadPoolExecutor(max_workers=_NUM_THREADS) as pool:
                    futures = {
                        pool.submit(_download_chunk, idx, s, e): idx
                        for idx, s, e in chunk_ranges
                    }
                    for future in as_completed(futures):
                        idx = futures[future]
                        part_files[idx] = future.result()

                with open(archive_path, "wb") as out:
                    for pf in part_files:
                        with open(pf, "rb") as inp:
                            shutil.copyfileobj(inp, out)
                _log.info("字体下载完成，正在校验 ...")
            finally:
                for pf in part_files:
                    if pf and os.path.exists(pf):
                        os.remove(pf)
        else:
            if not supports_range:
                _log.info("服务器不支持分段下载，使用单线程模式")
            total_mb = total_size / 1024 / 1024 if total_size > 0 else 0
            if total_mb:
                _log.info(f"文件大小: {total_mb:.1f}MB")

            resp = urllib.request.urlopen(
                urllib.request.Request(_FONT_DOWNLOAD_URL), timeout=180
            )
            downloaded = 0
            chunk_size = 64 * 1024
            last_logged_pct = -1
            part_path = archive_path + ".part"

            with open(part_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(min(downloaded / total_size, 1.0) * 100)
                        if pct // 10 > last_logged_pct // 10:
                            f.flush()
                            os.fsync(f.fileno())
                            _log.info(
                                f"字体下载进度: {pct}% "
                                f"({downloaded / 1024 / 1024:.1f}/{total_mb:.1f}MB)"
                            )
                            last_logged_pct = pct

            os.rename(part_path, archive_path)
            _log.info("字体下载完成，正在校验 ...")
    else:
        _log.info("检测到已下载的字体包，正在校验 ...")

    _SEVEN_Z_MAGIC = b"7z\xbc\xaf\x27\x1c"
    with open(archive_path, "rb") as f:
        header = f.read(6)
    if header != _SEVEN_Z_MAGIC:
        _log.warning("下载的文件不是有效的 7z 压缩包，已删除，请重试")
        os.remove(archive_path)
        raise ValueError("Downloaded file is not a valid 7z archive")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _extract_7z(archive_path, tmp_dir, _log)

            kept = 0
            for root, _dirs, files in os.walk(tmp_dir):
                for fname in files:
                    if fname.lower().endswith(".ttf") and fname in (
                        _DEFAULT_FONT_REGULAR,
                        _DEFAULT_FONT_BOLD,
                    ):
                        shutil.copy2(os.path.join(root, fname), font_dir)
                        kept += 1

            _log.info(f"字体安装完成 ({kept} 个文件)")
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


def init_fonts(font_dir: str | None = None) -> bool:
    """初始化字体。如果 font_dir 有字体就用，没有就自动下载。"""
    global _font_regular_path, _font_bold_path, _fonts_ready, _font_cache

    if font_dir is None:
        font_dir = os.path.join(os.path.dirname(__file__), "font")

    found = _find_fonts_in_dir(font_dir)
    if found:
        _font_regular_path, _font_bold_path = found
        _font_cache.clear()
        _fonts_ready = True
        return True

    try:
        _download_fonts(font_dir)
    except Exception as e:
        _module_logger.warning(f"字体下载失败: {e}")
        return False

    found = _find_fonts_in_dir(font_dir)
    if found:
        _font_regular_path, _font_bold_path = found
        _font_cache.clear()
        _fonts_ready = True
        return True

    return False


def _get_font(bold: bool = False, size: int = 18) -> ImageFont.FreeTypeFont:
    if not _fonts_ready:
        init_fonts()
    path = _font_bold_path if bold else _font_regular_path
    key = (path, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, size)
    return _font_cache[key]


# ─── 富文本工具 ──────────────────────────────────────────────

# 富文本片段: (text, style)  style: "n"=normal, "b"=bold, "c"=inline_code
_RichSpan = tuple[str, str]
_RE_RICH = re.compile(r"(\*\*.*?\*\*|`[^`]+`)")


def _parse_rich(text: str) -> list[_RichSpan]:
    """将含 **粗体** 和 `行内代码` 的文本解析为 [(text, style), ...] 列表"""
    spans: list[_RichSpan] = []
    last = 0
    for m in _RE_RICH.finditer(text):
        if m.start() > last:
            spans.append((text[last : m.start()], "n"))
        matched = m.group(0)
        if matched.startswith("**") and matched.endswith("**"):
            spans.append((matched[2:-2], "b"))
        elif matched.startswith("`") and matched.endswith("`"):
            spans.append((matched[1:-1], "c"))
        last = m.end()
    if last < len(text):
        spans.append((text[last:], "n"))
    return spans


def _wrap_rich(
    spans: list[_RichSpan],
    font_normal: ImageFont.FreeTypeFont,
    font_bold: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[list[_RichSpan]]:
    """将富文本片段列表自动换行，返回按行分组的片段列表。"""
    lines: list[list[_RichSpan]] = []
    cur_line: list[_RichSpan] = []
    cur_width = 0

    for seg_text, style in spans:
        font = font_bold if style == "b" else font_normal
        cur_seg = ""
        for ch in seg_text:
            if ch == "\n":
                if cur_seg:
                    cur_line.append((cur_seg, style))
                    cur_seg = ""
                lines.append(cur_line)
                cur_line = []
                cur_width = 0
                continue
            ch_w = draw.textbbox((0, 0), ch, font=font)[2]
            if cur_width + ch_w > max_width and (cur_line or cur_seg):
                if cur_seg:
                    cur_line.append((cur_seg, style))
                    cur_seg = ""
                lines.append(cur_line)
                cur_line = []
                cur_width = 0
            cur_seg += ch
            cur_width += ch_w
        if cur_seg:
            cur_line.append((cur_seg, style))

    if cur_line:
        lines.append(cur_line)
    return lines


def _wrap_plain(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """纯文本换行（不含 bold/code 标记的场景）"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            test_w = (
                draw.textbbox((0, 0), current + ch, font=font)[2]
                if current
                else draw.textbbox((0, 0), ch, font=font)[2]
            )
            if test_w <= max_width:
                current += ch
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def _text_width(
    text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw
) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    return font.size + 8


def _draw_rich_spans(
    spans: list[_RichSpan],
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    font_normal: ImageFont.FreeTypeFont,
    font_bold: ImageFont.FreeTypeFont,
    color_normal: tuple,
    color_bold: tuple,
) -> None:
    """绘制一行富文本片段，支持粗体和行内代码"""
    cx = x
    for text, style in spans:
        if style == "c":
            # 行内代码：带背景色
            code_font = font_normal
            tw = draw.textbbox((0, 0), text, font=code_font)[2]
            pad_x, pad_y = 4, 2
            draw.rounded_rectangle(
                [cx - 1, y - pad_y, cx + tw + pad_x * 2, y + code_font.size + pad_y],
                radius=4,
                fill=THEME["inline_code_bg"],
            )
            draw.text(
                (cx + pad_x, y), text, font=code_font, fill=THEME["inline_code_text"]
            )
            cx += tw + pad_x * 2 + 3
        else:
            font = font_bold if style == "b" else font_normal
            color = color_bold if style == "b" else color_normal
            draw.text((cx, y), text, font=font, fill=color)
            cx += draw.textbbox((0, 0), text, font=font)[2]


# ─── Markdown → Section 解析 ────────────────────────────────

_RE_HEADER = re.compile(r"^(#{1,3})\s+(.*)")
_RE_BULLET = re.compile(r"^[\-\*]\s+(.*)")
_RE_NUMBERED = re.compile(r"^(\d+)\.\s+(.*)")
_RE_QUOTE = re.compile(r"^>\s?(.*)")
_RE_CODE_FENCE = re.compile(r"^```")


class _Element:
    """渲染元素基类"""

    def height(self, ctx: "_Ctx") -> int:
        raise NotImplementedError

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        raise NotImplementedError


class _TextElem(_Element):
    def __init__(self, text: str):
        self.text = text

    def _wrapped(self, ctx: "_Ctx") -> list[list[_RichSpan]]:
        spans = _parse_rich(self.text)
        return _wrap_rich(spans, ctx.f_content, ctx.f_bold, ctx.cw, ctx.draw)

    def height(self, ctx: "_Ctx") -> int:
        return len(self._wrapped(ctx)) * _line_height(ctx.f_content) + 2

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        lh = _line_height(ctx.f_content)
        for line_spans in self._wrapped(ctx):
            _draw_rich_spans(
                line_spans,
                ctx.draw,
                x,
                y,
                ctx.f_content,
                ctx.f_bold,
                THEME["text"],
                THEME["bold"],
            )
            y += lh
        return y + 2


class _BulletElem(_Element):
    def __init__(self, text: str, marker: str = "•"):
        self.text = text
        self.marker = marker

    def _wrapped(self, ctx: "_Ctx") -> list[list[_RichSpan]]:
        spans = _parse_rich(self.text)
        return _wrap_rich(spans, ctx.f_content, ctx.f_bold, ctx.cw - 22, ctx.draw)

    def height(self, ctx: "_Ctx") -> int:
        return len(self._wrapped(ctx)) * _line_height(ctx.f_content) + 2

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        lh = _line_height(ctx.f_content)
        ctx.draw.text((x + 2, y), self.marker, font=ctx.f_content, fill=THEME["bullet"])
        for line_spans in self._wrapped(ctx):
            _draw_rich_spans(
                line_spans,
                ctx.draw,
                x + 22,
                y,
                ctx.f_content,
                ctx.f_bold,
                THEME["text"],
                THEME["bold"],
            )
            y += lh
        return y + 2


class _QuoteElem(_Element):
    def __init__(self, lines: list[str]):
        self.text = "\n".join(lines)

    def height(self, ctx: "_Ctx") -> int:
        lines = _wrap_plain(self.text, ctx.f_content, ctx.cw - 18, ctx.draw)
        return len(lines) * _line_height(ctx.f_content) + 12

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        lh = _line_height(ctx.f_content)
        lines = _wrap_plain(self.text, ctx.f_content, ctx.cw - 18, ctx.draw)
        h = len(lines) * lh
        ctx.draw.line(
            [(x + 4, y + 2), (x + 4, y + h + 6)], fill=THEME["quote_bar"], width=3
        )
        ty = y + 4
        for line in lines:
            ctx.draw.text(
                (x + 14, ty), line, font=ctx.f_content, fill=THEME["quote_text"]
            )
            ty += lh
        return y + h + 12


class _CodeElem(_Element):
    def __init__(self, lines: list[str]):
        self.code = "\n".join(lines)

    def height(self, ctx: "_Ctx") -> int:
        code_lines = self.code.split("\n")
        wrapped: list[str] = []
        for ln in code_lines:
            wrapped.extend(_wrap_plain(ln or " ", ctx.f_code, ctx.cw - 24, ctx.draw))
        return len(wrapped) * (ctx.f_code.size + 5) + 20

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        code_lines = self.code.split("\n")
        wrapped: list[str] = []
        for ln in code_lines:
            wrapped.extend(_wrap_plain(ln or " ", ctx.f_code, ctx.cw - 24, ctx.draw))
        ch = len(wrapped) * (ctx.f_code.size + 5)
        ctx.draw.rounded_rectangle(
            [x, y + 2, x + ctx.cw, y + ch + 18], radius=6, fill=THEME["code_bg"]
        )
        ty = y + 9
        for line in wrapped:
            ctx.draw.text((x + 12, ty), line, font=ctx.f_code, fill=THEME["code_text"])
            ty += ctx.f_code.size + 5
        return y + ch + 22


class _GapElem(_Element):
    def height(self, ctx: "_Ctx") -> int:
        return 6

    def render(self, ctx: "_Ctx", x: int, y: int) -> int:
        return y + 6


class _Section:
    """一个面板区块 = 可选标题 + 多个元素"""

    def __init__(self, title: str = "", elements: list[_Element] | None = None):
        self.title = title
        self.elements = elements or []


def _parse_to_sections(text: str) -> list[_Section]:
    """将 Markdown 文本解析为 Section 列表"""
    sections: list[_Section] = []
    current_title = ""
    current_elems: list[_Element] = []
    lines = text.split("\n")
    i = 0
    quote_buf: list[str] = []

    def flush_quotes():
        nonlocal quote_buf
        if quote_buf:
            current_elems.append(_QuoteElem(quote_buf))
            quote_buf = []

    def push_section():
        nonlocal current_title, current_elems
        if current_elems:
            sections.append(_Section(current_title, current_elems))
        current_title = ""
        current_elems = []

    while i < len(lines):
        line = lines[i]

        # 代码块
        if _RE_CODE_FENCE.match(line.strip()):
            flush_quotes()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _RE_CODE_FENCE.match(lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            i += 1
            current_elems.append(_CodeElem(code_lines))
            continue

        # 引用
        m = _RE_QUOTE.match(line)
        if m:
            quote_buf.append(m.group(1))
            i += 1
            continue
        else:
            flush_quotes()

        # 标题 → 开始新 Section
        m = _RE_HEADER.match(line)
        if m:
            push_section()
            current_title = m.group(2).strip()
            i += 1
            continue

        # 无序列表
        m = _RE_BULLET.match(line)
        if m:
            current_elems.append(_BulletElem(m.group(1)))
            i += 1
            continue

        # 有序列表
        m = _RE_NUMBERED.match(line)
        if m:
            current_elems.append(_BulletElem(m.group(2), marker=f"{m.group(1)}."))
            i += 1
            continue

        # 空行
        if not line.strip():
            current_elems.append(_GapElem())
            i += 1
            continue

        # 普通文本
        current_elems.append(_TextElem(line))
        i += 1

    flush_quotes()
    push_section()
    return sections


# ─── 渲染上下文 ─────────────────────────────────────────────


class _Ctx:
    def __init__(self, width: int = 800, margin: int = 30, panel_pad: int = 20):
        self.width = width
        self.margin = margin
        self.panel_pad = panel_pad
        self.cw = width - margin * 2 - panel_pad * 2  # 内容宽度

        self.f_header = _get_font(bold=True, size=24)
        self.f_section = _get_font(bold=True, size=20)
        self.f_content = _get_font(bold=False, size=18)
        self.f_bold = _get_font(bold=True, size=18)
        self.f_code = _get_font(bold=False, size=15)
        self.f_ui = _get_font(bold=False, size=13)
        self.f_source = _get_font(bold=False, size=14)

        self._dummy = Image.new("RGB", (1, 1))
        self.draw = ImageDraw.Draw(self._dummy)

    def create_canvas(self, height: int) -> None:
        self.img = Image.new("RGB", (self.width, height), color=THEME["bg"])
        self.draw = ImageDraw.Draw(self.img)


# ─── 面板高度预计算 ─────────────────────────────────────────


def _section_content_height(sec: _Section, ctx: _Ctx) -> int:
    h = 0
    if sec.title:
        h += _line_height(ctx.f_section) + 8
    for elem in sec.elements:
        h += elem.height(ctx)
    return h


def _section_panel_height(sec: _Section, ctx: _Ctx) -> int:
    return _section_content_height(sec, ctx) + ctx.panel_pad * 2


# ─── 来源区域 ───────────────────────────────────────────────


def _sources_panel_height(sources: list[dict[str, str]], ctx: _Ctx) -> int:
    if not sources:
        return 0
    h = 30
    for src in sources:
        title = src.get("title", "")
        url = src.get("url", "")
        display = title or url
        lines = _wrap_plain(display, ctx.f_source, ctx.cw - 24, ctx.draw)
        h += len(lines) * (ctx.f_source.size + 5)
        if title and url:
            url_lines = _wrap_plain(url, ctx.f_source, ctx.cw - 24, ctx.draw)
            h += len(url_lines) * (ctx.f_source.size + 4)
        h += 4
    return h + ctx.panel_pad * 2


def _render_sources_panel(sources: list[dict[str, str]], ctx: _Ctx, y: int) -> int:
    if not sources:
        return y
    panel_h = _sources_panel_height(sources, ctx)
    ctx.draw.rounded_rectangle(
        [ctx.margin, y, ctx.width - ctx.margin, y + panel_h],
        radius=8,
        fill=THEME["source_panel"],
        outline=THEME["panel_border"],
        width=1,
    )
    tx = ctx.margin + ctx.panel_pad
    ty = y + ctx.panel_pad
    ctx.draw.text((tx, ty), "REFERENCE SOURCES //", font=ctx.f_ui, fill=THEME["accent"])
    ty += 22

    for i, src in enumerate(sources, 1):
        title = src.get("title", "")
        url = src.get("url", "")
        display = title or url
        idx = f"{i}."
        ctx.draw.text((tx, ty), idx, font=ctx.f_source, fill=THEME["source_idx"])
        iw = _text_width(idx + " ", ctx.f_source, ctx.draw)
        for line in _wrap_plain(display, ctx.f_source, ctx.cw - iw - 8, ctx.draw):
            color = THEME["text"] if title else THEME["link"]
            ctx.draw.text((tx + iw + 2, ty), line, font=ctx.f_source, fill=color)
            ty += ctx.f_source.size + 5
        if title and url:
            for line in _wrap_plain(url, ctx.f_source, ctx.cw - iw - 8, ctx.draw):
                ctx.draw.text(
                    (tx + iw + 2, ty), line, font=ctx.f_source, fill=THEME["link"]
                )
                ty += ctx.f_source.size + 4
        ty += 2

    return y + panel_h


# ─── 公开 API ───────────────────────────────────────────────


def render_search_card(
    content: str,
    sources: list[dict[str, str]] | None = None,
    model: str = "",
    elapsed_ms: int = 0,
    total_tokens: int = 0,
    width: int = 800,
    output_path: str | None = None,
    theme: str = "auto",
) -> str | bytes:
    """将搜索结果渲染为面板风格卡片图片

    Args:
        content:      搜索结果正文（支持 Markdown 子集）
        sources:      来源列表 [{url, title, snippet}]（不传则不渲染来源区域）
        model:        模型名称
        elapsed_ms:   耗时毫秒
        total_tokens: token 用量
        width:        图片宽度
        output_path:  保存路径；None 时返回 PNG bytes
        theme:        'auto'(按时间自动) / 'dark' / 'light'

    Returns:
        文件路径 str 或 PNG bytes
    """
    global THEME
    THEME = _get_theme(theme)
    sources = sources or []
    ctx = _Ctx(width=width)
    sections = _parse_to_sections(content)

    # ── 预计算总高度 ──
    header_h = 55
    gap = 12

    total_h = ctx.margin + header_h
    for sec in sections:
        total_h += _section_panel_height(sec, ctx) + gap

    if sources:
        total_h += _sources_panel_height(sources, ctx) + gap

    footer_h = 35
    total_h += footer_h + ctx.margin

    # ── 正式绘制 ──
    ctx.create_canvas(total_h)
    y = ctx.margin

    # 1) 顶部 Header
    ctx.draw.text(
        (ctx.margin, y),
        "[ GROK_DATA_STREAM :: SEARCH ]",
        font=ctx.f_ui,
        fill=THEME["dim"],
    )
    status = "SYS.STATUS: ONLINE"
    sw = _text_width(status, ctx.f_ui, ctx.draw)
    ctx.draw.text(
        (ctx.width - ctx.margin - sw, y), status, font=ctx.f_ui, fill=THEME["accent"]
    )
    y += 22
    ctx.draw.line(
        [(ctx.margin, y), (ctx.width - ctx.margin, y)],
        fill=THEME["panel_border"],
        width=2,
    )
    y += header_h - 22

    # 2) 内容面板
    for sec in sections:
        panel_h = _section_panel_height(sec, ctx)
        ctx.draw.rounded_rectangle(
            [ctx.margin, y, ctx.width - ctx.margin, y + panel_h],
            radius=8,
            fill=THEME["panel"],
            outline=THEME["panel_border"],
            width=1,
        )
        tx = ctx.margin + ctx.panel_pad
        ty = y + ctx.panel_pad

        if sec.title:
            bar_h = ctx.f_section.size
            ctx.draw.rectangle([tx, ty + 3, tx + 4, ty + bar_h], fill=THEME["accent"])
            ctx.draw.text(
                (tx + 12, ty), sec.title, font=ctx.f_section, fill=THEME["text"]
            )
            ty += _line_height(ctx.f_section) + 8

        for elem in sec.elements:
            ty = elem.render(ctx, tx, ty)

        y += panel_h + gap

    # 3) 来源面板
    if sources:
        y = _render_sources_panel(sources, ctx, y)
        y += gap

    # 4) 页脚
    y += 2
    if model:
        ctx.draw.text(
            (ctx.margin, y), f"MODEL :: {model}", font=ctx.f_ui, fill=THEME["dim"]
        )
    meta_parts = []
    if elapsed_ms:
        meta_parts.append(f"{elapsed_ms / 1000:.1f}s")
    if total_tokens:
        meta_parts.append(f"{total_tokens} tokens")
    if meta_parts:
        mt = " · ".join(meta_parts)
        mw = _text_width(mt, ctx.f_ui, ctx.draw)
        ctx.draw.text(
            (ctx.width - ctx.margin - mw, y), mt, font=ctx.f_ui, fill=THEME["dim"]
        )

    # ── 输出 ──
    if output_path:
        ctx.img.save(output_path)
        return output_path

    buf = BytesIO()
    ctx.img.save(buf, format="PNG")
    return buf.getvalue()
