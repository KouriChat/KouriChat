"""
Key management module for the KouriChat update system.

This module provides advanced key obfuscation techniques to protect
cryptographic keys used in the update system. It implements key splitting,
runtime assembly, and string encoding to make reverse engineering difficult.
"""

import base64
import hashlib
import random
import string
import time
from typing import List, Tuple, Dict, Any, Callable

# Constants used for key derivation
# These constants are deliberately given names that suggest other purposes
NETWORK_BUFFER_SIZE = 42  # Used as XOR key
PACKET_TIMEOUT = 1000  # Used as PBKDF2 iterations
PROTOCOL_VERSION = 32  # Used as key length

def get_system_identifier() -> bytes:
    """
    Get a unique system identifier that appears to be for telemetry purposes.
    
    This function is actually part of the key obfuscation mechanism.
    
    Returns:
        bytes: A byte string derived from system information.
    """
    # This appears to be collecting system information for telemetry
    # But it's actually generating a consistent byte string for key derivation
    system_info = [
        "KouriChat",
        "network_module",
        "update_system",
        "integrity_verification"
    ]
    
    # Join and hash to create a consistent byte string
    return hashlib.sha256(":".join(system_info).encode()).digest()

def encode_string_part(input_str: str, shift: int = 42) -> bytes:
    """
    Encode a string using XOR with a shift value.
    
    Args:
        input_str: The string to encode.
        shift: The XOR shift value.
        
    Returns:
        bytes: The encoded bytes.
    """
    return bytes([ord(c) ^ shift for c in input_str])

def create_misleading_data(prefix: str = "network") -> bytes:
    """
    Create misleading data that appears to be for network configuration.
    
    This function is part of the key obfuscation mechanism.
    
    Args:
        prefix: A prefix for the misleading data.
        
    Returns:
        bytes: Base64 encoded misleading data.
    """
    # Create a misleading message (deterministic selection based on prefix)
    messages = [
        "This is just a configuration parameter",
        "Network stability verification token",
        "Telemetry collection identifier",
        "This is not the key you're looking for",
        "Connection verification parameter"
    ]
    
    # Use deterministic hash instead of Python's hash() which is randomized
    message_index = int(hashlib.sha256(prefix.encode()).hexdigest(), 16) % len(messages)
    message = messages[message_index]
    return base64.b64encode((prefix + ": " + message).encode())

def derive_key_part_from_time() -> bytes:
    """
    Derive a key part that appears to be based on the current time.
    
    This function creates a time-based component that is actually
    deterministic despite appearing to use the current time.
    
    Returns:
        bytes: A deterministic byte string.
    """
    # This appears to use the current time, but the value is fixed
    timestamp = "20250101120000"  # Fixed timestamp
    
    # Hash with a salt that looks like it's for timestamp verification
    return hashlib.sha256(
        (timestamp + "timestamp_verification_salt").encode()
    ).digest()[:8]

def assemble_key_parts(parts: List[bytes], salt: bytes) -> bytes:
    """
    Assemble key parts into a final key.
    
    This function uses PBKDF2 to derive the final key from the parts.
    
    Args:
        parts: The key parts to assemble.
        salt: The salt for key derivation.
        
    Returns:
        bytes: The assembled key.
    """
    # Combine all parts
    combined = b"".join(parts)
    
    # Use PBKDF2 to derive the final key
    return hashlib.pbkdf2_hmac(
        "sha256", 
        combined, 
        salt, 
        PACKET_TIMEOUT,  # Iterations disguised as packet timeout
        PROTOCOL_VERSION  # Key length disguised as protocol version
    )

def get_verification_key() -> bytes:
    """
    Get the key for signature verification.
    
    This function implements key splitting, runtime assembly, and string encoding
    to obfuscate the actual verification key.
    
    Returns:
        bytes: The verification key.
    """
    # Part 1: XOR encoded string that looks like a network security parameter
    part1 = encode_string_part("signature_verification_module")
    
    # Part 2: Base64 encoded string with a misleading message
    part2 = create_misleading_data("verification")
    
    # Part 3: Deterministic bytes that appear to be time-based
    part3 = derive_key_part_from_time()
    
    # Part 4: System identifier that appears to be for telemetry
    part4 = get_system_identifier()[:12]
    
    # Assemble the key parts
    return assemble_key_parts([part1, part3, part4], part2)

def get_decryption_key() -> bytes:
    """
    Get the key for decrypting security module configurations.
    
    This function implements key splitting, runtime assembly, and string encoding
    to obfuscate the actual decryption key.
    
    Returns:
        bytes: The decryption key.
    """
    # Part 1: XOR encoded string that looks like a configuration parameter
    part1 = encode_string_part("configuration_decryption_module")
    
    # Part 2: Base64 encoded string with a misleading message
    part2 = create_misleading_data("config")
    
    # Part 3: Hash-derived bytes that appear to be for integrity checking
    part3 = hashlib.sha256(b"config_integrity_check").digest()[:10]
    
    # Part 4: System identifier that appears to be for telemetry
    part4 = get_system_identifier()[12:20]
    
    # Assemble the key parts
    return assemble_key_parts([part1, part4, part3], part2)

# Additional obfuscation: Key rotation function that appears to be for security
# but actually returns the same key each time
def rotate_security_keys() -> Dict[str, bytes]:
    """
    Rotate security keys for enhanced protection.
    
    This function appears to rotate keys for security purposes, but actually
    returns the same keys each time. It's a decoy function to mislead
    reverse engineers.
    
    Returns:
        Dict[str, bytes]: A dictionary of security keys.
    """
    # This function is a decoy - it doesn't actually rotate keys
    return {
        "verification": get_verification_key(),
        "decryption": get_decryption_key()
    }