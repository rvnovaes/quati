"""
Tag {% querystring %} compatível com a antiga do django-tables2 (removida na versão 3),
aceitando chaves dinâmicas: {% querystring table.prefixed_order_by_field=column.order_by_alias.next %}.
Sobrescreve a tag builtin do Django (que só aceita chaves literais) quando esta biblioteca é carregada.
"""
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


class QuerystringNode(template.Node):
    def __init__(self, updates, removals):
        self.updates = updates
        self.removals = removals

    def render(self, context):
        request = context.get('request')
        if request is None:
            return ''
        params = request.GET.copy()
        for key_expr, value_expr in self.updates:
            key = key_expr.resolve(context)
            value = value_expr.resolve(context)
            if value is None or value == '':
                params.pop(str(key), None)
            else:
                params[str(key)] = value
        for key_expr in self.removals:
            params.pop(str(key_expr.resolve(context)), None)
        return escape('?' + params.urlencode())


@register.tag
def querystring(parser, token):
    bits = token.split_contents()[1:]
    updates, removals = [], []
    if 'without' in bits:
        idx = bits.index('without')
        bits, removal_bits = bits[:idx], bits[idx + 1:]
        removals = [parser.compile_filter(b) for b in removal_bits]
    for bit in bits:
        if '=' not in bit:
            raise template.TemplateSyntaxError("querystring: esperado chave=valor, recebido %r" % bit)
        key, value = bit.split('=', 1)
        updates.append((parser.compile_filter(key), parser.compile_filter(value)))
    return QuerystringNode(updates, removals)
