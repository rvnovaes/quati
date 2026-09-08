import os
import os.path
import shutil
import json
import logging
from django.conf import settings
from django.contrib import messages
from core.views import CustomLoginRequiredView
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.db import IntegrityError
from core.views import AuditFormMixin, MultiDeleteViewMixin, SingleTableViewMixin
from core.messages import CREATE_SUCCESS_MESSAGE, DELETE_SUCCESS_MESSAGE, UPDATE_SUCCESS_MESSAGE, \
    record_from_wrong_office, success_delete, integrity_error_delete, DELETE_EXCEPTION_MESSAGE
from core.utils import get_office_session
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View
from django.views.generic.edit import CreateView, UpdateView
from . import utils
from .forms import UploadFileForm, DefaultAttachmentRuleForm, DefaultAttachmentRuleCreateForm
from .tables import DefaulAttachmentRuleTable
from .models import Attachment, DefaultAttachmentRule

logger = logging.getLogger('django')


##
# Utils
##
def make_response(status=200, content_type='text/plain', content=None):
    """ Construct a response to an upload request.
    Success is indicated by a status of 200 and { "success": true }
    contained in the content.
    Also, content-type is text/plain by default since IE9 and below chokes
    on application/json. For CORS environments and IE9 and below, the
    content-type needs to be text/html.
    """
    response = HttpResponse()
    response.status_code = status
    response['Content-Type'] = content_type
    response.content = content
    return response


##
# Views
##
class AttachmentFormMixin(object):

    def form_valid(self, form):
        if self.model.use_upload:
            files = self.request.FILES.getlist('file')
            if files:
                instance = form.save(commit=False)
                for f in files:
                    model_name = self.model._meta.app_label.lower() + '.' + \
                                 self.model.__name__.lower()
                    attachment = Attachment(
                        model_name=model_name,
                        object_id=instance.id,
                        file=f,
                        create_user_id=self.request.user.id
                    )
                    attachment.save()
            form.save()
        return True


class UploadView(View):
    """
    View which will handle all upload requests sent by Uploader.
    """

    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(UploadView, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        """A POST request. Validate the form and then handle the upload
        based ont the POSTed data. Does not handle extra parameters yet.
        """
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            data = request.POST

            for file in request.FILES.getlist('file'):
                    attachment = Attachment(
                        model_name=data.get('model_name'),
                        object_id=data.get('object_id'),
                        file=file,
                        exibition_name=file.name,
                        create_user_id=request.user.id
                    )
                    attachment.save()
            return make_response(content=json.dumps({'success': True,
                                                     'model_name': data.get('model_name'),
                                                     'object_id': data.get('object_id')}))
        else:
            return make_response(status=400,
                                 content=json.dumps({
                                     'success': False,
                                     'error': '%s' % repr(form.errors)
                                 }))


def ajax_get_attachments(request):
    attachments = Attachment.objects.filter(
        model_name=request.GET.get('model_name'),
        object_id=request.GET.get('object_id')
    )
    ret = []
    for attachment in attachments:
        ret.append({
            'exibition_name': attachment.exibition_name,
            'object_id': attachment.object_id,
            'model_name': attachment.model_name,
            'pk': attachment.pk,
            'url': attachment.file.name,
            'filename': attachment.filename,
            'user': attachment.create_user.username,
            'data': attachment.create_date.strftime('%d/%m/%Y %H:%M'),
        })

    data = {
        'total_records': attachments.count(),
        'files': ret
    }

    return JsonResponse(data, safe=False)


@login_required
def ajax_drop_attachment(request, pk):
    attachment = Attachment.objects.get(pk=pk)

    try:
        attachment.delete()
        data = {'is_deleted': True,
                'message': success_delete()
                }

    except IntegrityError:
        data = {'is_deleted': False,
                'message': integrity_error_delete()
                }
    except Exception:
        data = {'is_deleted': False,
                'message': DELETE_EXCEPTION_MESSAGE,
                }

    return JsonResponse(data, safe=False)


class DefaultAttachmentRuleListView(CustomLoginRequiredView, SingleTableViewMixin):
    model = DefaultAttachmentRule
    table_class = DefaulAttachmentRuleTable
    ordering = ('id', )
    paginate_by = 30


class DefaultAttachmentRuleCreateView(AuditFormMixin, CreateView):
    model = DefaultAttachmentRule
    form_class = DefaultAttachmentRuleCreateForm
    success_url = reverse_lazy('ecm:defaultattachmentrule_list')
    success_message = CREATE_SUCCESS_MESSAGE
    object_list_url = 'ecm:defaultattachmentrule_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class DefaultAttachmentRuleUpdateView(AuditFormMixin, UpdateView):
    model = DefaultAttachmentRule
    form_class = DefaultAttachmentRuleForm
    success_url = reverse_lazy('ecm:defaultattachmentrule_list')
    success_message = UPDATE_SUCCESS_MESSAGE
    template_name_suffix = '_update_form'
    object_list_url = 'ecm:defaultattachmentrule_list'

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw


class DefaultAttachmentRuleDeleteView(AuditFormMixin, MultiDeleteViewMixin):
    model = DefaultAttachmentRule
    success_url = reverse_lazy('ecm:defaultattachmentrule_list')
    success_message = DELETE_SUCCESS_MESSAGE.format(
        model._meta.verbose_name_plural)
    object_list_url = 'ecm:defaultattachmentrule_list'

