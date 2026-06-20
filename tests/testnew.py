import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from flask import Flask, Blueprint, session
from app.follows import is_following, following_ids
from app.notifications import create_notification, notify_community_member, notify_community_members
from app.routes.ThreadRoutes import ThreadRoute, ThreadRoutes
from app.routes.UserRoutes import UserRoutes
def row_mock(**fields):
      row = MagicMock()
      row.__getitem__.side_effect = fields.__getitem__
      row.get.side_effect = fields.get
      for key, value in fields.items():
          setattr(row, key, value)
      return row

class PureHelperUnitTests(unittest.TestCase):
      def test_is_following_returns_true_when_db_row_exists(self):
          db = MagicMock()
          db.fetch_one.return_value = row_mock(exists=1)

          result = is_following(db, follower_id=1, followee_id=2)

          self.assertTrue(result)
          db.fetch_one.assert_called_once_with(
              "SELECT 1 FROM user_follows WHERE follower_id = %s AND followee_id = %s",
              (1, 2),
          )

      def test_is_following_short_circuits_without_database_when_ids_missing(self):
          db = MagicMock()

          result = is_following(db, follower_id=None, followee_id=2)

          self.assertFalse(result)
          db.fetch_one.assert_not_called()

      def test_following_ids_returns_set_from_mocked_rows(self):
          db = MagicMock()
          db.fetch_all.return_value = [
              row_mock(followee_id=2),
              row_mock(followee_id=3),
          ]

          result = following_ids(db, follower_id=1)

          self.assertEqual(result, {2, 3})
          db.fetch_all.assert_called_once_with(
              "SELECT followee_id FROM user_follows WHERE follower_id = %s",
              (1,),
          )

      def test_create_notification_inserts_notification(self):
          db = MagicMock()

          result = create_notification(
              db,
              user_id=5,
              type="follow",
              message="Alex started following you",
              url="/user/1",
              actor_id=1,
          )

          self.assertTrue(result)
          db.execute.assert_called_once_with(
              """
          INSERT INTO notifications (user_id, actor_id, type, message, url)
          VALUES (%s, %s, %s, %s, %s)
          """,
              (5, 1, "follow", "Alex started following you", "/user/1"),
          )

      def test_create_notification_does_not_notify_self(self):
          db = MagicMock()

          result = create_notification(
              db,
              user_id=5,
              type="follow",
              message="You followed yourself",
              actor_id=5,
          )

          self.assertFalse(result)
          db.execute.assert_not_called()

      @patch("app.notifications.create_notification")
      def test_notify_community_members_skips_actor(self, mock_create_notification):
          db = MagicMock()
          db.fetch_all.return_value = [
              row_mock(user_id=1),
              row_mock(user_id=2),
              row_mock(user_id=3),
          ]

          notify_community_members(
              db,
              community_id=10,
              type="community_post",
              message="New post in Basket Hub",
              url="/community/10",
              actor_id=2,
          )

          db.fetch_all.assert_called_once_with(
              "SELECT user_id FROM community_members WHERE community_id = %s",
              (10,),
          )
          self.assertEqual(mock_create_notification.call_count, 2)
          mock_create_notification.assert_any_call(
              db, 1, "community_post", "New post in Basket Hub",
              url="/community/10",
              actor_id=2,
          )
          mock_create_notification.assert_any_call(
              db, 3, "community_post", "New post in Basket Hub",
              url="/community/10",
              actor_id=2,
          )


class RouteUnitTests(unittest.TestCase):
      def setUp(self):
          self.app = Flask(__name__)
          self.app.secret_key = "unit-test-secret"

          home = Blueprint("Home", __name__)
          thread = Blueprint("Thread", __name__)
          user = Blueprint("User", __name__)
          auth = Blueprint("Auth", __name__)

          @home.route("/")
          def home_page():
              return "home"

          @thread.route("/thread/<int:thread_id>")
          def view_thread(thread_id):
              return f"thread {thread_id}"

          @user.route("/user/<int:user_id>")
          def profile(user_id):
              return f"user {user_id}"

          @auth.route("/login")
          def login():
              return "login"

          self.app.register_blueprint(home)
          self.app.register_blueprint(thread)
          self.app.register_blueprint(user)
          self.app.register_blueprint(auth)

      @patch("app.routes.ThreadRoutes.Database")
      def test_vote_reply_inserts_new_like_and_returns_mocked_counts(self, mock_database):
          db = MagicMock()
          mock_database.return_value = db

          reply = row_mock(id=20, thread_id=10, user_email="author")
          like_count = row_mock(c=4)
          dislike_count = row_mock(c=1)

          db.fetch_one.side_effect = [
              reply,
              None,
              like_count,
              dislike_count,
          ]

          routes = ThreadRoutes.__new__(ThreadRoutes)

          with self.app.test_request_context(
              "/thread/10/reply/20/vote",
              method="POST",
              data={"vote_type": "like"},
              headers={"X-Requested-With": "XMLHttpRequest"},
          ):
              session["user_id"] = 7
              response = routes.vote_reply(10, 20)

          self.assertEqual(response.status_code, 200)
          self.assertEqual(
              response.get_json(),
              {"success": True, "like_count": 4, "dislike_count": 1},
          )

          mock_database.assert_called_once()
          db.fetch_one.assert_any_call(
              "SELECT * FROM replies WHERE id = %s AND thread_id = %s",
              (20, 10),
          )
          db.fetch_one.assert_any_call(
              "SELECT * FROM reply_votes WHERE reply_id = %s AND user_id = %s",
              (20, 7),
          )
          db.execute.assert_called_once_with(
              "INSERT INTO reply_votes (user_id, reply_id, vote_type) VALUES (%s, %s, %s)",
              (7, 20, "like"),
          )
          db.close.assert_called_once()

      @patch("app.routes.UserRoutes.are_mutual_followers", return_value=True)
      @patch("app.routes.UserRoutes.create_notification")
      @patch("app.routes.UserRoutes.has_block_between", return_value=False)
      @patch("app.routes.UserRoutes.Database")
      def test_follow_creates_follow_and_notification_without_database(
          self,
          mock_database,
          mock_has_block_between,
          mock_create_notification,
          mock_are_mutual_followers,
      ):
          db = MagicMock()
          mock_database.return_value = db

          target = row_mock(id=9, name="Taylor")
          follower = row_mock(id=3, name="Jordan")
          db.fetch_one.side_effect = [target, follower]

          routes = UserRoutes.__new__(UserRoutes)

          with self.app.test_request_context("/user/9/follow", method="POST"):
              session["user_id"] = 3
              session["user_name"] = "Jordan"
              response = routes.follow(9)

          self.assertEqual(response.status_code, 302)

          mock_database.assert_called_once()
          mock_has_block_between.assert_called_once_with(db, 3, 9)
          db.execute.assert_called_once_with(
              "INSERT IGNORE INTO user_follows (follower_id, followee_id) VALUES (%s, %s)",
              (3, 9),
          )
          db.fetch_one.assert_any_call(
              "SELECT id, name FROM users WHERE id = %s",
              (9,),
          )
          db.fetch_one.assert_any_call(
              "SELECT id, name FROM users WHERE id = %s",
              (3,),
          )
          mock_create_notification.assert_called_once()
          mock_are_mutual_followers.assert_called_once_with(db, 3, 9)
          db.close.assert_called_once()


if __name__ == "__main__":
      unittest.main()