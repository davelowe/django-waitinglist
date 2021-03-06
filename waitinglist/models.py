import collections

from django.db import models
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.models import User

from account.models import SignupCode, SignupCodeResult
from account.signals import user_signed_up


class WaitingListEntry(models.Model):
    
    email = models.EmailField(_("email address"), unique=True)
    created = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    
    class Meta:
        verbose_name = _("waiting list entry")
        verbose_name_plural = _("waiting list entries")


Member = collections.namedtuple("Member", ["email", "signup_code", "user", "invited"])


class Cohort(models.Model):
    
    name = models.CharField(_("name"), max_length=35)
    created = models.DateTimeField(_("created"), default=timezone.now, editable=False)
    
    def members(self):
        members = []
        for scc in self.signupcodecohort_set.select_related():
            try:
                scr = SignupCodeResult.objects.get(signup_code=scc.signup_code_id)
            except SignupCodeResult.DoesNotExist:
                user = None
            else:
                user = scr.user
            members.append(
                Member(
                    scc.signup_code.email,
                    scc.signup_code,
                    user,
                    bool(scc.signup_code.sent)
                )
            )
        return members
    
    def member_counts(self):
        members = self.members()
        return {
            "total": len(members),
            "users": len([m for m in members if m.user is not None]),
            "pending": len([m.signup_code for m in members if not m.invited]),
        }
    
    def send_invitations(self):
        for sc in [m.signup_code for m in self.members() if not m.invited]:
            sc.send()
    
    def __unicode__(self):
        return self.name


class SignupCodeCohort(models.Model):
    """
    fetch cohort of a given signup code
        SignupCodeCohort.objects.select_related("cohort").get(signup_code__code="abc").cohort
        
    list of people waiting NOT on the site already or invited
        WaitingListEntry.objects.exclude(email__in=SignupCode.objects.values("email")).exclude(email__in=User.objects.values("email"))
    """
    signup_code = models.OneToOneField(SignupCode)
    cohort = models.ForeignKey(Cohort)


class UserCohort(models.Model):
    """
    Upon signup we create an instance of this model associating the new user and their cohort
    """
    user = models.OneToOneField(User)
    cohort = models.ForeignKey(Cohort)


@receiver(user_signed_up)
def handle_user_signup(sender, **kwargs):
    signup_code = kwargs["form"].cleaned_data["code"]
    # fetch the cohort for the signup code
    qs = SignupCodeCohort.objects.select_related("cohort")
    try:
        cohort = qs.get(signup_code__code=signup_code).cohort
        # create a UserCohort for user association to a cohort
        UserCohort.objects.create(user=kwargs["user"], cohort=cohort)
    except SignupCodeCohort.DoesNotExist:
        pass
