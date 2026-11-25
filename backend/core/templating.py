"""
Krishi Bazaar — Jinja2 rendering for FastAPI.
The HTML templates use Django-style tags ({% url %}, {% static %}, {% csrf_token %},
`|date:"d M Y"`); this module translates them so the templates render under Jinja2.
"""
import re
from datetime import datetime

import jinja2
from fastapi.responses import HTMLResponse
from jinja2 import nodes
from jinja2.ext import Extension
from markupsafe import Markup, escape

from .auth import CART_SESSION_KEY
from .config import DEBUG, TEMPLATES_DIR
from .security import CSRF_FIELD, csrf_token

STATE_CHOICES = [
    ("", "Select State"), ("Karnataka", "Karnataka"), ("Maharashtra", "Maharashtra"),
    ("Kerala", "Kerala"), ("Tamil Nadu", "Tamil Nadu"), ("Andhra Pradesh", "Andhra Pradesh"),
    ("Telangana", "Telangana"), ("Gujarat", "Gujarat"), ("Punjab", "Punjab"),
    ("Delhi", "Delhi"), ("Uttar Pradesh", "Uttar Pradesh"), ("Himachal Pradesh", "Himachal Pradesh"),
    ("Jammu & Kashmir", "Jammu & Kashmir"), ("West Bengal", "West Bengal"),
]
ADDRESS_TYPE_CHOICES = [
    ("home", "Home"), ("work", "Office / Work"),
    ("warehouse", "Estate / Warehouse"), ("other", "Other"),
]


class DjangoCompatExtension(Extension):
    """
    Extends Jinja2 to support Django tags seamlessly:
    {% csrf_token %}, {% load ... %}, {% static '...' %}, {% url '...' %}
    """
    tags = {"url", "csrf_token", "load", "static"}

    def parse(self, parser):
        tag = parser.stream.current.value
        lineno = next(parser.stream).lineno

        if tag == "csrf_token":
            return nodes.Output([
                self.call_method("_csrf_input", [nodes.ContextReference()], lineno=lineno)
            ], lineno=lineno)

        if tag == "load":
            while parser.stream.current.type != "block_end":
                next(parser.stream)
            return nodes.Output([nodes.Const("")], lineno=lineno)

        if tag == "static":
            path_expr = parser.parse_expression()
            return nodes.Output([
                self.call_method("_resolve_static", [path_expr], lineno=lineno)
            ], lineno=lineno)

        if tag == "url":
            name_expr = parser.parse_expression()
            args = []
            while parser.stream.current.type != "block_end":
                args.append(parser.parse_expression())
            return nodes.Output([
                self.call_method("_resolve_url", [name_expr, nodes.List(args)], lineno=lineno)
            ], lineno=lineno)

    def _csrf_input(self, context):
        token = context.get("csrf_value", "")
        return Markup(f'<input type="hidden" name="{CSRF_FIELD}" value="{escape(token)}">')

    def _resolve_static(self, path):
        return f"/static/{path.lstrip('/')}"

    def _resolve_url(self, name, args):
        url_map = {
            "home": "/",
            "cart_detail": "/cart/",
            "cart_clear": "/cart/clear/",
            "checkout": "/checkout/",
            "cart_checkout": "/checkout/",
            "services": "/services/",
            "equipment_rental": "/equipment-rental/",
            "crop_health": "/crop-health/",
            "contact": "/contact/",
            "register": "/register/",
            "login": "/login/",
            "logout": "/logout/",
            "buyer_orders": "/buyer/orders/",
            "address_list": "/addresses/",
            "address_add": "/addresses/add/",
            "farmer_dashboard": "/farmer/dashboard/",
            "product_create": "/farmer/product/add/",
            "admin_dashboard": "/admin-dashboard/",
            "forgot_password": "/forgot-password/",
            "google_login": "/auth/google/login/",
            "google_callback": "/auth/google/callback/",
            "otp_send": "/auth/otp/send/",
            "otp_verify": "/auth/otp/verify/",
            "otp_login": "/auth/otp/login/",
        }
        if url_map.get(name):
            return url_map[name]
        if name == "product_review" and args:
            return f"/product/{args[0]}/review/"
        if name == "product_detail" and args:
            return f"/product/{args[0]}/"
        if name == "place_order" and args:
            return f"/product/{args[0]}/order/"
        if name == "cart_add" and args:
            return f"/cart/add/{args[0]}/"
        if name == "cart_update" and args:
            return f"/cart/update/{args[0]}/"
        if name == "cart_remove" and args:
            return f"/cart/remove/{args[0]}/"
        if name == "product_edit" and args:
            return f"/farmer/product/{args[0]}/edit/"
        if name == "product_delete" and args:
            return f"/farmer/product/{args[0]}/delete/"
        if name == "order_tracking" and args:
            return f"/order/{args[0]}/tracking/"
        if name == "dispatch_order" and args:
            return f"/farmer/order/{args[0]}/dispatch/"
        if name == "update_delivery_step" and len(args) >= 2:
            return f"/farmer/order/{args[0]}/delivery-step/{args[1]}/"
        if name == "update_order" and len(args) >= 2:
            return f"/farmer/order/{args[0]}/{args[1]}/"
        if name == "address_edit" and args:
            return f"/addresses/{args[0]}/edit/"
        if name == "address_delete" and args:
            return f"/addresses/{args[0]}/delete/"
        if name == "address_set_default" and args:
            return f"/addresses/{args[0]}/set-default/"
        return f"/{name}/"


def django_to_jinja(src: str) -> str:
    """Preprocess Django template syntax into Jinja2 syntax."""
    # Convert {% empty %} in for loops to {% else %}
    src = re.sub(r'\{%\s*empty\s*%\}', '{% else %}', src)

    # Convert Django forloop variables to Jinja2 loop variables
    src = re.sub(r'\bforloop\.first\b', 'loop.first', src)
    src = re.sub(r'\bforloop\.last\b', 'loop.last', src)
    src = re.sub(r'\bforloop\.counter0\b', 'loop.index0', src)
    src = re.sub(r'\bforloop\.counter\b', 'loop.index', src)

    # Convert filter:arg to filter(arg)
    def filter_replace(match):
        full = match.group(0)
        def sub_one(m):
            fname = m.group(1)
            farg = m.group(2)
            return f"|{fname}({farg})"
        return re.sub(r'\|([a-zA-Z0-9_]+):(".*?"|\'.*?\'|[a-zA-Z0-9_.]+)', sub_one, full)

    return re.sub(r'(\{\{.*?\}\}|\{%.*?%\})', filter_replace, src, flags=re.DOTALL)


class PreprocessingLoader(jinja2.FileSystemLoader):
    """Jinja2 loader that transforms Django tags dynamically on read."""
    def get_source(self, environment, template):
        src, filename, uptodate = super().get_source(environment, template)
        return django_to_jinja(src), filename, uptodate


# Custom Filters
_DATE_TOKENS = {
    "d": "%d", "j": "%d", "D": "%a", "l": "%A", "m": "%m", "n": "%m", "M": "%b", "N": "%b",
    "F": "%B", "y": "%y", "Y": "%Y", "H": "%H", "G": "%H", "h": "%I", "g": "%I", "i": "%M",
    "s": "%S", "A": "%p", "a": "%p",
}


def format_date(value, fmt="d M Y, h:i A"):
    """Django-style `date` filter (d M Y, h:i A ...)."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    try:
        return value.strftime("".join(_DATE_TOKENS.get(ch, ch) for ch in fmt))
    except (ValueError, AttributeError):
        return str(value)


def escapejs(value) -> str:
    """Make a value safe inside a JavaScript string literal (Django's escapejs)."""
    return "".join(
        f"\\u{ord(ch):04X}" if ch in "\\'\"<>&=-;\u2028\u2029" or ord(ch) < 32 else ch
        for ch in str(value)
    )


def stringformat(val, fmt):
    try:
        return ("%" + str(fmt)) % val
    except Exception:
        return str(val)


def pluralize(val, arg="s"):
    try:
        return "" if int(val) == 1 else arg
    except Exception:
        return ""


# Initialize Jinja2 Environment
jinja_env = jinja2.Environment(
    loader=PreprocessingLoader([str(TEMPLATES_DIR)]),
    extensions=[DjangoCompatExtension],
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    auto_reload=DEBUG,
)

jinja_env.filters["date"] = format_date
jinja_env.filters["stringformat"] = stringformat
jinja_env.filters["pluralize"] = pluralize
jinja_env.filters["escapejs"] = escapejs


class AnonymousUser:
    is_authenticated = False
    is_staff = False
    username = ""
    first_name = ""
    profile = None
    get_full_name = ""


class RequestCompat:
    """Wrapper around starlette Request to support request.GET and other Django conventions."""
    def __init__(self, raw_request):
        self._raw = raw_request
        self.query_params = raw_request.query_params
        self.GET = raw_request.query_params
        self.POST = {}
        self.session = raw_request.session

    def __getattr__(self, name):
        return getattr(self._raw, name)


class FormFieldProxy:
    def __init__(self, name="field", value="", label=None, field_type="text", choices=None, errors=None, help_text=""):
        self.name = name
        self.value = value if value is not None else ""
        self.label = label or name.replace("_", " ").title()
        self.field_type = field_type
        self.choices = choices or []
        self.errors = errors or []
        self.help_text = help_text

    def __bool__(self):
        return bool(self.value or self.errors)

    def __str__(self):
        name, value = escape(self.name), escape(self.value)
        if self.field_type == "select" and self.choices:
            opts = "\n".join(
                f'<option value="{escape(c[0])}" {"selected" if str(self.value) == str(c[0]) else ""}>{escape(c[1])}</option>'
                for c in self.choices
            )
            return f'<select name="{name}" class="lux-input">{opts}</select>'
        if self.field_type == "textarea":
            return f'<textarea name="{name}" class="lux-input" rows="3">{value}</textarea>'
        return f'<input type="{escape(self.field_type)}" name="{name}" value="{value}" class="lux-input">'

    def __html__(self):
        return str(self)


class FormProxy:
    """Provides graceful fallback for templates expecting Django Form objects."""
    DEFAULT_STATE_CHOICES = STATE_CHOICES
    DEFAULT_TYPE_CHOICES = ADDRESS_TYPE_CHOICES

    def __init__(self, non_field_errors=None, values=None):
        self.non_field_errors = non_field_errors or []
        self._values = values or {}
        self._fields = {}
        self.fields = {
            "state": type("ChoiceObj", (), {"choices": self.DEFAULT_STATE_CHOICES})(),
            "address_type": type("ChoiceObj", (), {"choices": self.DEFAULT_TYPE_CHOICES})(),
        }

    def __getattr__(self, name):
        if name not in self._fields:
            raw = self._values.get(name, "")
            if isinstance(raw, dict) and "value" in raw:
                val = raw.get("value", "")
                errs = raw.get("errors", [])
            elif isinstance(raw, FormFieldProxy):
                return raw
            else:
                val = raw
                errs = []
            self._fields[name] = FormFieldProxy(name=name, value=val, errors=errs)
        return self._fields[name]

    def __getitem__(self, name):
        return getattr(self, name)

    def __iter__(self):
        if not self._values:
            yield FormFieldProxy(name="quantity", value="", label="Purchase Quantity", field_type="number")
        else:
            for k in self._values.keys():
                if k != "fields":
                    yield getattr(self, k)


class FlashMessage:
    def __init__(self, text, tags="info"):
        self.text = text
        self.tags = tags

    def __str__(self):
        return self.text  # no __html__: messages can contain user input, so Jinja must escape them


def render_template(template_name: str, context: dict, request=None, status_code: int = 200) -> HTMLResponse:
    """Helper to render a template and wrap it into a FastAPI HTMLResponse."""
    ctx = dict(context)
    if "form" not in ctx:
        ctx["form"] = FormProxy()
    elif isinstance(ctx["form"], dict) and not isinstance(ctx["form"], FormProxy):
        ctx["form"] = FormProxy(values=ctx["form"])

    if request:
        compat_request = RequestCompat(request)
        ctx["request"] = compat_request
        ctx["csrf_value"] = csrf_token(request.session)

        if "user" not in ctx or ctx["user"] is None:
            user_in_state = getattr(request.state, "user", None)
            ctx["user"] = user_in_state if user_in_state else AnonymousUser()

        if "cart_count" not in ctx:
            cart = request.session.get(CART_SESSION_KEY, {})
            ctx["cart_count"] = len(cart)

        if "messages" not in ctx:
            raw_messages = request.session.pop("_flash_messages", [])
            ctx["messages"] = [
                FlashMessage(m["text"], m.get("tags", "info"))
                for m in raw_messages
                if isinstance(m, dict) and "text" in m
            ]
    else:
        ctx.setdefault("request", None)
        ctx.setdefault("csrf_value", "")
        ctx.setdefault("messages", [])
        ctx.setdefault("cart_count", 0)
        if "user" not in ctx or ctx["user"] is None:
            ctx["user"] = AnonymousUser()

    template = jinja_env.get_template(template_name)
    html_content = template.render(**ctx)
    return HTMLResponse(content=html_content, status_code=status_code)


def add_flash_message(request, message: str, tag: str = "success"):
    """Store flash message in session (JSON-serializable)."""
    msgs = request.session.get("_flash_messages", [])
    msgs.append({"text": str(message), "tags": tag})
    request.session["_flash_messages"] = msgs
