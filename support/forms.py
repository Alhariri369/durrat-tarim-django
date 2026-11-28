from django import forms
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

from catalog.utils import normalize_arabic

arabic_phone_validator = RegexValidator(
    regex=r"^05\d{8}$",
    message=_("أدخل رقم جوال سعودي صحيح يبدأ بـ 05"),
)

arabic_name_validator = RegexValidator(
    regex=r"^[\u0621-\u064A\s\-\.]{3,}$",
    message=_("الرجاء إدخال اسم باللغة العربية مكون من 3 أحرف على الأقل"),
)

_INPUT_CLASSES = (
    "w-full rounded-xl border border-secondary/15 bg-surface px-4 py-3 text-sm "
    "text-secondary placeholder:text-secondary/45 transition-colors "
    "focus:border-primary focus-visible:outline-none focus-visible:ring-2 "
    "focus-visible:ring-primary/30"
)


class ContactForm(forms.Form):
    name = forms.CharField(
        label="الاسم بالكامل",
        max_length=200,
        validators=[arabic_name_validator],
        widget=forms.TextInput(
            attrs={
                "placeholder": "مثال: نورة العطاس…",
                "autocomplete": "name",
                "class": _INPUT_CLASSES,
            }
        ),
    )
    phone = forms.CharField(
        label="رقم الجوال",
        max_length=20,
        validators=[arabic_phone_validator],
        widget=forms.TelInput(
            attrs={
                "placeholder": "05XXXXXXXX…",
                "dir": "ltr",
                "inputmode": "tel",
                "autocomplete": "tel",
                "spellcheck": "false",
                "class": f"{_INPUT_CLASSES} tabular-nums text-start",
            }
        ),
    )
    subject = forms.CharField(
        label="الموضوع",
        max_length=500,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "استفسار عن مقاس أو قطعة…",
                "class": _INPUT_CLASSES,
            }
        ),
    )
    message = forms.CharField(
        label="رسالتك",
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "اكتبي تفاصيل استفساركِ هنا…",
                "class": f"{_INPUT_CLASSES} resize-y",
            }
        ),
        min_length=10,
        error_messages={
            "min_length": _("الرجاء كتابة رسالة مكونة من 10 أحرف على الأقل"),
        },
    )
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "tabindex": "-1",
                "style": "position:absolute;left:-9999px;",
            }
        ),
    )

    def clean_name(self):
        name = self.cleaned_data.get("name", "")
        return normalize_arabic(name)

    def clean_subject(self):
        subject = self.cleaned_data.get("subject", "").strip()
        return subject or "استفسار عام"

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError(_("خطأ في الإرسال، الرجاء المحاولة مرة أخرى."))
        return value
