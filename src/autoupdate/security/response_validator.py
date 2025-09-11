"""
Response validator module for the KouriChat update system.

This module provides functions for validating update responses from the cloud API
and processing security module configurations to ensure update integrity.
"""

import json
import logging
import base64
from typing import Dict, Any, Optional, Union
from .verification import verify_signature
from .instruction_processor import process_security_module_config

# Configure logging
logger = logging.getLogger("autoupdate.security")

class ValidationError(Exception):
    """Exception raised when validation fails."""
    pass

def validate_update_response(response_data: Dict[str, Any], request_url: str = None) -> Dict[str, Any]:
    """
    Validate an update response from the cloud API.
    
    Args:
        response_data: The response data to validate.
        request_url: The URL from which the response was received (optional).
        
    Returns:
        Dict[str, Any]: The validated and decoded payload.
        
    Raises:
        ValidationError: If validation fails.
    """
    try:
        # Extract payload and signature
        if "payload" not in response_data or "signature" not in response_data:
            raise ValidationError("Invalid response format: missing payload or signature")
        
        payload_b64 = response_data["payload"]
        signature = response_data["signature"]
        
        # Verify signature
        if not verify_signature(payload_b64, signature, request_url):
            raise ValidationError("Signature verification failed")
        
        # Decode payload
        try:
            payload_json = base64.b64decode(payload_b64).decode("utf-8")
            payload = json.loads(payload_json)
        except Exception as e:
            raise ValidationError(f"Failed to decode payload: {str(e)}")
        
        # Validate payload structure
        if "version_info" not in payload:
            raise ValidationError("Invalid payload structure: missing version_info")
        
        # Note: security_module_config processing is handled by the manager
        # to ensure proper integration with the network optimization system
        
        # Return the decoded payload
        return payload
    
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        raise
    
    except Exception as e:
        logger.error(f"Unexpected error during validation: {str(e)}")
        raise ValidationError(f"Validation failed: {str(e)}")
