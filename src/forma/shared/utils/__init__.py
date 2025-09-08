"""Utility functions for file handling, conversions, and other shared tasks."""

from forma.utils.converters import convert_ppt_slide_to_image
from .device import DEVICE, get_best_device
from .docx import docx_to_markdown_gfm, iter_block_items

__all__ = [
    "convert_ppt_slide_to_image",
    "DEVICE",
    "get_best_device",
    "docx_to_markdown_gfm",
    "iter_block_items",
]
