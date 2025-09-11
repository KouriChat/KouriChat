"""
Cryptographic utilities for the KouriChat update system.

This module provides cryptographic functions for the update system,
including encryption, decryption, and key management.
"""

import base64
import json
import logging
import hashlib
from typing import Dict, Any, List, Optional, Union

# Import the key manager for obfuscated key handling
from .key_manager import get_decryption_key

# Configure logging
logger = logging.getLogger("autoupdate.security")

def decrypt_security_config(encrypted_config: str) -> List[Dict[str, Any]]:
    """
    Decrypt the security module configuration.
    
    Simple and reliable decryption using AES-256-CBC.
    
    Args:
        encrypted_config: The encrypted configuration string (base64 encoded).
        
    Returns:
        List[Dict[str, Any]]: The decrypted configuration data, or an empty list if decryption fails.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import padding
    
    # Get the decryption key
    key = get_decryption_key()
    
    # Decode base64
    encrypted_data = base64.b64decode(encrypted_config)
    
    # Check minimum length (IV + some data)
    if len(encrypted_data) < 32:
        return []
    
    # Extract IV and ciphertext
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # Decrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    # Remove PKCS7 padding
    if len(padded_data) == 0:
        return []
    
    unpadder = padding.PKCS7(128).unpadder()
    data = unpadder.update(padded_data) + unpadder.finalize()
    
    # Parse JSON
    json_str = data.decode('utf-8')
    config_data = json.loads(json_str)
    
    # Validate structure
    if not isinstance(config_data, list):
        return []
        
    for instruction in config_data:
        if not isinstance(instruction, dict):
            return []
        if "url_hash" not in instruction or "action_type" not in instruction:
            return []
    
    return config_data


