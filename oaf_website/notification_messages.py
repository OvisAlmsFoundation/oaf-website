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
            raise diagnostic_error(ValueError, "_secure_page", "notification_page_https", stage="request")
        return value
    except Exception:
        pass
    raise diagnostic_error(ValueError("A configured secure notification page is required."), "_secure_page", "notification_page_https", stage="request") from None


def secure_page(value):
    """Legacy configuration is accepted; ordinary withdrawal uses its own page."""
    page = _secure_page(value, {"/gramanna.html", "/manage-notifications.html"})
    return page.rsplit("/", 1)[0] + "/manage-notifications.html"


def secure_management_page(value):
    page = _secure_page(value, {"/gramanna.html", "/confirm-email.html", "/manage-notifications.html"})
    return page.rsplit("/", 1)[0] + "/manage-notifications.html"


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


def verification_message(token, confirmation_page, *, management_token=None, unsubscribe_token=None):
    """Render a private fragment for the explicit, scanner-resistant public UI."""
    if type(token) is not str or HEX.fullmatch(token) is None:
        raise diagnostic_error(ValueError("Invalid confirmation capability."), "verification_message", "confirmation_template_token", stage="request")
    link = secure_confirmation_page(confirmation_page) + "#confirm-email=" + token
    message = _message("Confirm your OAF notification subscription",
        "Please confirm this email address for your requested OAF notifications.",
        "Confirm email", link,
        "This confirmation link expires 24 hours after your request. If you did not request this, ignore this email.")
    return management_footer(message, confirmation_page, management_token, unsubscribe_token)


def management_footer(message, page, token=None, unsubscribe_token=None):
    if token is None and unsubscribe_token is None:
        return message
    if token is not None:
        from .notification_management import TOKEN
        if type(token) is not str or TOKEN.fullmatch(token) is None:
            raise diagnostic_error(ValueError("Invalid management capability."), "management_footer", "management_template_token", stage="request")
        fragment = "#manage=" + token
    else:
        if type(unsubscribe_token) is not str or re.fullmatch(r"[0-9a-f]{64}\.[0-9a-f]{64}", unsubscribe_token) is None:
            raise diagnostic_error(ValueError("Invalid withdrawal capability."), "management_footer", "withdrawal_template_token", stage="request")
        fragment = "#unsubscribe=" + unsubscribe_token
    link = secure_management_page(page) + fragment
    label = "Manage Preferences" if token else "Unsubscribe"
    explanation = ("This management link expires 30 days after this email is prepared. "
        "Viewing or changing preferences requires email confirmation."
        if token else "This private link only unsubscribes the subscription created with it.")
    return Message(message.subject, message.text + f"\n{label}: {link}\n{explanation}\n",
        message.html.replace("</body>", f'<p><a href="{escape(link, quote=True)}">{label}</a></p>'
            f'<p>{escape(explanation)}</p></body>'))


def management_message(token, page):
    from .notification_management import TOKEN
    if type(token) is not str or TOKEN.fullmatch(token) is None:
        raise diagnostic_error(ValueError("Invalid management capability."), "management_message", "management_template_token", stage="request")
    return _message("Manage your OAF notifications",
        "Use your private link to view and change your selected OAF notifications or unsubscribe.",
        "Manage Preferences", secure_management_page(page) + "#manage=" + token,
        "This private management link expires 24 hours after your request. If you did not request it, ignore this email.")


def release_message(event, subscription, capabilities, notification_page, *, management_token=None):
    platform, release_id, url = event["platform"], event["release_id"], event["release_url"]
    if (event["content_version"] != CONTENT_VERSION or type(release_id) is not str
            or type(url) is not str or len(release_id) > 150):
        raise diagnostic_error(ValueError("Invalid approved release template."), "release_message", "release_template_platform", stage="request")
    if platform == "android":
        valid = (re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", release_id)
                 and url == "https://play.google.com/store/apps/details?id=" + release_id)
        name = "Android"
    elif platform == "ios":
        valid = (re.fullmatch(r"[1-9][0-9]{5,19}", release_id)
                 and url == "https://apps.apple.com/app/id" + release_id)
        name = "Apple iOS"
    else:
        raise diagnostic_error(ValueError("Invalid approved release template."), "release_message", "release_template_url", stage="request")
    if not valid or type(subscription) is not str or HEX.fullmatch(subscription) is None:
        raise diagnostic_error(ValueError("Invalid approved release template."), "release_message", "release_template_url", stage="request")
    message = _message(f"GraManna is available for {name}",
        f"GraManna is now available for {name}. You requested this platform launch announcement.",
        "View the approved store listing", url, "Ovis Alms Foundation")
    return management_footer(message, secure_page(notification_page), management_token,
                             capabilities.issue(subscription) if management_token is None else None)

from .notification_dispatch import diagnostic_error
