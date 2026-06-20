import re


class WordCensor:
    """Utility class for censoring inappropriate words in user content.

    Matching rules (case-insensitive):
      • A banned single word matches the word *and any letters attached to its
        end*, so "fuck" also censors "fucking", "fucker", "fucks". A word
        boundary is required at the START, so "crap" does NOT censor "scrap"
        and "ass..." doesn't fire inside "class".
      • A banned phrase ("crypto scam") matches across any run of whitespace.
      • Each matched run is replaced character-for-character with CENSOR_CHAR,
        preserving the original length so layout doesn't jump around.
    """

    # Populated at app startup (see app/__init__.py). Safe to leave empty.
    BANNED_WORDS = []

    # Character used to mask matched text.
    CENSOR_CHAR = "*"

    # Cache the compiled regex so we don't rebuild it on every call. Keyed on a
    # snapshot of the word list so add/remove_banned_word transparently rebuild.
    _compiled = None
    _compiled_signature = None

    @staticmethod
    def _build_pattern(banned_words, ignore_case=True):
        """Compile the banned-word list into one alternation regex (or None)."""
        parts = []
        for raw in banned_words:
            word = (raw or "").strip()
            if not word:
                continue
            if re.search(r"\s", word):
                # Phrase: escape each token, allow flexible whitespace between.
                tokens = [re.escape(t) for t in word.split()]
                parts.append(r"\b" + r"\s+".join(tokens) + r"\b")
            else:
                # Single word: boundary at the start, then the word + any
                # trailing word characters (suffixes/inflections).
                parts.append(r"\b" + re.escape(word) + r"\w*")
        if not parts:
            return None
        flags = re.IGNORECASE if ignore_case else 0
        return re.compile("|".join(parts), flags)

    @classmethod
    def _get_pattern(cls, banned_words):
        """Return a compiled pattern for `banned_words`, rebuilding only when
        the word list changed since the last call."""
        signature = tuple(banned_words)
        if cls._compiled_signature != signature:
            cls._compiled = cls._build_pattern(banned_words)
            cls._compiled_signature = signature
        return cls._compiled

    @staticmethod
    def censor_text(text, banned_words=None, censor_char=None):
        """Censor banned words/phrases in `text` and return the result.

        Empty/whitespace-only text, an empty ban list, or a None text are
        returned unchanged. Matching is case-insensitive.
        """
        if not text:
            return text

        if banned_words is None:
            banned_words = WordCensor.BANNED_WORDS
        if not banned_words:
            return text

        if censor_char is None:
            censor_char = WordCensor.CENSOR_CHAR

        # Use the cached pattern when censoring against the default list;
        # otherwise build a one-off pattern for the custom list.
        if banned_words is WordCensor.BANNED_WORDS:
            pattern = WordCensor._get_pattern(banned_words)
        else:
            pattern = WordCensor._build_pattern(banned_words)
        if pattern is None:
            return text

        return pattern.sub(lambda m: censor_char * len(m.group(0)), text)

    @staticmethod
    def contains_banned_word(text, banned_words=None):
        """True if `text` contains any banned word/phrase (case-insensitive)."""
        if not text:
            return False
        if banned_words is None:
            banned_words = WordCensor.BANNED_WORDS
        if not banned_words:
            return False
        if banned_words is WordCensor.BANNED_WORDS:
            pattern = WordCensor._get_pattern(banned_words)
        else:
            pattern = WordCensor._build_pattern(banned_words)
        return bool(pattern and pattern.search(text))

    @staticmethod
    def add_banned_word(word):
        """Add a new word to the ban list (no duplicates, case-insensitive)."""
        if word and word.lower() not in [w.lower() for w in WordCensor.BANNED_WORDS]:
            WordCensor.BANNED_WORDS.append(word.lower())

    @staticmethod
    def remove_banned_word(word):
        """Remove a word from the ban list."""
        WordCensor.BANNED_WORDS = [
            w for w in WordCensor.BANNED_WORDS if w.lower() != word.lower()
        ]

    @staticmethod
    def get_banned_words():
        """Get the current list of banned words."""
        return WordCensor.BANNED_WORDS.copy()
