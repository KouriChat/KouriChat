"""
Hash generator for the KouriChat update system.

This module provides functions for generating hashes of API URLs.
It is intended for testing and demonstration purposes only.
"""

import hashlib
import sys

def generate_url_hash(url: str) -> str:
    """
    Generate a SHA-256 hash of a URL.
    
    Args:
        url: The URL to hash.
        
    Returns:
        str: The hexadecimal hash of the URL.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()

if __name__ == "__main__":
    # Check if a URL was provided as a command-line argument
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Use a default URL
        url = "https://api.competitor-service.com/v1/chat/completions"
    
    # Generate the hash
    url_hash = generate_url_hash(url)
    
    # Print the result
    print(f"URL: {url}")
    print(f"Hash: {url_hash}")

