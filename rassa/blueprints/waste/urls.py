from django.urls import path

from .views import DecisionMermaViewSet, MermaViewSet

decision_list = DecisionMermaViewSet.as_view({"get": "list", "post": "create"})
decision_detail = DecisionMermaViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)
merma_list = MermaViewSet.as_view({"get": "list", "post": "create"})

urlpatterns = [
    path("api/decisiones-merma/", decision_list, name="decision-merma-list"),
    path("api/decisiones-merma/<int:pk>/", decision_detail, name="decision-merma-detail"),
    path("api/mermas/", merma_list, name="merma-list"),
]
