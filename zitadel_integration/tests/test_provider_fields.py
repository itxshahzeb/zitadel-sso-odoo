from odoo.tests.common import TransactionCase, new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestProviderFields(TransactionCase):
    """The provider record itself: defaults, and who may read the secret."""

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

    def test_legacy_flow_is_the_default(self):
        """A provider created without a flow behaves as it always did.

        Databases upgrading to this module must not have their existing
        providers silently switched to a flow the IdP may not accept.
        """
        legacy = self.env['auth.oauth.provider'].create({
            'name': 'Legacy',
            'auth_endpoint': 'https://old.example.com/authorize',
            'validation_endpoint': 'https://old.example.com/userinfo',
            'body': 'Login',
        })
        self.assertEqual(legacy.flow, 'token')
        self.assertEqual(legacy.default_user_type, 'portal')
        self.assertFalse(legacy.auto_redirect)

    def test_secret_is_hidden_from_non_administrators(self):
        """client_secret is a group_system field, not merely a masked input.

        auth_oauth's own list_providers() does sudo().search_read() with no
        field list, so the secret travels further than the settings screen.
        """
        staff = new_test_user(self.env, login='oidc_staff', groups='base.group_user')
        as_staff = self.provider.with_user(staff)
        self.assertNotIn('client_secret', as_staff.fields_get())
        with self.assertRaises(AccessError):
            as_staff.read(['client_secret'])

    def test_administrator_can_read_the_secret(self):
        admin = new_test_user(self.env, login='oidc_admin', groups='base.group_system')
        self.assertEqual(
            self.provider.with_user(admin).client_secret, 's3cret',
        )

    def test_shipped_provider_is_inert(self):
        """The record the module seeds must not put a live button on /web/login.

        It carries placeholder endpoints; enabled by default it would render a
        broken "Login with ZITADEL" link on every database that installs this.
        """
        seeded = self.env.ref(
            'zitadel_integration.provider_zitadel', raise_if_not_found=False,
        )
        self.assertTrue(seeded, "the seeded provider record is missing")
        self.assertFalse(seeded.enabled)
        self.assertFalse(seeded.auto_redirect)
        self.assertFalse(seeded.client_id)
        for url in (seeded.auth_endpoint, seeded.token_endpoint,
                    seeded.validation_endpoint):
            self.assertIn('example', url, "a real tenant is shipped in the data")
