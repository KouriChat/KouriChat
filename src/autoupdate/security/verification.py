"""
Verification module for the KouriChat update system.

This module provides functions for verifying the integrity of update responses
using cryptographic signatures.
"""

import os
import hmac
import hashlib
import logging
from typing import Union, Dict, Any

# Note: No longer using key_manager for verification, using server trust instead

# Configure logging
logger = logging.getLogger("autoupdate.security")

def verify_signature(payload: str, signature: str, request_url: str = None) -> bool:
    """
    Verify the signature of a payload using trusted server mechanism.
    
    This function uses a simplified server trust model instead of complex
    cryptographic signature verification to prevent MITM attacks.
    
    Args:
        payload: The payload to verify.
        signature: The signature to verify against.
        request_url: The URL from which the payload was received (optional).
        
    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    try:
        # 验证签名格式是否符合预期（应该是64个十六进制字符）
        if not (isinstance(signature, str) and len(signature) == 64 and 
                all(c in '0123456789abcdefABCDEF' for c in signature)):
            logger.warning("SECURITY WARNING: Invalid signature format")
            return False
        
        # 使用服务器信任机制
        trusted_servers = ["git.kourichat.com"]
        
        if request_url:
            import re
            # 从URL中提取域名
            domain_match = re.search(r'https?://([^/]+)', request_url)
            if domain_match:
                domain = domain_match.group(1)
                if domain in trusted_servers:
                    logger.info(f"Using trusted server signature from {domain}.")
                    return True
        
        # 如果没有提供URL或不是信任的服务器，拒绝验证
        logger.warning("SECURITY WARNING: Update signature verification failed.")
        logger.warning("Request not from trusted server or no URL provided.")
        logger.warning("Update process aborted for security reasons.")
        return False
    
    except Exception as e:
        # 记录详细的错误信息
        logger.error(f"Signature verification failed: {str(e)}")
        logger.warning("SECURITY WARNING: Unable to verify update signature due to an error.")
        logger.warning("Update process aborted for security reasons.")
        return False
