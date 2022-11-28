from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.timezone import now
from sequences import get_next_value

from . models import EmailInfo, KeyValueStore, Skola, Soutez_Otazka, Tym, Soutez, Tym_Soutez, Otazka, Tym_Soutez_Otazka, LogTable, ChatMsgs, ChatConvos
from . utils import make_tym_login
from . forms import OtazkaDetailForm

class TymCreationForm(forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput)

    class Meta:
        model = Tym
        fields = ['jmeno','skola','email','soutezici1','soutezici2','soutezici3','soutezici4','soutezici5']

    def save(self, commit=True):
        if self.is_valid():
            user = super().save(commit=False)
            user.login=make_tym_login(self.cleaned_data["jmeno"])
            user.set_password(self.cleaned_data["password"])
            if commit:
                user.save()
            return user
    
    def clean_jmeno(self):
        jmeno = self.cleaned_data["jmeno"]
        # kontrola na unikátnost jména
        login = make_tym_login(jmeno)
        if Tym.objects.filter(login=login).count() > 0:
           raise forms.ValidationError('Login týmu není jedinečný, musíte zvolit jiné jméno týmu.')
        return jmeno

class TymChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label = 'Heslo týmu',help_text = ("Heslo týmu lze změnit <a href=\"../password/\">zde</a>."))
    login = forms.CharField(disabled=True)

    class Meta:
        model = Tym
        fields = ['jmeno','skola','email','soutezici1','soutezici2','soutezici3','soutezici4','soutezici5']

    def __init__(self, *args, **kwargs):
        super(TymChangeForm, self).__init__(*args, **kwargs)
        self.Meta.fields.remove('password')

    def save(self, commit=True):
        if self.is_valid():
            user = super().save(commit=False)
            user.login=make_tym_login(self.cleaned_data["jmeno"])
            if commit:
                user.save()
            return user

    def clean_jmeno(self):
        jmeno = self.cleaned_data["jmeno"]
        # kontrola na unikátnost jména
        login = make_tym_login(jmeno)
        if Tym.objects.filter(login=login).count() > 1:
           raise forms.ValidationError('Login týmu není jedinečný, musíte zvolit jiné jméno týmu.')
        return jmeno

class TymAdmin(UserAdmin):
    form = TymChangeForm
    add_form = TymCreationForm

    list_display = ['login', 'jmeno', 'skola', 'cas_vytvoreni' ]
    list_filter = ['login','jmeno']
    fieldsets = (
        (None, {'fields': ['login','jmeno','skola','password','email', ]}),
        ('Soutezici', {'fields': ['soutezici1', 'soutezici2', 'soutezici3', 'soutezici4', 'soutezici5']}),
    )

    add_fieldsets = (
        (None, {'fields': ['jmeno','skola','password','email', ]}),
        ('Soutezici', {'fields': ['soutezici1', 'soutezici2', 'soutezici3', 'soutezici4', 'soutezici5']}),
    )
    search_fields = ['email','login']
    ordering = ['-cas_vytvoreni','login',]
    filter_horizontal = []

class TymSoutezCreateForm(forms.ModelForm):
    
    class Meta:
        model = Tym_Soutez
        fields = ['tym', 'soutez', 'penize', 'cislo']
        readonly_fields = ['cislo']

    def save(self, commit=True):
        if self.is_valid():
            ts:Tym_Soutez = super().save(commit=False)
            ts.cislo = get_next_value(f'ts_{ts.soutez.pk}')
            if commit:
                ts.save()
            return ts

class TymSoutezChangeForm(forms.ModelForm):
    
    class Meta:
        model = Tym_Soutez
        fields = ['tym', 'soutez', 'penize', 'cislo']
        readonly_fields = ['cislo']


class TymSoutezAdmin(admin.ModelAdmin):
    form = TymSoutezCreateForm
    add_form = TymSoutezChangeForm
    list_display = ('tym', 'soutez', 'penize', 'cislo')
    fields = list_display
    readonly_fields = ('cislo',)
    search_fields = ('tym__jmeno', 'tym__skola__nazev', 'cislo')

class SoutezCreationForm(forms.ModelForm):

    class Meta:
        model = Soutez
        fields = ['typ', 'prezencni', 'limit', 'regod', 'regdo', 'zahajena', 'delkam'] 

    def clean(self):
        super().clean()
        rdo=self.cleaned_data.get('regdo')
        rod=self.cleaned_data.get('regod')
        typ=self.cleaned_data.get('typ')
        prezencni=self.cleaned_data.get('prezencni')
        if rod.date() < now().date():
            self.add_error('regod', "Registrace začíná dříve než dnes.")
        if rdo < rod:
            self.add_error('regdo', "Registrace končí dříve než začíná.")
        dbsoutez = Soutez.objects.filter(typ=typ, rok=rdo.year, prezencni=prezencni)
        if dbsoutez:
            if  dbsoutez.count()>1 or dbsoutez.first() != self.instance:
                self.add_error(None, {
                    'typ': "Nelze vypsat dvě soutěže stejného typu na jeden rok.",
                    'prezencni': ''
                })

class SoutezChangeForm(forms.ModelForm):
    class Meta:
        model = Soutez
        fields = ['typ', 'prezencni', 'limit', 'regod', 'regdo', 'zahajena', 'delkam' ] 

    def clean(self):
        super().clean()
        rdo=self.cleaned_data.get('regdo')
        rod=self.cleaned_data.get('regod')
        typ=self.cleaned_data.get('typ')
        prezencni=self.cleaned_data.get('prezencni')
        if rdo < rod:
            self.add_error('regdo', "Registrace končí dříve než začíná.")
        dbsoutez = Soutez.objects.filter(typ=typ, rok=rdo.year, prezencni=prezencni)
        if dbsoutez:
            if  dbsoutez.count()>1 or dbsoutez.first() != self.instance:
                self.add_error(None, {
                    'typ': "Nelze vypsat dvě soutěže stejného typu na jeden rok.",
                    'prezencni': ''
                })


class SoutezAdmin(admin.ModelAdmin):
    form = SoutezChangeForm
    add_form = SoutezCreationForm

    list_display = ('typ', 'prezencni', 'nazev', 'aktivni', 'rok', 'regod','regdo','limit', 'zahajena','registrace', 'delkam')  
    fieldsets = (
        (None, {'fields': ['typ', 'prezencni', 'limit', 'aktivni', 'regod', 'regdo', 'zahajena', 'delkam'] }),
    )
    add_fieldsets =  (
        (None, {'fields': ['typ', 'prezencni', 'limit', 'regod', 'regdo',  'zahajena', 'delkam']}),
    )
    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            self.form = self.add_form
        else:
            self.form = self.form
        return super(SoutezAdmin, self).get_form(request, obj, **kwargs)


class TymSoutezOtazkaAdminForm(forms.ModelForm):
    class Meta:
        model = Tym_Soutez_Otazka
        fields = ('tym', 'otazka', 'stav', 'odpoved', 'bazar', 'bylaPodpora')

    def save(self, commit=True):
        if self.is_valid():
            tso:Tym_Soutez_Otazka = super().save(commit=False)
            tso.skola = tso.tym.skola
            if commit:
                tso.save()
            return tso

class OtazkaAdminForm(OtazkaDetailForm):
    class Meta(OtazkaDetailForm.Meta):
        fields = ['typ', 'vyhodnoceni', 'obtiznost', 'stav', 'zadani' ,'reseni', 'obrazek']
        labels = {
            'typ': 'Typ',
            'vyhodnoceni': 'Vyhodnocení',
            'obtiznost': 'Obtížnost',
            'zadani': 'Zadání',
            'reseni': 'Řešení',
            'obrazek': 'Obrázek',
            'stav': 'Stav'
        }


class TymSoutezOtazkaAdmin(admin.ModelAdmin):
    form = TymSoutezOtazkaAdminForm
    list_display = ('tym', 'otazka', 'stav', 'odpoved', 'bazar')
    search_fields = ('otazka__cisloVSoutezi', 'tym__jmeno')

class SkolaAdmin(admin.ModelAdmin):
    list_display = ('nazev', 'uzemi')
    search_fields = ('nazev',)

class OtazkaAdmin(admin.ModelAdmin):
    list_display = ('typ', 'id', 'stav', 'obtiznost', 'vyhodnoceni', 'obrazek')
    search_fields = ('id',)
    form = OtazkaAdminForm

class LogTableAdmin(admin.ModelAdmin):
    list_display = ('tym', 'otazka','soutez','staryStav','novyStav', 'cas')
    search_fields = ('tym__jmeno', 'otazka__pk')

class EmailInfoAdmin(admin.ModelAdmin):
    list_display = ('odeslal','soutez','kdy')

class ChatConvosAdmin(admin.ModelAdmin):
    list_display = ('id', 'tym', 'otazka', 'sazka')

class KeyValueStoreAdmin(admin.ModelAdmin):
    list_display = ('key', 'trunc_val')

    def trunc_val(self, obj):
        if len(obj.val) > 256:
            return obj.val[:256] + '...'
        else:
            return obj.val

class SoutezOtazkaAdmin(admin.ModelAdmin):
    list_display = ('otazka', 'soutez', 'cisloVSoutezi')
    search_fields = ('otazka__id', 'cisloVSoutezi')

admin.site.register(Skola, SkolaAdmin)
admin.site.register(Tym,TymAdmin)
admin.site.register(Soutez, SoutezAdmin)
admin.site.register(Tym_Soutez, TymSoutezAdmin)
admin.site.register(Otazka, OtazkaAdmin)
admin.site.register(Tym_Soutez_Otazka, TymSoutezOtazkaAdmin)
admin.site.register(LogTable, LogTableAdmin)
admin.site.register(EmailInfo, EmailInfoAdmin)
admin.site.register(ChatConvos, ChatConvosAdmin)
admin.site.register(ChatMsgs)
admin.site.register(KeyValueStore, KeyValueStoreAdmin)
admin.site.register(Soutez_Otazka, SoutezOtazkaAdmin)