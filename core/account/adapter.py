from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_username, user_email, user_field
from allauth.utils import valid_email_or_none
from django.contrib.auth.models import User

class EzlSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        user = sociallogin.user
        if user.id:
            return
        if not user.email:
            return
        try:
            user = User.objects.get(email=user.email)  # if user exists, connect the account to the existing account and login
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass  

    def populate_user(self,
                      request,
                      sociallogin,
                      data):
        """
        Hook that can be used to further populate the user instance.

        For convenience, we populate several common fields.

        Note that the user instance being populated represents a
        suggested User instance that represents the social user that is
        in the process of being logged in.

        The User instance need not be completely valid and conflict
        free. For example, verifying whether or not the username
        already exists, is not a responsibility.
        """
        username = email = data.get('email')
        first_name = data.get('first_name')
        last_name = data.get('last_name')        
        name = data.get('name')
        user = sociallogin.user
        user_username(user, username or '')
        user_email(user, valid_email_or_none(email) or '')
        name_parts = (name or '').partition(' ')
        user_field(user, 'first_name', first_name or name_parts[0])
        user_field(user, 'last_name', last_name or name_parts[2])
        return user

