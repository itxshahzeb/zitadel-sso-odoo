from odoo import fields, models


class AuthOAuthProvider(models.Model):
    _inherit = 'auth.oauth.provider'

    flow = fields.Selection(
        [
            ('token', 'OAuth2 Implicit (legacy)'),
            ('id_token_code', 'OpenID Connect (Authorization Code)'),
        ],
        string='Flow',
        default='token',
        required=True,
    )
    # Settings-only, at field level rather than in the view alone.
    #
    # password="True" on the form masks the input box and nothing else: the
    # value still reads back through the ORM, through exports, and through RPC.
    # It matters here because auth_oauth's own list_providers() calls
    # sudo().search_read() with no field list, so every enabled provider -
    # secret included - is loaded by a controller that unauthenticated visitors
    # reach. Odoo's stock login template prints only auth_link, css_class and
    # body, so nothing leaks today; groups= makes that a guarantee rather than
    # a property of a template somebody else maintains.
    client_secret = fields.Char(
        string='Client Secret',
        groups='base.group_system',
    )
    token_endpoint = fields.Char(
        string='Token URL',
        help='OIDC token endpoint, used to exchange the authorization code for an access token.',
    )
    auto_redirect = fields.Boolean(
        string='Auto-redirect Login',
        default=False,
        help='If enabled, /web/login will automatically redirect users to this provider '
             'instead of showing the local login form. Use ?local=1 in the URL to bypass '
             'the redirect (e.g. for admin lockout recovery).',
    )
    default_user_type = fields.Selection(
        [
            ('portal', 'Portal'),
            ('internal', 'Internal'),
        ],
        string='Default User Type',
        default='portal',
        required=True,
        help='User type assigned when a new user is created via this provider. '
             'Existing users keep their current groups.',
    )
