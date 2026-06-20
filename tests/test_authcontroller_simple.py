"""Simple, self-contained tests for app/controllers/authcontroller.py.

The controller is a mini self-contained Flask app: it builds its own
``app = Flask(__name__)``, defines ``AuthController`` with ``login``/``home``/
``register`` methods (each returning ``render_template(...)``), and registers
the ``/``, ``/login`` and ``/register`` routes.

These tests use:
  * the ``unittest`` framework (TestCase subclass, ``test_*`` methods, ``setUp``)
  * ``unittest`` assert helpers (assertEqual / assertIn / assertTrue / mock
    assert_called_*) instead of bare ``assert``
  * ``unittest.mock`` (MagicMock / patch)
  * Flask's test client (``mod.app.test_client()``)

Because the real templates (home.html / login.html / register.html) need app
context and template variables we don't want to depend on, ``render_template``
is patched with a MagicMock returning the sentinel string "RENDERED".
"""

import unittest
from unittest.mock import patch, MagicMock

import app.controllers.authcontroller as mod


# The exact products list the controller's home() builds. Read from the source
# file so the test asserts the real expected values (brush/brush1/brush2).
EXPECTED_PRODUCTS = [
    {"name": "brush", "price": "200"},
    {"name": "brush1", "price": "250"},
    {"name": "brush2", "price": "300"},
]


class AuthControllerSimpleTests(unittest.TestCase):
    def setUp(self):
        mod.app.config["TESTING"] = True
        self.client = mod.app.test_client()

    # 1. GET /login -> 200 and render_template called once with "login.html".
    @patch("app.controllers.authcontroller.render_template")
    def test_login_route(self, mock_render):
        mock_render.return_value = "RENDERED"

        resp = self.client.get("/login")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        mock_render.assert_called_once_with("login.html")

    # 2. GET /register -> 200 and render_template called with "register.html".
    @patch("app.controllers.authcontroller.render_template")
    def test_register_route(self, mock_render):
        mock_render.return_value = "RENDERED"

        resp = self.client.get("/register")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        mock_render.assert_called_once_with("register.html")

    # 3. GET / (home) -> 200, render_template called with "home.html" and the
    #    products kwarg equal to the expected 3-item list. Inspect call_args.
    @patch("app.controllers.authcontroller.render_template")
    def test_home_route_passes_products(self, mock_render):
        mock_render.return_value = "RENDERED"

        resp = self.client.get("/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(as_text=True), "RENDERED")
        self.assertTrue(mock_render.called)

        # Positional template name and the products keyword argument.
        args, kwargs = mock_render.call_args
        self.assertEqual(args[0], "home.html")
        self.assertIn("products", kwargs)
        self.assertEqual(kwargs["products"], EXPECTED_PRODUCTS)

    # 4. Direct unit test: instantiate AuthController and call .home() inside a
    #    test request context, asserting render_template got the products list.
    @patch("app.controllers.authcontroller.render_template")
    def test_controller_home_method_directly(self, mock_render):
        mock_render.return_value = "RENDERED"

        controller = mod.AuthController()
        with mod.app.test_request_context("/"):
            result = controller.home()

        self.assertEqual(result, "RENDERED")
        mock_render.assert_called_once_with("home.html", products=EXPECTED_PRODUCTS)

    # Bonus direct-method coverage using a plain MagicMock for render_template,
    # exercising login() and register() without the route layer.
    def test_controller_login_register_methods_directly(self):
        with patch.object(mod, "render_template", MagicMock(return_value="RENDERED")) as mock_render:
            controller = mod.AuthController()

            login_result = controller.login()
            self.assertEqual(login_result, "RENDERED")
            mock_render.assert_called_with("login.html")

            register_result = controller.register()
            self.assertEqual(register_result, "RENDERED")
            mock_render.assert_called_with("register.html")


if __name__ == "__main__":
    unittest.main()
