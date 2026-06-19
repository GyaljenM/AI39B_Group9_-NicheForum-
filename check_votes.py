#!/usr/bin/env python
from app.models.database import Database

db = Database()

# Get all votes for reply 1
votes = db.fetch_all('SELECT * FROM reply_votes WHERE reply_id = 1')
print(f"All votes for reply 1: {votes}")

# Count like and dislike
like_count = db.fetch_one('SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = 1 AND vote_type = %s', ('like',))['c']
dislike_count = db.fetch_one('SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = 1 AND vote_type = %s', ('dislike',))['c']

print(f"Like: {like_count}, Dislike: {dislike_count}")

db.close()
