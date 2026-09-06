import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Profile


class Command(BaseCommand):
    help = "Promote a user to superuser and staff (Django Admin access) without changing password or data."

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames',
            nargs='*',
            default=['Smoke'],
            help='Username(s) to grant is_staff=True, is_superuser=True, is_active=True.'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=None,
            help='Optional password if creating the user from scratch.'
        )

    def handle(self, *args, **options):
        usernames = options['usernames']
        if not usernames:
            usernames = ['Smoke']

        # Also include any usernames defined in environment variables
        env_names = os.environ.get('ADMIN_USERNAMES', '')
        if env_names:
            for n in env_names.split(','):
                n_clean = n.strip()
                if n_clean and n_clean not in usernames:
                    usernames.append(n_clean)

        for name in usernames:
            user = User.objects.filter(username__iexact=name).first()
            if user:
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                user.save(update_fields=['is_staff', 'is_superuser', 'is_active'])
                Profile.objects.get_or_create(user=user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f" [OK] User '{user.username}' (id={user.id}) is now Staff and Superuser with full /admin/ access!"
                    )
                )
            else:
                # User does not exist yet. Check if password is provided or in env
                pwd = options['password'] or os.environ.get('DJANGO_SUPERUSER_PASSWORD')
                if pwd:
                    email = os.environ.get('DJANGO_SUPERUSER_EMAIL', f'{name.lower()}@neondrop.gg')
                    new_user = User.objects.create_superuser(username=name, email=email, password=pwd)
                    Profile.objects.get_or_create(user=new_user)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f" [CREATED] Superuser '{new_user.username}' (id={new_user.id}) successfully created!"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f" [NOTE] User '{name}' does not exist yet. When '{name}' registers or logs in, they will be automatically granted Staff & Superuser rights."
                        )
                    )
