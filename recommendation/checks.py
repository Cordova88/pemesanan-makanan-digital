"""Deployment checks do not read credentials or connect to external services."""
from django.conf import settings
from importlib.util import find_spec
from django.core.checks import CheckMessage, Error, Warning, Tags, register

from .services.security import UsageGuard


@register(Tags.security, deploy=True)
def chatbot_deployment_checks(app_configs: object = None, **kwargs: object) -> list[CheckMessage]:
    findings: list[CheckMessage] = []
    requirements = (
        (not settings.DEBUG, 'Disable DEBUG for production.'),
        (bool(settings.ALLOWED_HOSTS) and '*' not in settings.ALLOWED_HOSTS, 'Configure explicit ALLOWED_HOSTS.'),
        (getattr(settings, 'SESSION_COOKIE_SECURE', False), 'Enable secure session cookies over HTTPS.'),
        (getattr(settings, 'CSRF_COOKIE_SECURE', False), 'Enable secure CSRF cookies over HTTPS.'),
        (getattr(settings, 'SECURE_SSL_REDIRECT', False), 'Enable HTTPS redirection after configuring trusted proxy/TLS.'),
        (getattr(settings, 'SESSION_COOKIE_HTTPONLY', True), 'Keep session cookies HTTP-only.'),
    )
    for index, (passed, message) in enumerate(requirements, 1):
        if not passed:
            findings.append(Error(message, id=f'chatbot.E{index:03d}'))
    alias = getattr(settings, 'CHATBOT_CACHE_ALIAS', 'default')
    if settings.CACHES.get(alias, {}).get('BACKEND') not in UsageGuard.SHARED:
        findings.append(Error('Configure a dedicated shared atomic cache for chatbot limits.', id='chatbot.E007'))
    else:
        backend = settings.CACHES[alias]['BACKEND']
        binding = 'redis' if backend.endswith('RedisCache') else 'pymemcache' if backend.endswith('PyMemcacheCache') else 'pylibmc'
        if find_spec(binding) is None:
            findings.append(Error('Install and verify the chosen shared-cache binding before deployment.', id='chatbot.E009'))
    if getattr(settings, 'CHATBOT_REQUIRE_SHARED_CACHE', True) is not True:
        findings.append(Error('Keep shared-cache enforcement enabled in production.', id='chatbot.E008'))
    if 'django.contrib.sessions' not in settings.INSTALLED_APPS:
        findings.append(Error('Enable and migrate Django sessions for atomic chatbot state storage.', id='chatbot.E010'))
    if not getattr(settings, 'SECURE_HSTS_SECONDS', 0):
        findings.append(Warning('Plan and verify HSTS after HTTPS is confirmed; do not enable blindly.', id='chatbot.W001'))
    if getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax') not in {'Lax', 'Strict'}:
        findings.append(Warning('Review cross-site session-cookie policy for this deployment.', id='chatbot.W002'))
    return findings
