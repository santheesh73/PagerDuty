from rest_framework import pagination


class PageNumberPagination(pagination.PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100


class CursorPagination(pagination.CursorPagination):
    """Stable under concurrent inserts: new incidents arriving never shift a page boundary."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = ("-created_at", "-id")  # unique: a cursor over ties skips rows
