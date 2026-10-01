# ZITADEL SSO — OpenID Connect (Authorization Code)

Single Sign-On for Odoo 18 against ZITADEL, or any other OpenID Connect
provider that requires the Authorization Code flow.

## Why this exists

Odoo's built-in `auth_oauth` implements only the OAuth2 **implicit** flow. It
builds `response_type=token` authorization links and expects an access token to
come back in the URL fragment. That flow was deprecated by OAuth 2.1 and is
refused outright by every current OIDC provider — ZITADEL, Keycloak, Auth0,
Okta, Microsoft Entra ID.

This module adds the **Authorization Code** flow with a confidential client,
as a per-provider option. Providers already set up for the legacy flow are
untouched and keep working.

## Installation

1. Copy `zitadel_integration` into your addons path.
2. Update the apps list, then install **ZITADEL SSO — OpenID Connect**.
3. Nothing is switched on by install: the module ships one provider record,
   disabled, with placeholder endpoints.

## Setting up the provider

### 1. Create the application in ZITADEL

In your ZITADEL console, inside your project:

| Setting | Value |
|---|---|
| Application type | **Web** |
| Authentication method | **Code** (PKCE off, Basic auth) |
| Redirect URI | `https://your-odoo-domain/auth_oauth/signin` |
| Post-logout URI | `https://your-odoo-domain/web/login` |

The redirect URI must match exactly, including scheme and any trailing path.
Odoo builds it from the **web.base.url** system parameter, so make sure that
parameter is your real public URL and not `localhost:8069`.

Copy the **Client ID** and **Client Secret** that ZITADEL shows you. The secret
is displayed once.

### 2. Configure Odoo

Enable developer mode, then **Settings → Users & Companies → OAuth Providers**,
and open the **ZITADEL** record.

| Field | Value |
|---|---|
| Flow | OpenID Connect (Authorization Code) |
| Client ID | from ZITADEL |
| Client Secret | from ZITADEL |
| Authorization URL | `https://YOUR-INSTANCE.zitadel.cloud/oauth/v2/authorize` |
| Token URL | `https://YOUR-INSTANCE.zitadel.cloud/oauth/v2/token` |
| UserInfo URL | `https://YOUR-INSTANCE.zitadel.cloud/oidc/v1/userinfo` |
| Scope | `openid profile email` |
| Default User Type | Portal or Internal |
| Allowed | tick, once the values above are real |

Then enable **Settings → General Settings → Integrations → OAuth
Authentication**.

### 3. Test

Log out, open `/web/login`, and the **Login with ZITADEL** button appears below
the password form.

## Options

### Default User Type

Decides what a first-time user becomes. **Portal** gives website/portal access
only; **Internal** gives a backend user, which consumes a seat on Odoo
Enterprise. Users who already exist keep whatever groups they have — this
setting only applies the first time an identity signs in.

### Auto-redirect Login

With this ticked, `/web/login` goes straight to the provider instead of showing
the local form. Useful when SSO is the only way in.

**Lockout escape:** append `?local=1` to reach the normal login form, e.g.
`https://your-odoo-domain/web/login?local=1`. Keep a local administrator
password that works, and test the escape hatch *before* you rely on it.

## Using another OIDC provider

Nothing in the code is ZITADEL-specific — the token exchange is a plain
RFC 6749 authorization-code request. For any other provider, fetch
`https://ITS-ISSUER/.well-known/openid-configuration` and copy
`authorization_endpoint`, `token_endpoint` and `userinfo_endpoint` into the
three URL fields.

Tested against ZITADEL Cloud. Keycloak, Auth0, Okta and Entra ID expose the
same endpoints and are expected to work; they are not covered by the tests.

## Security notes

* The client secret is a `base.group_system` field. It is never sent to the
  browser and is not readable by non-administrators over RPC.
* The authorization code is exchanged server-to-server. No token touches the
  browser.
* Authentication failures raise `AccessDenied` with no detail; the reason is in
  the server log. This is deliberate — a login form that explains *why* it
  refused is a login form that enumerates accounts.
* The module does not use PKCE. It is not required for a confidential client,
  which authenticates with its secret, but if your provider mandates PKCE this
  module will not satisfy it.

## Known limits

* One auto-redirect provider at a time — the first enabled one wins.
* Group promotion to Internal happens on the first login only, by design.
* If a login matches an **archived** user, group promotion and profile sync are
  skipped.

## Running the tests

```
odoo-bin -d YOURDB -u zitadel_integration --test-enable --test-tags /zitadel_integration --stop-after-init
```

## License

LGPL-3.
