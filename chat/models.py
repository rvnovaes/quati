from django.db import models
from core.models import Audit, OfficeMixin, Office, Company
from django.contrib.auth.models import User

# Create your models here.


class Chat(Audit):
    company = models.ForeignKey(
        Company, related_name='company_chats', null=True, blank=True, on_delete=models.PROTECT)
    offices = models.ManyToManyField(Office, related_name='chats')
    label = models.SlugField(unique=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    back_url = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-alter_date']

    def __str__(self):
        return self.label


class Message(Audit):
    chat = models.ForeignKey(Chat, related_name='messages', on_delete=models.PROTECT)
    message = models.TextField(verbose_name='Mensagem')

    class Meta:
        ordering = ['create_date']

    def __str__(self):
        return self.message


class UserByChat(Audit):
    user_by_chat = models.ForeignKey(User, verbose_name='Usuario', on_delete=models.PROTECT)
    chat = models.ForeignKey(Chat, verbose_name='chat', related_name='users', on_delete=models.PROTECT)

    def __str__(self):
        return self.user_by_chat.username

    class Meta:
        indexes = [models.Index(fields=['user_by_chat_id'])]


class UnreadMessage(Audit):
    message = models.ForeignKey(Message, on_delete=models.PROTECT)
    user_by_message = models.ForeignKey(UserByChat, on_delete=models.PROTECT)

    def __str__(self):
        return self.user_by_message.user_by_chat.username

    class Meta:
        indexes = [models.Index(fields=['user_by_message_id'])]
