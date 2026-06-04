"""Protocols for controlled Excel workbook access."""

from backend.quote.excel_protocol.chunk import Chunk, ExcelChunkProtocol
from backend.quote.excel_protocol.read import Cell, ExcelReadProtocol

__all__ = ["Cell", "Chunk", "ExcelReadProtocol", "ExcelChunkProtocol"]
