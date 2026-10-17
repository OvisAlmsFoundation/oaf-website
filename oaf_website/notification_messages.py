"""Fixed internal templates, with no routing, credentials, persistence or sending."""

from dataclasses import dataclass, field
from html import escape
import re
from urllib.parse import urlsplit

from .notification_delivery import CONTENT_VERSION, HEX
from .notifications import LABEL


@dataclass(frozen=True, repr=False)
class Message:
    subject: str
    text: str = field(repr=False)
    html: str = field(repr=False)


def _secure_page(value, paths):
    # Only a trusted server-injected absolute HTTPS page, never a request Host.
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in {None, 443}
                or parsed.query or parsed.fragment or parsed.path not in paths
                or len(parsed.hostname) > 253
                or not all(LABEL.fullmatch(label) for label in parsed.hostname.split("."))
                or not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::443)?/[A-Za-z0-9/_-]+\.html", value)):
            raise ValueError
        return value
    except Exception:
        pass
    raise ValueError("A configured secure notification page is required.") from None


def secure_page(value):
    """The unchanged exact notification/withdrawal-page contract."""
    return _secure_page(value, {"/gramanna.html"})


def secure_confirmation_page(value):
    """Accept the two exact trusted paths; render new mail to the dedicated page.

    Existing explicit /gramanna.html configuration remains compatible. Only its
    fixed path changes; HTTPS, configured authority and standard port are kept.
    """
    page = _secure_page(value, {"/gramanna.html", "/confirm-email.html"})
    return page.rsplit("/", 1)[0] + "/confirm-email.html"


def _message(subject, intro, label, link, footer):
    text = f"{intro}\n\n{label}: {link}\n\n{footer}\n"
    html = (f"<html><body><p>{escape(intro)}</p><p><a href=\"{escape(link, quote=True)}\">"
            f"{escape(label)}</a></p><p>{escape(footer)}</p></body></html>")
    return Message(subject, text, html)


def verification_message(token, confirmation_page):
    """Render a private fragment for the explicit, scanner-resistant public UI."""
    if type(token) is not str or HEX.fullmatch(token) is None:
        raise ValueError("Invalid confirmation capability.")
    link = secure_confirmation_page(confirmation_page) + "#confirm-email=" + token
    return _message("Confirm your OAF notification subscription",
        "Please confirm this email address for your requested OAF notifications.",
        "Confirm email", link,
        "This link expires 24 hours after your request. If you did not request this, ignore this email.")


def release_message(event, subscription, capabilities, notification_page):
    platform, release_id, url = event["platform"], event["release_id"], event["release_url"]
    if (event["content_version"] != CONTENT_VERSION or type(release_id) is not str
            or type(url) is not str or len(release_id) > 150):
        raise ValueError("Invalid approved release template.")
    if platform == "android":
        valid = (re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", release_id)
                 and url == "https://play.google.com/store/apps/details?id=" + release_id)
        name = "Android"
    elif platform == "ios":
        valid = (re.fullmatch(r"[1-9][0-9]{5,19}", release_id)
                 and url == "https://apps.apple.com/app/id" + release_id)
        name = "Apple iOS"
    else:
        raise ValueError("Invalid approved release template.")
    if not valid or type(subscription) is not str or HEX.fullmatch(subscription) is None:
        raise ValueError("Invalid approved release template.")
    withdrawal = secure_page(notification_page) + "#unsubscribe=" + capabilities.issue(subscription)
    message = _message(f"GraManna is available for {name}",
        f"GraManna is now available for {name}. You requested this platform launch announcement.",
        "View the approved store listing", url, "Ovis Alms Foundation")
    return Message(message.subject, message.text + f"\nUnsubscribe: {withdrawal}\n",
        message.html.replace("</body>", f"<p><a href=\"{escape(withdrawal, quote=True)}\">Unsubscribe</a></p></body>"))
