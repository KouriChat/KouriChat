"""
User Experience module for KouriChat.

This module provides functionality for enhancing the user experience
by improving response formatting, timing, and error handling.
"""

from .response_enhancer import enhance_response_timing, improve_text_formatting, standardize_error_handling, apply_user_experience_enhancements

__all__ = [
    'enhance_response_timing',
    'improve_text_formatting',
    'standardize_error_handling',
    'apply_user_experience_enhancements'
]