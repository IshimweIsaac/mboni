# Hosting Mboni on the team server

The live site **https://mboni.lumina.rw** runs on Isaac's PC:

| Piece | What it does |
|---|---|
| `mboni.service` | gunicorn serving the app on 127.0.0.1:8070 (from `~/srv/mboni`, a clone of this repo) |
| `mboni-tunnel.service` | Cloudflare Tunnel publishing port 8070 as mboni.lumina.rw (HTTPS, no open router ports) |
| `mboni-update.timer` + `update.sh` | every 2 minutes: fetch `main`, run all tests, go live only if they pass |
| `~/.config/mboni/mboni.env` | `SECRET_KEY`, `DATABASE`, `SESSION_COOKIE_SECURE=1`, `BEHIND_PROXY=1` (not in git) |

So the team workflow is: edit in VS Code (locally or at vscode.dev), push to `main`, and the site updates by itself
within about two minutes. GitHub Actions runs the same tests on every push.
