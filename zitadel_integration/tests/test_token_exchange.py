from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessDenied
from odoo.tests import tagged


class _Response:
    """Just enough of requests.Response for the code under test."""

    def __init__(self, ok=True, status_code=200, payload=None, text=''):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@tagged('post_install', '-at_install')
class TestTokenExchange(TransactionCase):
    """_zitadel_exchange_code: the server-to-server half of the code flow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['auth.oauth.provider'].create({
            'name': 'Test OIDC',
            'flow': 'id_token_code',
            'client_id': 'test-client',
            'client_secret': 's3cret',
            'auth_endpoint': 'https://idp.example.com/authorize',
            'token_endpoint': 'https://idp.example.com/token',
            'validation_endpoint': 'https://idp.example.com/userinfo',
            'body': 'Login with Test',
            'enabled': True,
        })
        cls.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://odoo.example.com',
        )

    def test_code_is_exchanged_for_a_token(self):
        captured = {}

        def fake_post(url, data=None, auth=None, timeout=None):
            captured.update(url=url, data=data, auth=auth, timeout=timeout)
            return _Response(payload={'access_token': 'tok-123'})

        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   side_effect=fake_post):
            token = self.env['res.users']._zitadel_exchange_code(
                self.provider, {'code': 'auth-code'},
            )

        self.assertEqual(token, 'tok-123')
        self.assertEqual(captured['url'], 'https://idp.example.com/token')
        self.assertEqual(captured['data']['grant_type'], 'authorization_code')
        self.assertEqual(captured['data']['code'], 'auth-code')
        self.assertEqual(captured['auth'], ('test-client', 's3cret'))
        self.assertTrue(captured['timeout'], "the call must not hang forever")

    def test_redirect_uri_is_built_from_web_base_url(self):
        """It has to match what was registered with the provider, exactly.

        A mismatch here is the single most common cause of a failed OIDC
        setup, and the provider's error says only "invalid redirect".
        """
        captured = {}

        def fake_post(url, data=None, auth=None, timeout=None):
            captured.update(data=data)
            return _Response(payload={'access_token': 'tok'})

        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   side_effect=fake_post):
            self.env['res.users']._zitadel_exchange_code(
                self.provider, {'code': 'auth-code'},
            )

        self.assertEqual(
            captured['data']['redirect_uri'],
            'https://odoo.example.com/auth_oauth/signin',
        )

    def test_trailing_slash_on_base_url_does_not_double_up(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'https://odoo.example.com/',
        )
        captured = {}

        def fake_post(url, data=None, auth=None, timeout=None):
            captured.update(data=data)
            return _Response(payload={'access_token': 'tok'})

        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   side_effect=fake_post):
            self.env['res.users']._zitadel_exchange_code(
                self.provider, {'code': 'auth-code'},
            )

        self.assertEqual(
            captured['data']['redirect_uri'],
            'https://odoo.example.com/auth_oauth/signin',
        )

    def test_missing_code_is_refused(self):
        with self.assertRaises(AccessDenied):
            self.env['res.users']._zitadel_exchange_code(self.provider, {})

    def test_provider_error_is_refused(self):
        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   return_value=_Response(ok=False, status_code=401,
                                          text='invalid_client')):
            with self.assertRaises(AccessDenied):
                self.env['res.users']._zitadel_exchange_code(
                    self.provider, {'code': 'auth-code'},
                )

    def test_token_response_without_a_token_is_refused(self):
        """A 200 that carries no access_token must not pass for success."""
        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   return_value=_Response(payload={'token_type': 'Bearer'})):
            with self.assertRaises(AccessDenied):
                self.env['res.users']._zitadel_exchange_code(
                    self.provider, {'code': 'auth-code'},
                )

    def test_network_failure_is_refused(self):
        import requests
        with patch('odoo.addons.zitadel_integration.models.res_users.requests.post',
                   side_effect=requests.RequestException('boom')):
            with self.assertRaises(AccessDenied):
                self.env['res.users']._zitadel_exchange_code(
                    self.provider, {'code': 'auth-code'},
                )
