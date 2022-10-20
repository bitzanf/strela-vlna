from django import forms
from .models import KeyValueStore, Tym, Soutez, Tym_Soutez, Otazka, Tym_Soutez_Otazka, EmailInfo
from django.utils.timezone import now
from bootstrap_datepicker_plus.widgets import DateTimePickerInput   # 9.10.2022 - nefunguje, opraveno na .widgets
from django.forms import HiddenInput, DecimalField
from .lookups import SkolaLookup
from selectable.forms.widgets import AutoCompleteSelectWidget
from . utils import make_tym_login
from tinymce.widgets import TinyMCE

import re

class RegistraceForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = Tym
        fields = ['jmeno','skola','email','soutezici1','soutezici2','soutezici3','soutezici4','soutezici5']
        labels = {
            "jmeno": "Jméno týmu",
            "skola": "Škola",
            "email": "Email",
            "soutezici1": "Soutěžící 1",
            "soutezici2": "Soutěžící 2",
            "soutezici3": "Soutěžící 3",
            "soutezici4": "Soutěžící 4",
            "soutezici5": "Soutěžící 5"
        }
        widgets = {
            'skola': AutoCompleteSelectWidget(SkolaLookup)
        }

    def clean(self):
        super().clean()
        
        # tým musí zaškrtnout alespoň jednu soutěž
        has_soutez = False
        valid_soutez = False
        rx = re.compile('soutez(?P<pk>\d+)')
        for s in self.data.keys():
            m = rx.match(s)
            if m is not None:
                pk = int(m.group('pk'))
                soutez = Soutez.objects.filter(rok=now().year, pk=pk)
                if soutez.exists():
                    has_soutez = True
                    if soutez[0].registrace and not soutez[0].is_soutez_full:   #queryset, ne objekt
                        valid_soutez = True
                    else:
                        valid_soutez = False
                        break
        if not has_soutez:
            raise forms.ValidationError('Musíte zvolit alespoň jednu soutěž')
        if not valid_soutez:
            raise forms.ValidationError('Nemůžete se registrovat do již uzavřených soutěží')
        
        # kontrola na unikátnost jména
        login = make_tym_login(self.cleaned_data["jmeno"])
        if len(login) > 50:
            raise forms.ValidationError('Jméno týmu je příliš dlouhé (max cca 50 znaků).')
        if Tym.objects.filter(login=login).count() > 0:
           raise forms.ValidationError('Login týmu není jedinečný, musíte zvolit jiné jméno týmu.')

    def __init__(self, *args, **kwargs):
        super(RegistraceForm, self).__init__(*args, **kwargs)
        souteze = Soutez.objects.filter(rok=now().year)
        for s in souteze:
            if s.registrace and not s.is_soutez_full:
                self.fields["soutez"+str(s.pk)] = forms.BooleanField(required=False, label=s.pretty_name())

class HraOtazkaForm(forms.ModelForm):
    sazka = DecimalField(widget=HiddenInput(attrs={'id': 'sazka_penize'}), required=False, min_value=0)

    class Meta:
        model = Tym_Soutez_Otazka
        fields = ['odpoved']
        labels = {
            "odpoved": "Vaše odpověď"
        }

    def clean(self):
        super().clean()
        if 'b-kontrola' in self.data:
            if self.cleaned_data.get("odpoved") == "":
                raise forms.ValidationError('Musíte něco odpovědět.')
        if 'b-bazar' in self.data and self.instance.bazar:
            raise forms.ValidationError("Nelze prodat otázka již zakoupená z bazaru")

class AdminNovaSoutezForm(forms.ModelForm):
    class Meta:
        model = Soutez
        fields = ['typ', 'prezencni', 'regod','regdo', 'limit', 'delkam']
        widgets = {
            'regod': DateTimePickerInput(options={
                     "format": "DD.MM.YYYY HH:mm",
                     "locale": "cs",
                 }),
            'regdo': DateTimePickerInput(options={
                     "format": "DD.MM.YYYY HH:mm",
                     "locale": "cs",
                 }),

        }
        labels = {
            'prezencni': 'Prezenční'
        }

    def clean(self):
        super().clean()
        rdo=self.cleaned_data.get('regdo')
        rod=self.cleaned_data.get('regod')
        typ=self.cleaned_data.get('typ')
        prezencni=self.cleaned_data.get('prezencni')

        if rod:
            if rod.date() < now().date():
                self.add_error('regod', "Registrace začíná dříve než dnes.")
                raise forms.ValidationError("Registrace začíná dříve než dnes.")
        else:
            self.add_error('regod', "Datum od je špatné")
            raise forms.ValidationError("Datum od je špatné")
        if rdo:
            if rdo < rod:
                self.add_error('regdo', "Registrace končí dříve než začíná.")
                raise forms.ValidationError("Registrace končí dříve než začíná.")
        else:
            self.add_error('regdo', "Datum do je špatné")
            raise forms.ValidationError("Datum do je špatné")   
        dbsoutez = Soutez.objects.filter(typ=typ, rok=rdo.year, prezencni=prezencni)
        if dbsoutez:
            if  dbsoutez.count() > 1 or dbsoutez.first() != self.instance:
                #self.add_error('typ', "Nelze vypsat dvě soutěže stejného typu na jeden rok.")
                self.add_error(None, {
                    'typ': "Nelze vypsat dvě soutěže stejného typu na jeden rok.",
                    'prezencni': ''
                })

class AdminNovaOtazka(forms.ModelForm):
    class Meta:
        model = Otazka
        fields = ['typ','vyhodnoceni','obtiznost','zadani','reseni']
        labels = {
            'typ': 'Typ',
            'vyhodnoceni': 'Vyhodnocení',
            'obtiznost': 'Obtížnost',
            'zadani': 'Zadání',
            'reseni': 'Řešení'
        }

    def clean_zadani(self):
        zadani = self.cleaned_data["zadani"]
        if Otazka.objects.filter(zadani=zadani).exists():
            raise forms.ValidationError("Otázku nelze uložit, protože existuje jiná otázka se stejným zadáním.")
        return zadani

class AdminZalozSoutezForm(forms.Form):
    pocet_otazek = forms.IntegerField(label="Počet otázek", required=False, initial=20, min_value=0)

    def clean_pocet_otazek(self):
        pocet_otazek = self.cleaned_data.get('pocet_otazek')
        if 'b-otazky' in self.data:
            if pocet_otazek == 0:
                raise forms.ValidationError("Nepřidáváte žádnou otázku.")
            if pocet_otazek % 5 != 0:
                raise forms.ValidationError("Počet otázek není dělitelný počtem kategorií.") 
        return pocet_otazek

class AdminEmailInfo(forms.ModelForm):
    class Meta:
        model = EmailInfo
        fields = ['zprava']
        widgets = {
            'zprava': TinyMCE(mce_attrs = {
                'image_title': True,
                'automatic_uploads': True,
                'file_picker_inputs': 'image',
                'file_picker_callback': 'TinyMCE_filepicker_callback'
            })
        }
        labels = {
            'zprava': 'Zpráva'
        }

class AdminSoutezMoneyForm(forms.Form):
    soutez: Soutez

    def __init__(self, *args, **kwargs):
        soutez_pk = kwargs.pop('pk')
        super().__init__(*args, **kwargs)
        #kwargs['pk'] = soutez_pk
        self.soutez = Soutez.objects.get(pk=soutez_pk)
        TvS = Tym_Soutez.objects.filter(soutez=self.soutez)
        for tym in TvS:
            #self.fields[tym.tym.login] = forms.IntegerField(required=True, min_value=0, label='Získané peníze týmu \"' + tym.tym.jmeno + '\"', initial=tym.penize)
            self.fields[str(tym.tym.pk)] = forms.IntegerField(required=True, min_value=0, label='Získané peníze týmu \"' + tym.tym.jmeno + '\"', initial=tym.penize)

    def clean(self):
        super().clean()
        if self.soutez.prezencni == 'O':
            raise forms.ValidationError("Body lze přiřadit jen prezeční soutěži")

class AdminTextForm(forms.Form):
    infotext_key:str

    def __init__(self, *args, **kwargs):
        self.infotext_key = kwargs.pop('key')
        super().__init__(*args, **kwargs)

        self.fields = {
            'infotext': forms.CharField(
                widget=TinyMCE(
                    mce_attrs= {
                        'content_css': '/static/css/style.css',
                        'setup': 'TinyMCE_setup',
                        'height': '512'
                    }
                ),
                label='',
                initial=KeyValueStore.objects.get(key=self.infotext_key).val
            )
        }