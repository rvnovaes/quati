import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from chat.models import Chat, Message, UserByChat, UnreadMessage

BROADCAST_GROUP = 'chat'


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket do chat. O cliente conecta em /ws/?label=<label do chat> e envia JSON
    {chat, label, text, user_id?}. A mensagem é persistida e retransmitida ao grupo
    do label (mesmo formato de resposta do consumer antigo, consumido pelo AngularJS).
    """

    async def connect(self):
        params = parse_qs(self.scope.get('query_string', b'').decode('utf-8'))
        labels = params.get('label')
        if not labels:
            await self.close()
            return
        self.label = labels[0]
        await self.channel_layer.group_add(self.label, self.channel_name)
        await self.channel_layer.group_add(BROADCAST_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, 'label', None):
            await self.channel_layer.group_discard(self.label, self.channel_name)
        await self.channel_layer.group_discard(BROADCAST_GROUP, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data)
        except (TypeError, json.JSONDecodeError):
            await self.channel_layer.group_send(
                BROADCAST_GROUP, {'type': 'chat.message', 'text': text_data})
            return
        user = self.scope.get('user')
        data = await self.persist_message(data, user.pk if user and user.is_authenticated else None)
        await self.channel_layer.group_send(
            data.get('label') or self.label, {'type': 'chat.message', 'text': json.dumps(data)})

    async def chat_message(self, event):
        await self.send(text_data=event['text'])

    @database_sync_to_async
    def persist_message(self, data, user_pk):
        if data.get('user_id'):
            user_message = User.objects.get(pk=data.get('user_id'))
        else:
            user_message = User.objects.get(pk=user_pk)
        chat, _ = Chat.objects.get_or_create(pk=int(data.get('chat')))
        chat_message = chat.messages.create(create_user=user_message, message=data.get('text'))
        chat.save()
        for user in UserByChat.objects.filter(~Q(user_by_chat=user_message), chat=chat, is_active=True):
            UnreadMessage.objects.create(
                create_user=user_message, user_by_message=user, message=chat_message)
        data['create_date'] = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')
        data['create_user_id'] = chat_message.create_user.id
        data['create_user__username'] = chat_message.create_user.username
        data['message'] = chat_message.message
        return data
