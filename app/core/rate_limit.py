from slowapi import Limiter
from slowapi.util import get_remote_address

# Named limiters mirror app/Providers/AppServiceProvider.php's RateLimiter::for(...) definitions.
# Laravel keys most of these by authenticated-user-id-or-IP; none of the routes in this
# port are authenticated, so keying purely by client IP is equivalent here.
limiter = Limiter(key_func=get_remote_address)

PUBLIC_FORMS = "5/minute"  # RateLimiter::for('public-forms') — club sign-up forms
VOTES = "20/minute"  # RateLimiter::for('votes') — poll/quiz/question answer submissions
SEARCH = "60/minute"  # RateLimiter::for('search') — /api/search
