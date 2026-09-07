import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Profile


class Command(BaseCommand):
    help = "Promote or create administrator/superuser accounts with Django Admin access and credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames',
            nargs='*',
            default=['admin', 'Smoke'],
            help='Username(s) to grant is_staff=True, is_superuser=True, is_active=True.'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Password to set when creating or updating the administrator.'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            default=False,
            help='Update password and permissions for existing users as well.'
        )

    def handle(self, *args, **options):
        usernames = options['usernames']
        if not usernames:
            usernames = ['admin', 'Smoke']

        # Also include any usernames defined in environment variables
        env_names = os.environ.get('ADMIN_USERNAMES', '')
        if env_names:
            for n in env_names.split(','):
                n_clean = n.strip()
                if n_clean and n_clean not in usernames:
                    usernames.append(n_clean)

        # Read password from env vars only — never hardcode in source!
        # Set ADMIN_PASSWORD in Render Dashboard -> Environment Variables.
        pwd = (
            options['password']
            or os.environ.get('ADMIN_PASSWORD')
            or os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        )
        update_existing = (
            options['update_existing']
            or os.environ.get('ADMIN_UPDATE_EXISTING', '').lower() in ('1', 'true', 'yes')
        )

        for name in usernames:
            user = User.objects.filter(username__iexact=name).first()
            if user:
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                update_fields = ['is_staff', 'is_superuser', 'is_active']
                if update_existing and pwd:
                    user.set_password(pwd)
                    update_fields.append('password')
                user.save(update_fields=update_fields)
                Profile.objects.get_or_create(user=user)
                pwd_status = " (password updated via ADMIN_PASSWORD)" if (update_existing and pwd) else " (existing password unchanged)"
                self.stdout.write(
                    self.style.SUCCESS(
                        f" [OK] User '{user.username}' (id={user.id}) is Staff and Superuser with full /admin/ access!{pwd_status}"
                    )
                )
            else:
                if not pwd:
                    self.stdout.write(
                        self.style.WARNING(
                            f" [SKIP] User '{name}' does not exist and ADMIN_PASSWORD env var is not set. "
                            f"Set ADMIN_PASSWORD in Render Dashboard to create this superuser automatically."
                        )
                    )
                    continue
                email = os.environ.get('DJANGO_SUPERUSER_EMAIL', f'{name.lower()}@neondrop.gg')
                new_user = User.objects.create_superuser(username=name, email=email, password=pwd)
                Profile.objects.get_or_create(user=new_user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f" [CREATED] Superuser '{new_user.username}' (id={new_user.id}) successfully created!"
                    )
                )
