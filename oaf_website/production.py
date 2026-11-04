"""One production Flask application and explicit finite Render entry points."""

import os
import sys
from ipaddress import ip_address

from flask import abort, jsonify, request, send_file
from werkzeug.wrappers import Response

from . import production_config as config
from .local_testing import PUBLIC_FILES, ROOT
from .notification_dispatch import report_failure
from .state_requests import create_app


class RenderPublicEdge:
    """Use Render's public HTTPS edge and owner-controlled private workspace.

    Private requests are not cryptographically authenticated by these headers.
    Services in the same workspace/region must remain owner-controlled.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/healthz" and environ.get("REQUEST_METHOD") in {"GET", "HEAD"}:
            # Render probes may use its assigned hostname. Only this fixed,
            # nonprivate liveness response is independent of the public Host.
            return Response('{"status":"ok"}\n', content_type="application/json",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})(environ, start_response)
        try:
            value = environ.get("HTTP_CF_CONNECTING_IP", "")
            # No lists, duplicates, ports, scope identifiers or fallback to XFF.
            client = ip_address(value)
            valid = "%" not in value and environ.get("HTTP_X_FORWARDED_PROTO") == "https"
        except (ValueError, TypeError):
            valid = False
        for name in tuple(environ):
            if (name in {"HTTP_FORWARDED", "HTTP_X_REAL_IP", "HTTP_CF_CONNECTING_IP"}
                    or name.startswith("HTTP_X_FORWARDED_")):
                del environ[name]
        if not valid:
            return Response('{"status":"unavailable"}\n', status=400, content_type="application/json",
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})(environ, start_response)
        environ["REMOTE_ADDR"] = str(client)
        environ["wsgi.url_scheme"] = "https"
        return self.app(environ, start_response)


def _public_file(name):
    path = ROOT / name
    if (not path.is_file() or any(p.is_symlink() for p in (path, *path.parents))
            or not path.resolve().is_relative_to(ROOT)):
        abort(404)
    return send_file(path)


def production_app():
    """Compose only; engine construction never checks out a connection."""
    try:
        settings = config.load_production_settings()
        secret = config.recognition_secret()
        integrations = config.load_integrations(secret) if settings.integrations_enabled else None
        webhook = None
        if settings.webhook_enabled:
            from .brevo_unsubscribe import BrevoWebhookConfig
            webhook = BrevoWebhookConfig("production", config.read_secret("webhook-token"))
        for name in PUBLIC_FILES:
            path = ROOT / name
            if (not path.is_file() or any(p.is_symlink() for p in (path, *path.parents))
                    or not path.resolve().is_relative_to(ROOT)):
                raise config.reject("public_file_present")
        app = create_app(expected_profile="production", recognition_secret=secret,
            public_origin=config.PUBLIC_ORIGIN, integration_config=integrations,
            confirmation_enabled=settings.confirmation_enabled, management_enabled=settings.management_enabled,
            releases_enabled=settings.releases_enabled, brevo_webhook_config=webhook,
            web_launch_url=os.environ.get("GRAMANNA_WEB_LAUNCH_URL"))
        app.config["TRUSTED_HOSTS"] = ["ovisalmsfoundation.org"]
        # Public ingress is Render's managed HTTPS edge. Same-workspace/region
        # private service access is an explicit owner-controlled trust assumption.
        app.wsgi_app = RenderPublicEdge(app.wsgi_app)

        @app.before_request
        def require_https():
            if request.path != "/healthz" and (not request.is_secure or request.host != "ovisalmsfoundation.org"):
                return jsonify(status="unavailable"), 400

        for number, name in enumerate(PUBLIC_FILES):
            app.add_url_rule("/" + name, f"public_{number}",
                             lambda filename=name: _public_file(filename))
        app.add_url_rule("/", "home", lambda: _public_file("index.html"))

        return app
    except Exception as exc:
        first = report_failure("application_startup", exc)
        # Suppress private original parser/driver values and traceback context.
        failure = RuntimeError("Production application unavailable.")
        failure.notification_failure = first
        raise failure from None


def main(argv=None):
    """Render start command: python -m oaf_website.production (one instance)."""
    app = None
    try:
        if (sys.argv[1:] if argv is None else argv):
            raise config.reject("production_arguments")
        if sys.version_info[:2] != (3, 11):
            raise config.reject("production_python_version")
        port = os.environ.get("PORT", "10000")
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise config.reject("production_port")
        app = production_app()
        from waitress import serve
        # Single process/thread retains existing process-local Contact budgets.
        # The middleware alone validates/clears edge headers. Waitress has no
        # proxy authority and no access log of private capability URLs.
        serve(app, host="0.0.0.0", port=int(port), threads=1, ident="",
              clear_untrusted_proxy_headers=False, max_request_body_size=16384,
              channel_timeout=30, expose_tracebacks=False)
        return 0
    except Exception as exc:
        report_failure("server_execution", exc, stage="startup")
        return 2
    finally:
        if app is not None:
            try:
                app.extensions["state_requests_engine"].dispose()
            except Exception as exc:
                report_failure("dispose", exc)
                return 2


def process():
    """Render Cron command; one existing durable batch, default OFF."""
    try:
        settings = config.load_production_settings()
        from .confirmation_processor import process_confirmations
        result = process_confirmations(expected_profile="production",
            enabled=settings.processing_enabled, management_enabled=settings.management_enabled,
            releases_enabled=settings.releases_enabled,
            confirmation_page=config.PUBLIC_ORIGIN + "/confirm-email.html")
        import json
        print(json.dumps({"status": result.status, "processed": result.processed,
                          "first_failure": result.first_failure}), flush=True)
        return {"processed": 0, "disabled": 2, "unavailable": 1}[result.status]
    except Exception as exc:
        report_failure("configuration", exc, stage="processor")
        return 2


if __name__ == "__main__":
    raise SystemExit(process() if sys.argv[1:] == ["process"] else main())
