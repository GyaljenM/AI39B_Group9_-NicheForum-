"""Helpers for the security-question password-recovery flow.

The security *answer* is hashed with bcrypt (per the recovery feature spec).
This is deliberately separate from account passwords, which stay on Werkzeug's
``generate_password_hash`` / ``check_password_hash`` (see AuthController.login) —
mixing the two would break login.
"""

import hashlib
import bcrypt

# Preset questions offered at signup. The signup form also lets users write a
# custom question; these are the ready-made choices.
SECURITY_QUESTIONS = [
    "What was your first pet's name?",
    "What is your mother's maiden name?",
    "What was the name of your first school?",
    "What city were you born in?",
    "What was the make of your first car?",
]


def normalize_answer(raw):
    """Normalize an answer before hashing/comparison: trim + lowercase.

    Keeps recovery forgiving of incidental casing/whitespace differences while
    staying deterministic, so the same answer always maps to the same hash input.
    """
    return (raw or "").strip().lower()


def hash_answer(raw):
    """Return a bcrypt hash of the normalized answer (utf-8 str)."""
    normalized = normalize_answer(raw).encode("utf-8")
    return bcrypt.hashpw(normalized, bcrypt.gensalt()).decode("utf-8")


def verify_answer(raw, answer_hash):
    """Return True iff ``raw`` matches the stored bcrypt ``answer_hash``.

    Safe against a missing/garbage hash (returns False rather than raising), so
    callers can treat "no question on file" and "wrong answer" identically.
    """
    if not answer_hash:
        return False
    try:
        return bcrypt.checkpw(
            normalize_answer(raw).encode("utf-8"),
            answer_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def decoy_question(email):
    """Pick a stable, plausible question for an email with no question on file.

    Used so the forgot-password flow shows a question for *every* submitted
    email — including unknown ones — without revealing whether the account
    exists. The choice is deterministic per email so repeat visits look
    consistent. A decoy never has a stored hash, so any answer fails.
    """
    digest = hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()
    return SECURITY_QUESTIONS[int(digest, 16) % len(SECURITY_QUESTIONS)]
