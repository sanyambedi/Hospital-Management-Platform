# ADR-0002: Caddy with internal TLS as reverse proxy

**Context**: The system needs HTTPS for production-like deployment. Options: Nginx + certbot, Traefik, Caddy, or no proxy.

**Decision**: Use Caddy 2 with `tls internal` for automatic HTTPS using Caddy's built-in CA. No public domain or Let's Encrypt needed.

**Consequences**: HTTPS works out of the box with `docker compose up`. Browsers show a cert warning (internal CA); use `curl -k` or trust the CA. Simple config (one Caddyfile). Security headers included. For production with a real domain, change `tls internal` to the domain name.
