from flask import Blueprint, request, redirect, url_for, session, flash, render_template
from app.models.database import Database
from app.utils.word_censor import WordCensor

class ThreadRoutes:
    def __init__(self):
        self.bp = Blueprint("Thread", __name__)

    def register(self):
        self.bp.route("/create-thread", methods=["POST"])(self.create_thread)
        self.bp.route("/community/<category_name>")(self.view_community)
        self.bp.route("/thread/<int:thread_id>")(self.view_thread)
        self.bp.route("/thread/<int:thread_id>/reply", methods=["POST"])(self.post_reply)
        self.bp.route("/thread/<int:thread_id>/vote", methods=["POST"])(self.vote_thread)
        self.bp.route("/thread/delete/<int:thread_id>", methods=["POST"])(self.delete_thread)
        return self.bp

    def delete_thread(self, thread_id):
        # Basic author check
        author = session.get("user_name", "Guest")
        try:
            db = Database()
            # Verify author before deleting
            thread = db.fetch_one("SELECT author FROM threads WHERE id = %s", (thread_id,))
            if thread and thread['author'] == author:
                # Replies will be deleted automatically due to ON DELETE CASCADE
                db.execute("DELETE FROM threads WHERE id = %s", (thread_id,))
            db.close()
        except Exception as e:
            print(f"Error deleting thread: {e}")
        
        return redirect(request.referrer or url_for("Home.home"))

    def vote_thread(self, thread_id):
        action = request.json.get("action")
        # In a real app, we'd track per-user votes in a separate table.
        # For now, we'll just increment/decrement the count.
        try:
            db = Database()
            if action == "up":
                db.execute("UPDATE threads SET votes = votes + 1 WHERE id = %s", (thread_id,))
            elif action == "down":
                db.execute("UPDATE threads SET votes = votes - 1 WHERE id = %s", (thread_id,))
            
            new_votes = db.fetch_one("SELECT votes FROM threads WHERE id = %s", (thread_id,))
            db.close()
            return {"success": True, "votes": new_votes['votes']}
        except Exception as e:
            return {"success": False, "error": str(e)}, 500

    def view_thread(self, thread_id):
        try:
            db = Database()
            thread = db.fetch_one("SELECT * FROM threads WHERE id = %s", (thread_id,))
            if not thread:
                flash("Thread not found!", "danger")
                return redirect(url_for("Home.home"))
            
            replies = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s ORDER BY created_at ASC", (thread_id,))
            db.close()
            return render_template("thread_detail.html", thread=thread, replies=replies)
        except Exception as e:
            flash(f"Error loading thread: {str(e)}", "danger")
            return redirect(url_for("Home.home"))

    def post_reply(self, thread_id):
        content = request.form.get("content")
        author = session.get("user_name", "Guest")

        if not content:
            return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

        # Apply word censoring to the reply content
        censored_content = WordCensor.censor_text(content)

        try:
            db = Database()
            db.execute(
                "INSERT INTO replies (thread_id, content, user_email) VALUES (%s, %s, %s)",
                (thread_id, censored_content, author)
            )
            db.close()
        except Exception as e:
            print(f"Error posting reply: {e}")

        return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

    def view_community(self, category_name):
        try:
            db = Database()
            # Fetch threads for this specific category
            threads = db.fetch_all(
                "SELECT * FROM threads WHERE category = %s ORDER BY votes DESC, created_at DESC",
                (category_name,)
            )
            # Fetch replies for each thread
            for thread in threads:
                thread['replies'] = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s ORDER BY created_at ASC", (thread['id'],))
            
            db.close()
            return render_template("community.html", category_name=category_name, threads=threads)
        except Exception as e:
            flash(f"Error loading community: {str(e)}", "danger")
            return redirect(url_for("Home.home"))

    def create_thread(self):
        title = request.form.get("title")
        content = request.form.get("content")
        category_name = request.form.get("category", "Sports")
        
        # Get author name from session, or default to guest
        author = session.get("user_name", "Guest")
        
        if not title or not content:
            return redirect(request.referrer or url_for("Home.home"))

        # Apply word censoring to title and content
        censored_title = WordCensor.censor_text(title)
        censored_content = WordCensor.censor_text(content)

        try:
            db = Database()
            # Fetch the ID for the category name
            cat = db.fetch_one("SELECT id FROM categories WHERE name = %s", (category_name,))
            category_id = cat['id'] if cat else None

            db.execute(
                "INSERT INTO threads (title, content, author, category, category_id) VALUES (%s, %s, %s, %s, %s)",
                (censored_title, censored_content, author, category_name, category_id)
            )
            db.close()
        except Exception as e:
            print(f"Error creating thread: {e}")

        return redirect(request.referrer or url_for("Home.home"))
