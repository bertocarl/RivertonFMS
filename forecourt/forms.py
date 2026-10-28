from common.forms import StyledModelForm

from .models import Nozzle, Product, Pump, Tank


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "kind", "unit", "selling_price", "cost_price", "reorder_level", "is_active"]


class TankForm(StyledModelForm):
    class Meta:
        model = Tank
        fields = ["station", "name", "product", "capacity", "minimum_level", "current_level", "is_active"]


class PumpForm(StyledModelForm):
    class Meta:
        model = Pump
        fields = ["station", "number", "ifsf_node_id", "is_active"]


class NozzleForm(StyledModelForm):
    class Meta:
        model = Nozzle
        fields = ["pump", "number", "tank", "is_active"]
