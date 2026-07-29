from django.urls import path

from .views import DecisionMermaViewSet, MermaResumenView, MermaViewSet

decision_list = DecisionMermaViewSet.as_view({"get": "list", "post": "create"})
decision_detail = DecisionMermaViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
merma_list = MermaViewSet.as_view({"get": "list", "post": "create"})
merma_detail = MermaViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path("api/decisiones-merma/", decision_list, name="decision-merma-list"),
    path("api/decisiones-merma/<int:pk>/", decision_detail, name="decision-merma-detail"),
    path("api/mermas/", merma_list, name="merma-list"),
    path("api/mermas/<int:pk>/", merma_detail, name="merma-detail"),
    path("api/mermas/resumen/", MermaResumenView.as_view(), name="merma-resumen"),
]
