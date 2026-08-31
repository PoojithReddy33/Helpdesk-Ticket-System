from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import (
    HelpdeskTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """POST only. The one endpoint that must be reachable without a token."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    """Exchanges email + password for an access and a refresh token."""

    serializer_class = HelpdeskTokenObtainPairSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """The current user's profile, read and update."""

    serializer_class = UserSerializer

    def get_object(self):
        # No pk in the URL: the object is always whoever the token belongs to.
        return self.request.user
