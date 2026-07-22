from django.db.models import Count
from rassa.models import FamiliaUsuario

dupes = (
    FamiliaUsuario.objects.values("fk_usuario", "fk_familia")
    .annotate(cnt=Count("id_familia_usuario"))
    .filter(cnt__gt=1)
)

total_deleted = 0
for d in dupes:
    qs = FamiliaUsuario.objects.filter(
        fk_usuario_id=d["fk_usuario"], fk_familia_id=d["fk_familia"]
    ).order_by("id_familia_usuario")
    ids = list(qs.values_list("id_familia_usuario", flat=True))
    for pk in ids[1:]:
        FamiliaUsuario.objects.filter(id_familia_usuario=pk).delete()
        total_deleted += 1
    print(f"Cleaned user={d['fk_usuario']} family={d['fk_familia']}: kept {ids[0]}, deleted {ids[1:]}")

print(f"Total duplicates deleted: {total_deleted}")
