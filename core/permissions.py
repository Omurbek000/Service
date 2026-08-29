# Разрешения (permissions)
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOwner(BasePermission):
    """Разрешает доступ только владельцу объекта.

    Ожидается, что у объекта есть поле owner.
    """

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user


class IsJobOwner(BasePermission):
    """Доступ только владельцу задачи (владелец через video)."""

    def has_object_permission(self, request, view, obj):
        return obj.video.owner == request.user
