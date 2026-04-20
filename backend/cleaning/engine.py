from __future__ import annotations

import re
from bs4 import BeautifulSoup, Tag
from backend.cleaning.models import CleaningOptions, CleaningResult, CleaningStats


class MarkdownCleaner:
    def __init__(self, options: CleaningOptions | None = None) -> None:
        self.options = options or CleaningOptions()

    def clean(self, raw_md: str) -> CleaningResult:
        stats = CleaningStats()
        
        # 1. BeautifulSoup 阶段：处理 HTML 结构
        soup = BeautifulSoup(raw_md, "lxml")
        
        # 处理表格 (关键逻辑)
        if self.options.fix_tables:
            stats.fixed_tables = self._process_tables(soup)
        
        # 解包垃圾标签 (OCR 误识别的标签)
        stats.removed_tags = self._unwrap_garbage(soup)
        
        # 获取初步文本
        # 注意：soup.get_text() 可能会丢失一些 Markdown 换行特性，
        # 但由于原始输入本身就是混杂了 HTML 的 MD，我们需要小心处理。
        # 我们主要处理的是 <table> 和 <div> 等块状元素。
        cleaned_text = self._soup_to_md(soup)

        # 2. Regex 阶段：纯文本降噪
        if self.options.remove_cid:
            cleaned_text, count = self._remove_cid(cleaned_text)
            stats.removed_cids = count
            
        if self.options.fix_hyphens:
            cleaned_text, count = self._fix_hyphens(cleaned_text)
            stats.fixed_hyphens = count
            
        if self.options.normalize_whitespace:
            cleaned_text = self._normalize_whitespace(cleaned_text)

        return CleaningResult(cleaned_content=cleaned_text, stats=stats)

    def _process_tables(self, soup: BeautifulSoup) -> int:
        count = 0
        for table in soup.find_all("table"):
            md_table = self._table_to_markdown(table)
            # 将 <table> 替换为生成的 Markdown 字符串文本节点
            table.replace_with(md_table)
            count += 1
        return count

    def _table_to_markdown(self, table: Tag) -> str:
        """将 HTML 表格转换为标准 Markdown 表格，并处理 colspan/rowspan。"""
        rows = table.find_all("tr")
        if not rows:
            return ""

        # 1. 预计算网格尺寸
        grid: dict[tuple[int, int], str] = {}
        max_col = 0
        
        for r_idx, tr in enumerate(rows):
            c_idx = 0
            for td in tr.find_all(["td", "th"]):
                # 寻找下一个空闲列
                while (r_idx, c_idx) in grid:
                    c_idx += 1
                
                rowspan = int(td.get("rowspan", 1))
                colspan = int(td.get("colspan", 1))
                content = td.get_text(strip=True).replace("|", "\\|") # 转义 MD 表格分隔符
                
                # 填充网格 (Cell Expansion)
                for r in range(r_idx, r_idx + rowspan):
                    for c in range(c_idx, c_idx + colspan):
                        grid[(r, c)] = content
                
                c_idx += colspan
                max_col = max(max_col, c_idx)
        
        if not grid:
            return ""

        # 2. 生成 Markdown 文本
        total_rows = len(rows)
        lines = []
        
        for r in range(total_rows):
            row_cells = [grid.get((r, c), "") for c in range(max_col)]
            lines.append(f"| {' | '.join(row_cells)} |")
            
            # 如果是第一行（假设为表头），添加分隔线
            if r == 0:
                sep = ["---"] * max_col
                lines.append(f"| {' | '.join(sep)} |")
                
        return "\n" + "\n".join(lines) + "\n"

    def _unwrap_garbage(self, soup: BeautifulSoup) -> int:
        """剥离所有 OCR 误识别的非标准标签，保留其内部文本。"""
        count = 0
        # 定义一些常见的 OCR 误识别或不需要的样式标签
        # 1. 移除 style 属性
        for tag in soup.find_all(True):
            if tag.has_attr("style"):
                tag.attrs.pop("style", None)
        
        # 2. 解包所有非标准标签（简单判断：不在常见 HTML 标签列表中）
        # 这里我们可以更激进一点，解包除了 table/tr/td/th/img 之外的大多数标签
        # 因为我们最终想要的是纯 MD。
        preserved = {"table", "tr", "td", "th", "img", "br", "p", "h1", "h2", "h3", "h4", "h5", "h6"}
        for tag in soup.find_all(True):
            if tag.name not in preserved:
                tag.unwrap()
                count += 1
        return count

    def _soup_to_md(self, soup: BeautifulSoup) -> str:
        """从 BeautifulSoup 对象中提取文本，尽量保留结构。"""
        # 由于我们已经把 table 替换成了字符串，这里 get_text 比较安全
        return soup.get_text()

    def _remove_cid(self, text: str) -> tuple[str, int]:
        pattern = re.compile(r"\(cid:\d+\)")
        new_text, count = pattern.subn("", text)
        return new_text, count

    def _fix_hyphens(self, text: str) -> tuple[str, int]:
        # 匹配 单词- 换行 单词 的情况
        pattern = re.compile(r"(\w+)-\s*\n\s*(\w+)")
        new_text, count = pattern.subn(r"\1\2", text)
        return new_text, count

    def _normalize_whitespace(self, text: str) -> str:
        # 1. 压缩连续换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 2. 移除行末空格
        text = "\n".join(line.rstrip() for line in text.splitlines())
        return text.strip()
