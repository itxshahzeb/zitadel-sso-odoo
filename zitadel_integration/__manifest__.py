{
    'name': 'ZITADEL SSO - OpenID Connect (Authorization Code)',
    'version': '19.0.1.4.0',
    'category': 'Tools',
    'summary': 'Single Sign-On via ZITADEL, Keycloak, Auth0, Okta or any OpenID '
               'Connect provider, using the Authorization Code flow',
    'description': """
OpenID Connect Single Sign-On for Odoo
======================================

Odoo's built-in **auth_oauth** only speaks the OAuth2 *implicit* flow: it builds
``response_type=token`` links and expects an access token back in the URL
fragment. Every current OpenID Connect provider - ZITADEL, Keycloak, Auth0,
Okta, Microsoft Entra ID - requires the **Authorization Code** flow with a
confidential client instead, and refuses the implicit one outright.

This module adds that flow, as an option on each provider, without replacing
anything. Providers already configured for the legacy flow keep working exactly
as they did.

What it adds
------------

* **Authorization Code flow** with a confidential client (client id + secret).
  The code is exchanged for an access token server-side, never in the browser.
* **Per-provider flow selector**, so legacy and OIDC providers coexist in one
  database.
* **Client Secret** and **Token URL** fields, the secret readable only by
  Settings administrators.
* **Reliable first login.** Odoo's stock path copies the user named by the
  ``base.template_portal_user_id`` parameter; when that is unset or points at an
  archived user, every first-time SSO login fails with no useful error. This
  creates the user directly instead, so any authenticated identity gets an
  account.
* **Default user type per provider** - new users land as Portal or Internal.
  Existing users keep whatever groups they already have.
* **Profile sync** - name and email are refreshed from the provider on every
  login.
* **Auto-redirect login**, sending ``/web/login`` straight to the provider, with
  ``?local=1`` always available so an administrator cannot be locked out.
* **Correct landing page** - portal users arrive at ``/my`` rather than bouncing
  off the backend.

Setup
-----

See README.md for the full walkthrough: the redirect URI to register, which
application type to pick, and where each value goes.

Nothing is enabled on install. The module ships one disabled provider record
with placeholder endpoints for you to fill in.
""",
    'author': 'Shahzeb',
    'support': 'shahzebvaxeer5616@gmail.com',
    'depends': ['auth_oauth'],
    'data': [
        'data/auth_oauth_provider_data.xml',
        'views/auth_oauth_provider_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
