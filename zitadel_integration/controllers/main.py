import json

import werkzeug.urls

from odoo import http
from odoo.http import request
from odoo.addons.auth_oauth.controllers.main import OAuthLogin, OAuthController


class ZitadelOAuthLogin(OAuthLogin):

    def list_providers(self):
        providers = super().list_providers()
        for provider in providers:
            if provider.get('flow') != 'id_token_code':
                continue
            # web.base.url, NOT request.httprequest.url_root.
            #
            # The authorization request and the later token exchange must send
            # a byte-identical redirect_uri - the provider compares them and
            # refuses the token if they differ. _zitadel_exchange_code() builds
            # its copy from web.base.url, so this one has to come from the same
            # place.
            #
            # url_root reflects whatever scheme and host reached this worker,
            # which behind a reverse proxy or tunnel is routinely plain http on
            # an internal name. That yields http:// here and https:// at the
            # exchange: the login either never starts, or dies halfway with the
            # provider reporting an invalid redirect.
            base_url = request.env['ir.config_parameter'].sudo().get_param(
                'web.base.url',
            ) or request.httprequest.url_root
            return_url = '%s/auth_oauth/signin' % base_url.rstrip('/')
            state = self.get_state(provider)
            params = dict(
                response_type='code',
                client_id=provider['client_id'],
                redirect_uri=return_url,
                scope=provider['scope'],
                state=json.dumps(state),
            )
            provider['auth_link'] = '%s?%s' % (
                provider['auth_endpoint'],
                werkzeug.urls.url_encode(params),
            )
        return providers

    @http.route()
    def web_login(self, *args, **kw):
        if (
            request.httprequest.method == 'GET'
            and not request.session.uid
            and not kw.get('local')
            and not kw.get('oauth_error')
            and not kw.get('error')
        ):
            target = request.env['auth.oauth.provider'].sudo().search(
                [('enabled', '=', True), ('auto_redirect', '=', True)],
                limit=1,
            )
            if target:
                providers = self.list_providers()
                match = next((p for p in providers if p['id'] == target.id), None)
                if match and match.get('auth_link'):
                    return request.redirect(match['auth_link'], local=False)
        return super().web_login(*args, **kw)


class ZitadelOAuthController(OAuthController):

    @http.route()
    def signin(self, **kw):
        resp = super().signin(**kw)
        if not request.session.uid:
            return resp
        location = getattr(resp, 'location', None) or ''
        try:
            path = werkzeug.urls.url_parse(location).path
        except Exception:
            return resp
        if path not in ('/odoo', '/web', '/'):
            return resp
        user = request.env['res.users'].sudo().browse(request.session.uid)
        if user and not user._is_internal():
            resp.location = '/my'
            resp.autocorrect_location_header = False
        return resp
