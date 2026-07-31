# Security Policy

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private vulnerability reporting:
the repository's **Security** tab → *Report a vulnerability*. It creates a private
advisory only you and the maintainer can see.

Useful in a report: what an attacker gains, the smallest sequence of steps that shows it,
the version and how you installed it, and — if the AI layer is involved — the provider and
model, since behaviour there varies by model.

SAGA is an alpha maintained by one person. Expect a first response in a few days, not
hours. You will be credited in the advisory and the release notes unless you ask otherwise.

## Supported versions

Pre-1.0, only the **latest release** receives fixes. There are no backports to earlier
`0.x` tags — upgrading is the fix.

## Threat model

SAGA is single-player and self-hosted: one person, their own machine, their own database,
their own provider keys. It is not built to be exposed to the public internet, and running
it that way is outside what the code defends against.

Inside that model, these are the things worth reporting:

- **Authentication and authorisation** — anything that lets one account reach another
  account's campaigns, characters or settings.
- **Secret exposure** — provider keys or the JWT secret reachable through the API, a log
  line, an error response, or the frontend bundle.
- **Injection** — SQL injection, or a prompt injection that escalates beyond narration:
  making the DM call tools the player should not be able to trigger, corrupting world state,
  or reaching the host.
- **Remote code execution**, path traversal, or anything that escapes the world YAML loader
  or the campaign import path — both parse files a user supplies.
- **XSS** in narration, journal entries, or world content rendered in the frontend.

Not vulnerabilities:

- The model writing something offensive, wrong, or off-tone. That is a content-quality
  issue — open a normal issue.
- A weak configuration you set yourself: leaving the `change-me` secrets in place is
  rejected at startup on purpose, and overriding that is your decision.
- Denial of service against your own instance, or exhausting your own provider quota.
- Anything requiring an attacker to already have access to your machine or your `.env`.

## What the code already does

Stated so a report can point at the gap rather than the mechanism:

- Provider keys live in `.env` or, per user, encrypted with AES-256 at rest.
- Auth is JWT bearer plus bcrypt. Tokens are never accepted as query parameters.
- `jwt_secret` and `api_key_encryption_key` are validated at startup; the `change-me`
  defaults refuse to boot in production.
- Player input is sanitised and screened for prompt injection before reaching the DM.
- Tool errors returned to the model are sanitised — no stack traces, exception types or
  filesystem paths are fed back into the loop.
