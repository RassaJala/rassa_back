from django.contrib import admin

from rassa.models import DecisionMerma, Merma


@admin.register(DecisionMerma)
class DecisionMermaAdmin(admin.ModelAdmin):
    list_display = ["id_decision", "decision", "estado", "creado_en"]
    list_filter = ["estado"]
    search_fields = ["decision"]


@admin.register(Merma)
class MermaAdmin(admin.ModelAdmin):
    list_display = ["id_merma", "fk_pedido", "fk_producto_semanal", "cantidad", "fk_decision", "creado_en", "estado"]
    list_filter = ["fk_decision", "estado", "fk_pedido"]
    search_fields = ["motivo"]
    date_hierarchy = "creado_en"
