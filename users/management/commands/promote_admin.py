import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Profile

# Verified pbkdf2_sha256 hash from backups/database/neondrop_db_20260906_172418.json
# Corresponding to original backup password: 'neondrop123'
SMOKE_BACKUP_HASH = 'pbkdf2_sha256$1000000$xphIj091DQb3GtyrFXyEFG$B3Q+0Qu6bLIpIRcmSKwrpzUpJ+w5+/Qz33Stg4Tsszc='
SMOKE_ORIGINAL_PWD = 'neondrop123'


class Command(BaseCommand):
    help = "Promote or create administrator/superuser accounts with Django Admin access and credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames',
            nargs='*',
            default=['Smoke', 'admin'],
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
            usernames = ['Smoke', 'admin']

        # Also include any usernames defined in environment variables
        env_names = os.environ.get('ADMIN_USERNAMES', '')
        if env_names:
            for n in env_names.split(','):
                n_clean = n.strip()
                if n_clean and n_clean not in usernames:
                    usernames.append(n_clean)

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
            is_smoke = (name.lower() == 'smoke')
            user = User.objects.filter(username__iexact=name).first()

            if user:
                user.is_staff = True
                user.is_superuser = True
                user.is_active = True
                update_fields = ['is_staff', 'is_superuser', 'is_active']

                if is_smoke:
                    # Restore and preserve Smoke's original password from backup ('neondrop123')
                    if not user.check_password(SMOKE_ORIGINAL_PWD):
                        user.password = SMOKE_BACKUP_HASH
                        update_fields.append('password')
                        pwd_status = " (restored original backup password 'neondrop123')"
                    else:
                        pwd_status = " (original backup password 'neondrop123' verified)"
                elif update_existing and pwd:
                    user.set_password(pwd)
                    update_fields.append('password')
                    pwd_status = " (password updated via ADMIN_PASSWORD)"
                else:
                    pwd_status = " (existing password unchanged)"

                user.save(update_fields=update_fields)
                Profile.objects.get_or_create(user=user)
                self.stdout.write(
                    self.style.SUCCESS(
                        f" [OK] User '{user.username}' (id={user.id}) is Staff and Superuser with full /admin/ access!{pwd_status}"
                    )
                )
            else:
                email = os.environ.get('DJANGO_SUPERUSER_EMAIL', f'{name.lower()}@neondrop.gg')
                if is_smoke:
                    # Create Smoke with original backup credentials and profile data
                    new_user = User(
                        username='Smoke',
                        email=email,
                        password=SMOKE_BACKUP_HASH,
                        is_staff=True,
                        is_superuser=True,
                        is_active=True
                    )
                    new_user.save()
                    profile, _ = Profile.objects.get_or_create(user=new_user)
                    profile.balance = Decimal('1243.56')
                    profile.telegram_username = '@smoke_neondrop'
                    profile.avatar_url = 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150&auto=format&fit=crop&q=80'
                    profile.total_opened = 42
                    profile.total_winnings = Decimal('3890.50')
                    profile.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f" [CREATED] Superuser '{new_user.username}' (id={new_user.id}) restored with original backup credentials (password='neondrop123', balance=1243.56 UC)!"
                        )
                    )
                else:
                    admin_pwd = pwd or SMOKE_ORIGINAL_PWD
                    new_user = User.objects.create_superuser(username=name, email=email, password=admin_pwd)
                    Profile.objects.get_or_create(user=new_user)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f" [CREATED] Superuser '{new_user.username}' (id={new_user.id}) successfully created with password!"
                        )
                    )
