from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """The logged-in user's own profile."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "role", "created_at"]
        # Nobody may promote themselves by editing their own profile.
        read_only_fields = ["id", "email", "role", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, validators=[validate_password], style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone",
                  "password", "password_confirm"]

    def validate(self, attrs):
        """Object-level validation: runs after every field has passed."""
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields didn't match."}
            )
        return attrs

    def create(self, validated_data):
        # Not a real field on the model, so drop it before creating.
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")

        # Public signup always creates a customer. Roles are granted by an
        # admin, never chosen by the person registering.
        return User.objects.create_user(
            password=password, role=User.Role.CUSTOMER, **validated_data
        )


class HelpdeskTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds the user's role and email into the token payload itself."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Returned alongside the tokens so the frontend can render immediately
        # without decoding the JWT.
        data["user"] = UserSerializer(self.user).data
        return data
