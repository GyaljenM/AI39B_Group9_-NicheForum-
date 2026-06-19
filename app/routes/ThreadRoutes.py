from flask import Blueprint, request, redirect, url_for, session, flash, render_template
from app.models.database import Database
from app.utils.word_censor import WordCensor
from app.auth import login_required, admin_required
from app.routes.HomeRoutes import save_media, attach_media_and_poll, attach_notes, REPORT_REASON_VALUES
import os

class ThreadRoutes:
    def __init__(self):
        self.bp = Blueprint("Thread", __name__)
        # Folder for images/videos attached to threads.
        self.threads_upload_folder = 'app/static/uploads/threads'
        if not os.path.exists(self.threads_upload_folder):
            os.makedirs(self.threads_upload_folder, exist_ok=True)

    def register(self):
        self.bp.route("/create-thread", methods=["POST"])(self.create_thread)
        self.bp.route("/community/<category_name>")(self.view_community)
        self.bp.route("/thread/<int:thread_id>")(self.view_thread)
        self.bp.route("/thread/<int:thread_id>/reply", methods=["POST"])(self.post_reply)
        self.bp.route("/thread/<int:thread_id>/reply/<int:reply_id>/vote", methods=["POST"])(self.vote_reply)
        self.bp.route("/thread/<int:thread_id>/reply/<int:reply_id>/edit", methods=["GET", "POST"])(self.edit_reply)
        self.bp.route("/thread/<int:thread_id>/edit", methods=["GET", "POST"])(self.edit_thread)
        self.bp.route("/thread/<int:thread_id>/vote", methods=["POST"])(self.vote_thread)
        self.bp.route("/thread/<int:thread_id>/poll-vote", methods=["POST"])(self.vote_thread_poll)
        self.bp.route("/thread/<int:thread_id>/note", methods=["POST"])(self.add_thread_note)
        self.bp.route("/thread/note/<int:note_id>/rate", methods=["POST"])(self.rate_thread_note)
        self.bp.route("/thread/<int:thread_id>/report", methods=["POST"])(self.report_thread)
        self.bp.route("/report/thread/<int:report_id>/resolve", methods=["POST"])(self.resolve_thread_report)
        self.bp.route("/thread/delete/<int:thread_id>", methods=["POST"])(self.delete_thread)
        return self.bp

    def delete_thread(self, thread_id):
        # Basic author check
        author = session.get("user_name", "Guest")
        is_admin = session.get("user_role") == "admin"
        try:
            db = Database()
            # Verify author (or admin) before deleting
            thread = db.fetch_one("SELECT author FROM threads WHERE id = %s", (thread_id,))
            if thread and (thread['author'] == author or is_admin):
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
            
            user_id = session.get("user_id")
            replies = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s ORDER BY created_at ASC", (thread_id,))
            for reply in replies:
                likes = db.fetch_one(
                    "SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = %s AND vote_type = 'like'",
                    (reply['id'],)
                )
                dislikes = db.fetch_one(
                    "SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = %s AND vote_type = 'dislike'",
                    (reply['id'],)
                )
                reply['like_count'] = likes['c'] if likes else 0
                reply['dislike_count'] = dislikes['c'] if dislikes else 0
                reply['user_vote'] = None
                if user_id:
                    my_vote = db.fetch_one(
                        "SELECT vote_type FROM reply_votes WHERE reply_id = %s AND user_id = %s",
                        (reply['id'], user_id)
                    )
                    reply['user_vote'] = my_vote['vote_type'] if my_vote else None

            attach_media_and_poll(db, thread, "thread", user_id)
            attach_notes(db, thread, "thread", user_id)
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

    def vote_reply(self, thread_id, reply_id):
        user_id = session.get("user_id")
        if not user_id:
            return {"success": False, "error": "Login required"}, 401

        payload = request.get_json(silent=True) or {}
        vote_type = payload.get("vote_type")
        if vote_type not in ("like", "dislike"):
            return {"success": False, "error": "Invalid vote type"}, 400

        try:
            db = Database()
            reply = db.fetch_one("SELECT * FROM replies WHERE id = %s AND thread_id = %s", (reply_id, thread_id))
            if not reply:
                db.close()
                return {"success": False, "error": "Reply not found"}, 404

            existing = db.fetch_one(
                "SELECT * FROM reply_votes WHERE reply_id = %s AND user_id = %s",
                (reply_id, user_id)
            )
            if existing is None:
                db.execute(
                    "INSERT INTO reply_votes (user_id, reply_id, vote_type) VALUES (%s, %s, %s)",
                    (user_id, reply_id, vote_type)
                )
            elif existing['vote_type'] == vote_type:
                db.execute("DELETE FROM reply_votes WHERE id = %s", (existing['id'],))
            else:
                db.execute(
                    "UPDATE reply_votes SET vote_type = %s WHERE id = %s",
                    (vote_type, existing['id'])
                )

            likes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = %s AND vote_type = 'like'",
                (reply_id,)
            )
            dislikes = db.fetch_one(
                "SELECT COUNT(*) AS c FROM reply_votes WHERE reply_id = %s AND vote_type = 'dislike'",
                (reply_id,)
            )
            db.close()
            return {
                "success": True,
                "like_count": likes['c'] if likes else 0,
                "dislike_count": dislikes['c'] if dislikes else 0,
                "user_vote": vote_type if existing is None or existing['vote_type'] != vote_type else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}, 500

    def edit_reply(self, thread_id, reply_id):
        try:
            db = Database()
            reply = db.fetch_one("SELECT * FROM replies WHERE id = %s AND thread_id = %s", (reply_id, thread_id))
            if not reply:
                flash("Reply not found.", "danger")
                db.close()
                return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

            author = session.get("user_name", "Guest")
            if reply['user_email'] != author:
                flash("You are not authorized to edit this reply.", "danger")
                db.close()
                return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

            if request.method == 'POST':
                content = request.form.get('content')
                if not content:
                    flash("Content cannot be empty.", "warning")
                    db.close()
                    return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

                censored = WordCensor.censor_text(content)
                db.execute("UPDATE replies SET content = %s WHERE id = %s", (censored, reply_id))
                db.close()
                flash("Reply updated.", "success")
                return redirect(url_for("Thread.view_thread", thread_id=thread_id))

            db.close()
            return render_template("edit_reply.html", reply=reply, thread_id=thread_id)
        except Exception as e:
            flash(f"Error editing reply: {e}", "danger")
            return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

    def edit_thread(self, thread_id):
        try:
            db = Database()
            thread = db.fetch_one("SELECT * FROM threads WHERE id = %s", (thread_id,))
            if not thread:
                flash("Thread not found.", "danger")
                db.close()
                return redirect(url_for("Home.home"))

            author = session.get("user_name", "Guest")
            if thread['author'] != author:
                flash("You are not authorized to edit this thread.", "danger")
                db.close()
                return redirect(url_for("Thread.view_thread", thread_id=thread_id))

            if request.method == 'POST':
                title = request.form.get('title')
                content = request.form.get('content')
                if not title or not content:
                    flash("Title and content cannot be empty.", "warning")
                    db.close()
                    return redirect(url_for("Thread.edit_thread", thread_id=thread_id))

                censored_title = WordCensor.censor_text(title)
                censored_content = WordCensor.censor_text(content)
                db.execute("UPDATE threads SET title = %s, content = %s WHERE id = %s", (censored_title, censored_content, thread_id))
                db.close()
                flash("Thread updated.", "success")
                return redirect(url_for("Thread.view_thread", thread_id=thread_id))

            db.close()
            return render_template("edit_thread.html", thread=thread)
        except Exception as e:
            flash(f"Error editing thread: {e}", "danger")
            return redirect(url_for("Thread.view_thread", thread_id=thread_id))

    def view_community(self, category_name):
        try:
            db = Database()
            # Fetch threads for this specific category
            threads = db.fetch_all(
                "SELECT * FROM threads WHERE category = %s ORDER BY votes DESC, created_at DESC",
                (category_name,)
            )
            # Fetch replies for each thread
            user_id = session.get("user_id")
            for thread in threads:
                thread['replies'] = db.fetch_all("SELECT * FROM replies WHERE thread_id = %s ORDER BY created_at ASC", (thread['id'],))
                attach_media_and_poll(db, thread, "thread", user_id)
                attach_notes(db, thread, "thread", user_id)

            db.close()
            return render_template("community.html", category_name=category_name, threads=threads)
        except Exception as e:
            flash(f"Error loading community: {str(e)}", "danger")
            return redirect(url_for("Home.home"))

    def create_thread(self):
        thread_type = request.form.get("thread_type", "text")
        if thread_type not in ("text", "media", "poll"):
            thread_type = "text"
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        category_name = request.form.get("category", "Sports")

        # Get author name from session, or default to guest
        author = session.get("user_name", "Guest")

        if not title:
            flash("A title is required.", "warning")
            return redirect(request.referrer or url_for("Home.home"))
        if thread_type == "text" and not content:
            flash("Please write something in the body of your post.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        # Apply word censoring to title and content
        censored_title = WordCensor.censor_text(title)
        censored_content = WordCensor.censor_text(content)

        saved_media = []
        if thread_type in ("text", "media"):
            for f in request.files.getlist("media"):
                if not f or not f.filename:
                    continue
                result = save_media(f, self.threads_upload_folder, "uploads/threads")
                if result is None:
                    flash(f"Skipped '{f.filename}': unsupported file type.", "warning")
                    continue
                saved_media.append(result)
            if thread_type == "media" and not saved_media:
                flash("Please attach at least one image or video.", "warning")
                return redirect(request.referrer or url_for("Home.home"))

        poll_options = []
        if thread_type == "poll":
            poll_options = [o.strip() for o in request.form.getlist("poll_options") if o.strip()]
            if len(poll_options) < 2:
                flash("A poll needs at least two options.", "warning")
                return redirect(request.referrer or url_for("Home.home"))

        try:
            db = Database()
            # Fetch the ID for the category name
            cat = db.fetch_one("SELECT id FROM categories WHERE name = %s", (category_name,))
            category_id = cat['id'] if cat else None

            db.execute(
                "INSERT INTO threads (title, content, thread_type, author, category, category_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (censored_title, censored_content, thread_type, author, category_name, category_id)
            )
            thread_id = db.fetch_one("SELECT LAST_INSERT_ID() AS id")["id"]

            for media_type, rel_path in saved_media:
                db.execute(
                    "INSERT INTO thread_media (thread_id, media_type, file_path) VALUES (%s, %s, %s)",
                    (thread_id, media_type, rel_path),
                )

            for position, option_text in enumerate(poll_options):
                db.execute(
                    "INSERT INTO thread_poll_options (thread_id, option_text, position) VALUES (%s, %s, %s)",
                    (thread_id, option_text, position),
                )
            db.close()
        except Exception as e:
            print(f"Error creating thread: {e}")

        return redirect(request.referrer or url_for("Home.home"))

    @login_required
    def vote_thread_poll(self, thread_id):
        """Cast or change a vote on a poll thread (login required)."""
        user_id = session.get("user_id")
        option_id = request.form.get("option_id")

        db = Database()
        thread = db.fetch_one("SELECT * FROM threads WHERE id = %s", (thread_id,))
        if not thread:
            db.close()
            flash("Thread not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        option = db.fetch_one(
            "SELECT * FROM thread_poll_options WHERE id = %s AND thread_id = %s",
            (option_id, thread_id),
        )
        if not option:
            db.close()
            flash("Invalid poll option.", "warning")
            return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

        existing = db.fetch_one(
            "SELECT * FROM thread_poll_votes WHERE thread_id = %s AND user_id = %s",
            (thread_id, user_id),
        )
        if existing is None:
            db.execute(
                "INSERT INTO thread_poll_votes (option_id, thread_id, user_id) VALUES (%s, %s, %s)",
                (option["id"], thread_id, user_id),
            )
        elif existing["option_id"] != option["id"]:
            db.execute(
                "UPDATE thread_poll_votes SET option_id = %s WHERE id = %s",
                (option["id"], existing["id"]),
            )
        db.close()
        return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

    @login_required
    def add_thread_note(self, thread_id):
        """Attach a community note (crowd-sourced context) to a thread."""
        user_id = session.get("user_id")
        content = (request.form.get("content") or "").strip()
        source = (request.form.get("source") or "").strip() or None

        db = Database()
        thread = db.fetch_one("SELECT id FROM threads WHERE id = %s", (thread_id,))
        if not thread:
            db.close()
            flash("Thread not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        if not content:
            db.close()
            flash("A community note can't be empty.", "warning")
            return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

        db.execute(
            "INSERT INTO thread_notes (thread_id, user_id, content, source) VALUES (%s, %s, %s, %s)",
            (thread_id, user_id, content, source))
        db.close()
        flash("Community note added. It becomes public once enough readers rate it helpful.", "success")
        return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

    @login_required
    def rate_thread_note(self, note_id):
        """Rate a thread's community note helpful/not-helpful (one rating per user).

        Re-clicking the same rating removes it (toggle); the other switches it."""
        user_id = session.get("user_id")
        rating = request.form.get("rating")
        if rating not in ("helpful", "not_helpful"):
            flash("Invalid rating.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        note = db.fetch_one("SELECT * FROM thread_notes WHERE id = %s", (note_id,))
        if not note:
            db.close()
            flash("Note not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        existing = db.fetch_one(
            "SELECT * FROM thread_note_votes WHERE note_id = %s AND user_id = %s",
            (note_id, user_id))
        if existing is None:
            db.execute(
                "INSERT INTO thread_note_votes (note_id, user_id, rating) VALUES (%s, %s, %s)",
                (note_id, user_id, rating))
        elif existing['rating'] == rating:
            db.execute("DELETE FROM thread_note_votes WHERE id = %s", (existing['id'],))
        else:
            db.execute("UPDATE thread_note_votes SET rating = %s WHERE id = %s",
                       (rating, existing['id']))
        db.close()
        return redirect(request.referrer or url_for("Thread.view_thread", thread_id=note['thread_id']))

    @login_required
    def report_thread(self, thread_id):
        """Flag a thread for moderator review."""
        user_id = session.get("user_id")
        reason = request.form.get("reason")
        details = (request.form.get("details") or "").strip() or None

        if reason not in REPORT_REASON_VALUES:
            flash("Please choose a reason for your report.", "warning")
            return redirect(request.referrer or url_for("Home.home"))

        db = Database()
        thread = db.fetch_one("SELECT id FROM threads WHERE id = %s", (thread_id,))
        if not thread:
            db.close()
            flash("Thread not found.", "danger")
            return redirect(request.referrer or url_for("Home.home"))

        # One report per user per thread; re-reporting refreshes the existing row.
        db.execute(
            """
            INSERT INTO thread_reports (thread_id, user_id, reason, details)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE reason = VALUES(reason),
                                    details = VALUES(details),
                                    status = 'open'
            """,
            (thread_id, user_id, reason, details),
        )
        db.close()
        flash("Thanks for reporting. Our moderators will review this thread.", "success")
        return redirect(request.referrer or url_for("Thread.view_thread", thread_id=thread_id))

    @admin_required
    def resolve_thread_report(self, report_id):
        """Mark a thread report reviewed (dismiss it from the open queue)."""
        db = Database()
        db.execute("UPDATE thread_reports SET status = 'reviewed' WHERE id = %s", (report_id,))
        db.close()
        flash("Report dismissed.", "success")
        return redirect(url_for("Home.admin_reports"))
