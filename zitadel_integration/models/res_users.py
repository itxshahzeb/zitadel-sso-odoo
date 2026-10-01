import logging

import requests

from odoo import api, models
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _oidc_groups_field(self):
        """Name of the groups field on res.users, which changed in Odoo 19.

        Up to 18 it is ``groups_id``; from 19 it is ``group_ids``. Resolving it
        from ``_fields`` rather than branching on a version number keeps one
        source tree installable on 17 through 20 - the rest of this module uses
        no API that differs between them.
        """
        return 'group_ids' if 'group_ids' in self._fields else 'groups_id'

    @api.model
    def auth_oauth(self, provider, params):
        oauth_provider = self.env['auth.oauth.provider'].sudo().browse(provider)
        if oauth_provider.flow == 'id_token_code':
            params = dict(params)
            params['access_token'] = self._zitadel_exchange_code(oauth_provider, params)
        return super().auth_oauth(provider, params)

    @api.model
    def _signup_create_user(self, values):
        if values.get('oauth_provider_id'):
            return self._create_zitadel_user(values)
        return super()._signup_create_user(values)

    def _create_zitadel_user(self, values):
        """Create a brand-new Odoo user for a first-time ZITADEL login.

        This intentionally does NOT use Odoo's standard
        ``_create_user_from_template`` (which copies the user pointed to by
        the ``base.template_portal_user_id`` system parameter). That
        parameter can be unset, point to an archived user, or otherwise be
        broken -- which silently blocks sign-in for every ZITADEL identity
        except whichever user happened to be created/matched before.

        Instead we create the user directly with safe, minimal defaults so
        that *any* successfully authenticated ZITADEL account gets an Odoo
        account on first login, the same way "Login with Google" works.
        """
        login = values.get('login')
        if not login:
            _logger.warning('ZITADEL: no login/email in profile, refusing to create user')
            raise AccessDenied()

        company = self.env.company
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)

        user_values = {
            'name': values.get('name') or login,
            'login': login,
            'email': values.get('email') or login,
            'oauth_provider_id': values.get('oauth_provider_id'),
            'oauth_uid': values.get('oauth_uid'),
            'oauth_access_token': values.get('oauth_access_token'),
            'active': True,
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
        }
        if portal_group:
            user_values[self._oidc_groups_field()] = [(6, 0, [portal_group.id])]

        try:
            with self.env.cr.savepoint():
                # no_reset_password: skip Odoo's "set your password" welcome
                # email -- not needed since the user authenticates via ZITADEL.
                return self.with_context(no_reset_password=True).sudo().create(user_values)
        except Exception:
            _logger.exception('ZITADEL: failed to create user for login %s', login)
            raise AccessDenied()

    @api.model
    def _auth_oauth_signin(self, provider, validation, params):
        oauth_uid = validation.get('user_id')
        pre_existing = bool(oauth_uid) and bool(self.sudo().search_count([
            ('oauth_provider_id', '=', provider),
            ('oauth_uid', '=', oauth_uid),
        ]))

        login = super()._auth_oauth_signin(provider, validation, params)
        if not login:
            return login

        oauth_provider = self.env['auth.oauth.provider'].sudo().browse(provider)
        user = self.sudo().search([('login', '=', login)], limit=1)
        if not user:
            return login

        if not pre_existing and oauth_provider.default_user_type == 'internal':
            internal_group = self.env.ref('base.group_user', raise_if_not_found=False)
            portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
            groups_field = self._oidc_groups_field()
            if internal_group and internal_group not in user[groups_field]:
                cmd = [(4, internal_group.id)]
                if portal_group and portal_group in user[groups_field]:
                    cmd.append((3, portal_group.id))
                user.sudo().write({groups_field: cmd})

        sync_vals = {}
        name = validation.get('name') or validation.get('preferred_username')
        email = validation.get('email')
        if name and user.name != name:
            sync_vals['name'] = name
        if email and user.email != email:
            sync_vals['email'] = email
        if sync_vals:
            user.sudo().write(sync_vals)

        return login

    def _zitadel_exchange_code(self, provider, params):
        code = params.get('code')
        if not code:
            _logger.warning('ZITADEL: missing authorization code in callback params')
            raise AccessDenied()

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        redirect_uri = '%s/auth_oauth/signin' % base_url.rstrip('/')

        try:
            response = requests.post(
                provider.token_endpoint,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': redirect_uri,
                    'client_id': provider.client_id,
                    'client_secret': provider.client_secret or '',
                },
                auth=(provider.client_id, provider.client_secret or ''),
                timeout=10,
            )
        except requests.RequestException:
            _logger.exception('ZITADEL: token endpoint request failed')
            raise AccessDenied()

        if not response.ok:
            _logger.error(
                'ZITADEL token exchange failed (%s): %s',
                response.status_code, response.text,
            )
            raise AccessDenied()

        access_token = response.json().get('access_token')
        if not access_token:
            _logger.error('ZITADEL: no access_token in token response')
            raise AccessDenied()
        return access_token
