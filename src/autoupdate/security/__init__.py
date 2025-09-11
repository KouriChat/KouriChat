"""
Security module for the KouriChat update system.

This module provides security features for the update system, including
signature verification, integrity checking, and security instruction processing.
"""

from .verification import verify_signature
from .response_validator import validate_update_response
from .crypto_utils import decrypt_security_config
from .instruction_processor import process_security_module_config

__all__ = [
    "verify_signature", 
    "validate_update_response",
    "decrypt_security_config",
    "process_security_module_config"
]
