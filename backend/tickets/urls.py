from rest_framework.routers import DefaultRouter

from .views import CommentViewSet, TicketViewSet

# The router inspects each ViewSet and generates the standard REST URLs
# for it, so we never write them by hand.
router = DefaultRouter()
router.register(r"tickets", TicketViewSet, basename="ticket")
router.register(r"comments", CommentViewSet, basename="comment")

urlpatterns = router.urls
