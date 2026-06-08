import re

class WordCensor:
    """Utility class for censoring inappropriate words in user content."""
    
    # List of words to censor (add more as needed)
    BANNED_WORDS = [
        # Add your banned words here
        # Example format: "badword"
        # You can customize this list based on your requirements
    ]
    
    # Default censoring character
    CENSOR_CHAR = "*"
    
    @staticmethod
    def censor_text(text, banned_words=None, censor_char="*"):
        """
        Censor inappropriate words in text.
        
        Args:
            text (str): The text to censor
            banned_words (list): List of words to censor. If None, uses default BANNED_WORDS
            censor_char (str): Character to use for censoring (default: "*")
        
        Returns:
            str: The censored text
        """
        if not text:
            return text
        
        if banned_words is None:
            banned_words = WordCensor.BANNED_WORDS
        
        if not banned_words:
            return text
        
        censored_text = text
        
        # Case-insensitive censoring while preserving case in replacement length
        for word in banned_words:
            # Create a pattern that matches the word with word boundaries
            # Use re.IGNORECASE for case-insensitive matching
            pattern = r'\b' + re.escape(word) + r'\b'
            
            # Replace with asterisks of the same length
            def replace_func(match):
                return censor_char * len(match.group(0))
            
            censored_text = re.sub(pattern, replace_func, censored_text, flags=re.IGNORECASE)
        
        return censored_text
    
    @staticmethod
    def add_banned_word(word):
        """Add a new word to the ban list."""
        if word and word.lower() not in [w.lower() for w in WordCensor.BANNED_WORDS]:
            WordCensor.BANNED_WORDS.append(word.lower())
    
    @staticmethod
    def remove_banned_word(word):
        """Remove a word from the ban list."""
        WordCensor.BANNED_WORDS = [w for w in WordCensor.BANNED_WORDS if w.lower() != word.lower()]
    
    @staticmethod
    def get_banned_words():
        """Get the current list of banned words."""
        return WordCensor.BANNED_WORDS.copy()
