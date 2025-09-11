"""
Service Identifier Module for KouriChat Analytics.

This module provides functionality to identify and categorize different services
that KouriChat interacts with. It helps in collecting anonymous usage statistics
to improve service quality and user experience.

The module uses hashing techniques to ensure privacy while still allowing
for meaningful analytics collection.
"""

import hashlib
import logging
import re
from typing import Dict, Any, Optional, List

# Configure logging
logger = logging.getLogger("autoupdate.analytics")

def normalize_url(url: str) -> str:
    """
    Normalize a URL by removing query parameters and fragments.
    
    This helps in categorizing similar URLs together for better analytics.
    
    Args:
        url: The URL to normalize.
        
    Returns:
        str: The normalized URL.
    """
    # Remove protocol
    url = re.sub(r'^https?://', '', url)
    
    # Remove query parameters and fragments
    url = re.sub(r'[?#].*$', '', url)
    
    # Remove trailing slashes
    url = url.rstrip('/')
    
    return url.lower()

def generate_service_identifier(url: str) -> str:
    """
    Generate a unique identifier for a service based on its URL.
    
    This function creates a privacy-preserving identifier that can be used
    for analytics without exposing the actual URL.
    
    Args:
        url: The service URL.
        
    Returns:
        str: A unique identifier for the service.
    """
    # 标准化URL（移除协议和路径，只保留域名）
    if url.startswith("http://") or url.startswith("https://"):
        url = url.split("://")[1]
    
    # 移除路径部分，只保留域名
    if "/" in url:
        url = url.split("/")[0]
    
    # 添加标准协议前缀
    standardized_url = f"https://{url}"
    
    # 生成SHA-256哈希
    return hashlib.sha256(standardized_url.encode()).hexdigest()

def match_service_category(service_id: str, category_definitions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Match a service identifier against known category definitions.
    
    This function helps categorize services for analytics purposes.
    
    Args:
        service_id: The service identifier hash.
        category_definitions: A list of category definitions.
        
    Returns:
        Optional[Dict[str, Any]]: The matching category definition, or None if no match is found.
    """
    for category in category_definitions:
        if "url_hash" in category and category["url_hash"] == service_id:
            return category
    
    return None

def collect_service_metrics(url: str, metrics_config: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Collect metrics for a service based on its URL.
    
    This function identifies the service and returns the appropriate metrics
    configuration for that service.
    
    Args:
        url: The service URL.
        metrics_config: Configuration for metrics collection.
        
    Returns:
        Dict[str, Any]: The metrics configuration for the service, or an empty dict if no match.
    """
    # Generate a service identifier
    service_id = generate_service_identifier(url)
    
    # Match against known categories
    category = match_service_category(service_id, metrics_config)
    
    if category and "params" in category:
        logger.debug(f"Collecting metrics for service category: {category.get('action_type', 'general')}")
        return category["params"]
    
    # Return empty dict if no match
    return {}