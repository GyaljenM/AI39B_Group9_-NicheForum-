"""Pytest configuration for the NicheForum test-suite.

A handful of files under ``tests/`` are not automated unit tests at all — they
are interactive diagnostic / utility scripts that were moved into this folder.
They open live MySQL connections, talk to Gmail's SMTP server, or hit the
football-data.org API using hard-coded credentials, and several expect to be run
as ``python <script>.py`` from the project root (some even call ``input()``).

They can never pass in an offline, deterministic ``pytest`` run, so we exclude
them from collection here rather than letting pytest treat their ``test_*``
helper functions and module-level side effects as failures.
"""

collect_ignore = [
    "test_email_debug.py",      # interactive SMTP connection check (calls input())
    "test_full_verification.py",  # live MySQL insert + real email send
    "test_live_scores.py",      # hits football-data.org over the network
    "test_user_create.py",      # writes a real row into the users table
    "test_verification.py",     # standalone Flask app + live MySQL/SMTP demo
]
