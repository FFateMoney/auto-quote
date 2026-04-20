from __future__ import annotations

import re
import uuid
from backend.indexing.models import StandardChunk, StandardMetadata


class MarkdownHeadingSplitter:
    """按 Markdown 标题层级切分文本，并保持标题路径上下文。
    如果某标题下内容超过 max_chunk_bytes，会进一步按大小切分。
    """

    def __init__(self, max_chunk_bytes: int = 500_000) -> None:
        self.max_chunk_bytes = max_chunk_bytes

    def split(self, content: str, file_name: str, standard_id: str) -> list[StandardChunk]:
        chunks = []
        lines = content.splitlines()
        
        # 极致规范化 standard_id: 仅保留小写字母和数字
        normalized_id = re.sub(r'[^a-z0-9]', '', standard_id.lower())
        
        current_headings = [] # 记录当前的标题路径 [H1, H2, H3...]
        current_text_block = []

        # 匹配 #, ##, ### 等标题
        heading_re = re.compile(r"^(#{1,6})\s+(.*)$")

        def _create_chunks_from_text_block(text_block: list[str], headings: list[str]) -> None:
            """将文本块切分成一个或多个chunk（如果内容太大则按大小切分）"""
            if not text_block:
                return

            full_text = "\n".join(text_block).strip()
            if not full_text:
                return

            # 增强语义文本：[H1 > H2 > H3] \n 正文
            heading_context = " > ".join(headings)

            metadata = StandardMetadata(
                standard_id=normalized_id,
                file_name=file_name,
                heading_path=list(headings)
            )

            # 如果内容超过限制，按大小切分
            if len(full_text.encode('utf-8')) > self.max_chunk_bytes:
                # 将text按大小切分成多个部分
                sub_chunks = self._split_text_by_size(full_text)
                for seq_id, sub_text in enumerate(sub_chunks):
                    sub_full_context = f"[{heading_context}]\n{sub_text}" if heading_context else sub_text
                    chunks.append(StandardChunk(
                        id=str(uuid.uuid4()),
                        text=sub_text,
                        full_context_text=sub_full_context,
                        metadata=metadata,
                        sequence_id=seq_id
                    ))
            else:
                # 内容不大，直接创建一个chunk
                full_context_text = f"[{heading_context}]\n{full_text}" if heading_context else full_text
                chunks.append(StandardChunk(
                    id=str(uuid.uuid4()),
                    text=full_text,
                    full_context_text=full_context_text,
                    metadata=metadata,
                    sequence_id=None
                ))

        for line in lines:
            match = heading_re.match(line)
            if match:
                _create_chunks_from_text_block(current_text_block, current_headings)
                level = len(match.group(1))
                title = match.group(2).strip()
                if level <= len(current_headings):
                    current_headings = current_headings[:level-1]
                current_headings.append(title)
                current_text_block.clear()
            else:
                current_text_block.append(line)

        _create_chunks_from_text_block(current_text_block, current_headings)
        return chunks

    def _split_text_by_size(self, text: str) -> list[str]:
        """按大小切分文本，尽量保持段落完整（超大段落继续按行切）"""
        if len(text.encode('utf-8')) <= self.max_chunk_bytes:
            return [text]

        chunks = []
        paragraphs = text.split('\n\n')  # 按段落（空行）分割
        current_chunk = []
        current_size = 0

        for paragraph in paragraphs:
            para_size = len(paragraph.encode('utf-8'))

            # 如果单个paragraph本身就超过限制，按行再切
            if para_size > self.max_chunk_bytes:
                # 先保存当前积累的chunk
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                # 对这个大paragraph继续按行切
                line_chunks = self._split_text_by_lines(paragraph)
                chunks.extend(line_chunks)
            elif current_size + para_size > self.max_chunk_bytes and current_chunk:
                # 加上这个paragraph会超过限制，先保存当前chunk
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_size = para_size
            else:
                # 加上这个paragraph不会超过限制，继续累积
                current_chunk.append(paragraph)
                current_size += para_size + 2  # +2 for '\n\n'

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _split_text_by_lines(self, text: str) -> list[str]:
        """对超大文本按行切分"""
        chunks = []
        lines = text.split('\n')
        current_chunk = []
        current_size = 0

        for line in lines:
            line_size = len(line.encode('utf-8'))
            if current_size + line_size > self.max_chunk_bytes and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size + 1  # +1 for '\n'

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks
