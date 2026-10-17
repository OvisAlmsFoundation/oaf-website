"""Internal bounded release processor. No route, worker, scheduler or activation."""

from dataclasses import dataclass

from .brevo import BrevoAdapter, BrevoConfig, BrevoConfigurationError, ProviderOutcome
from .notification_messages import release_message, secure_page
from .notifications import UnsubscribeCapabilities


@dataclass(frozen=True)
class BatchResult:
    status: str
    processed: int = 0


class ReleaseDispatcher:
    def __init__(self, store, config, notification_page, *, transport=None):
        if type(config) is not BrevoConfig or config.environment != store.environment:
            raise BrevoConfigurationError("Brevo configuration must match the delivery environment.")
        self.store = store
        self.page = secure_page(notification_page)
        self.capabilities = UnsubscribeCapabilities(store.secret)
        self.adapter = BrevoAdapter(config, transport=transport)

    def process(self, event_id, *, limit=20):
        # Validate before persistence or provider access. No recipient input is accepted.
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Release batches require 1 to 20 recipients.")
        processed = 0
        try:
            self.store.recover_event(event_id)
            self.store.prepare_event(event_id)
            event, subscriptions = self.store.dispatch_batch(event_id, limit)
            if event is None:
                return BatchResult("unavailable")
            for subscription in subscriptions:
                message = release_message(event, subscription, self.capabilities, self.page)
                claim = self.store.claim(event_id, subscription)
                if claim is None:
                    continue
                # Commit and recheck immediately before the only possible HTTP call.
                email = self.store.begin_submission(event_id, subscription, claim)
                if email is None:
                    continue
                try:
                    outcome = self.adapter.submit(email, message)
                except Exception:
                    # An injected adapter may already have posted; hold rather than repeat.
                    outcome = ProviderOutcome("submission_unknown")
                if not self.store.record_outcome(event_id, subscription, claim,
                                                outcome.outcome, outcome.message_id):
                    return BatchResult("unavailable", processed)
                processed += 1
            return BatchResult("processed", processed)
        except Exception:
            # Includes uncertain commits. Never post after a failed dispatch commit,
            # retry a POST here, or disclose email/token/SQL/credential/provider errors.
            return BatchResult("unavailable", processed)
