from .basemodel import BaseModel
from .database import Database

class User(BaseModel):
    @property
    def table(self):
        return "users"

    def create(self, name, username, email, password, role="user"):
        db = Database()
        db.execute(
            f"INSERT INTO {self.table} (name, username, email, password, role) VALUES (%s, %s, %s, %s, %s)",
            (name, username, email, password, role),
        )
        db.close()

    def update_profile(self, user_id, name, username, bio, profile_picture=None):
        db = Database()
        if profile_picture:
            db.execute(
                f"UPDATE {self.table} SET name = %s, username = %s, bio = %s, profile_picture = %s WHERE id = %s",
                (name, username, bio, profile_picture, user_id),
            )
        else:
            db.execute(
                f"UPDATE {self.table} SET name = %s, username = %s, bio = %s WHERE id = %s",
                (name, username, bio, user_id),
            )
        db.close()
