import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessDenied
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestUserProvisioning(TransactionCase):
    """First-login account creation, and what happens on later logins."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Users = cls.env['res.users']
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
        # signup() refuses an uninvited new account otherwise, and the whole
        # first-login path runs through it.
        cls.env['ir.config_parameter'].sudo().set_param(
            'auth_signup.invitation_scope', 'b2c',
        )

    def _signup_values(self, login='newcomer@example.com', **extra):
        values = {
            'login': login,
            'name': 'New Comer',
            'email': login,
            'oauth_provider_id': self.provider.id,
            'oauth_uid': 'uid-1',
            'oauth_access_token': 'tok',
        }
        values.update(extra)
        return values

    def test_first_login_creates_a_portal_user(self):
        user = self.Users._signup_create_user(self._signup_values())
        self.assertTrue(user.exists())
        self.assertEqual(user.login, 'newcomer@example.com')
        self.assertEqual(user.name, 'New Comer')
        self.assertTrue(user.active)
        self.assertTrue(user.has_group('base.group_portal'))
        self.assertFalse(user.has_group('base.group_user'))

    def test_creation_does_not_depend_on_the_portal_template_parameter(self):
        """The whole reason this module bypasses _create_user_from_template.

        Odoo's stock path copies the user named by base.template_portal_user_id.
        Unset it, or point it at an archived user, and every first-time SSO
        login fails with nothing useful in the error. Account creation must
        survive both.
        """
        param = self.env['ir.config_parameter'].sudo()
        param.set_param('base.template_portal_user_id', '')
        user = self.Users._signup_create_user(
            self._signup_values(login='nocopy@example.com'),
        )
        self.assertTrue(user.exists())

        param.set_param('base.template_portal_user_id', '999999999')
        other = self.Users._signup_create_user(
            self._signup_values(login='badtemplate@example.com', oauth_uid='uid-2'),
        )
        self.assertTrue(other.exists())

    def test_profile_without_a_login_is_refused(self):
        """No email in the profile means no account. Never invent one."""
        values = self._signup_values()
        values.pop('login')
        with self.assertRaises(AccessDenied):
            self.Users._signup_create_user(values)

    def test_non_oauth_signup_is_left_to_odoo(self):
        """Ordinary signup must not be routed through the ZITADEL path.

        _signup_create_user is Odoo's, not ours; we only claim values that
        carry an oauth_provider_id. Anything else has to fall through
        untouched, or installing this module changes how every other signup
        on the database behaves.
        """
        called = []
        with patch.object(
            type(self.Users), '_create_zitadel_user',
            side_effect=lambda values: called.append(values),
        ):
            try:
                self.Users._signup_create_user(
                    {'login': 'plain@example.com', 'name': 'Plain'},
                )
            except Exception:
                pass
        self.assertFalse(called, "a non-OAuth signup was hijacked by this module")

    def _signin(self, uid, email, name=None):
        """Drive the real sign-in path, the way auth_oauth does.

        _auth_oauth_signin looks the user up by oauth_uid and, failing that,
        falls through to signup() - which is what reaches our overridden
        _signup_create_user. Calling _signup_create_user directly instead would
        create the user first and make pre_existing true on the way in, which
        is not what happens in production.
        """
        validation = {'user_id': uid, 'email': email}
        if name:
            validation['name'] = name
        return self.Users._auth_oauth_signin(
            self.provider.id,
            validation,
            {'access_token': 'tok', 'state': json.dumps({'d': self.env.cr.dbname})},
        )

    def test_internal_provider_promotes_a_new_user(self):
        self.provider.default_user_type = 'internal'
        login = self._signin('uid-3', 'staff@example.com', 'Staff Member')
        self.assertEqual(login, 'staff@example.com')
        user = self.Users.sudo().search([('login', '=', 'staff@example.com')])
        self.assertTrue(user, "no user was created by the sign-in")
        self.assertTrue(user.has_group('base.group_user'))
        self.assertFalse(user.has_group('base.group_portal'))

    def test_existing_user_keeps_their_groups(self):
        """Promotion is first-login only - it must not re-grant on every login.

        Somebody demoted from Internal to Portal would otherwise be promoted
        straight back the next morning.
        """
        self.provider.default_user_type = 'internal'
        self._signin('uid-4', 'demoted@example.com')
        user = self.Users.sudo().search([('login', '=', 'demoted@example.com')])
        self.assertTrue(user.has_group('base.group_user'))

        # an administrator puts them back to portal
        groups_field = self.Users._oidc_groups_field()
        user.write({groups_field: [
            (3, self.env.ref('base.group_user').id),
            (4, self.env.ref('base.group_portal').id),
        ]})

        # they log in again: the demotion must stick
        self._signin('uid-4', 'demoted@example.com')
        user.invalidate_recordset()
        self.assertTrue(user.has_group('base.group_portal'))
        self.assertFalse(user.has_group('base.group_user'))

    def test_name_and_email_are_synced_from_the_provider(self):
        self._signin('uid-5', 'sync@example.com', 'Original Name')
        user = self.Users.sudo().search([('login', '=', 'sync@example.com')])
        self._signin('uid-5', 'sync.new@example.com', 'Renamed Person')
        user.invalidate_recordset()
        self.assertEqual(user.name, 'Renamed Person')
        self.assertEqual(user.email, 'sync.new@example.com')

    def test_preferred_username_is_used_when_name_is_absent(self):
        self._signin('uid-6', 'pref@example.com')
        user = self.Users.sudo().search([('login', '=', 'pref@example.com')])
        self.Users._auth_oauth_signin(
            self.provider.id,
            {'user_id': 'uid-6', 'preferred_username': 'Preferred Name'},
            {'access_token': 'tok', 'state': json.dumps({'d': self.env.cr.dbname})},
        )
        user.invalidate_recordset()
        self.assertEqual(user.name, 'Preferred Name')
