from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse_lazy

from AKModel.models import AKOrgaMessage


@receiver(post_save, sender=AKOrgaMessage)
def orga_message_saved_handler(sender, instance: AKOrgaMessage, **kwargs):
    # React to saved (thus new) Orga message by sending an email

    if settings.SEND_MAILS:
        host = 'https://' + settings.ALLOWED_HOSTS[0] if len(settings.ALLOWED_HOSTS) > 0 else 'http://127.0.0.1:8000'
        url = f"{host}{reverse_lazy('submit:ak_detail', kwargs={'pk': instance.ak.pk, 'event_slug': instance.ak.event.slug})}"

        mail = EmailMessage(
            f"[AKPlanning] New message for AK '{instance.ak}' ({instance.ak.event})",
            f"{instance.text}\n\n{url}",
            settings.DEFAULT_FROM_EMAIL,
            [instance.ak.event.contact_email]
        )
        mail.send(fail_silently=True)
