# Пагинация
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Стандартная пагинация: 10 объектов на страницу, максимум 100."""

    page_size = 10
    max_page_size = 100
    page_size_query_param = 'page_size'
