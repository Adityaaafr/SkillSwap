from .models import ExchangeRequest


def pending_requests(request):
    """Number of requests waiting for the logged-in user's answer (shown in the navbar)."""
    if not request.user.is_authenticated:
        return {}
    count = ExchangeRequest.objects.filter(
        receiver=request.user, status=ExchangeRequest.Status.PENDING
    ).count()
    return {"pending_request_count": count}
