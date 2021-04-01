from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.text import slugify
from datetime import date
from django.utils.timezone import now
from sequences import get_next_value

from .models import EmailInfo, Skola, Tym, Soutez, Tym_Soutez, Otazka, Tym_Soutez_Otazka, LogTable, TymManager, ChatMsgs, ChatConvos

class TymCreationForm(forms.ModelForm):
    password = forms.CharField(label='Password', widget=forms.PasswordInput)

    class Meta:
        model = Tym
        fields = ['jmeno','skola','email','cislo','soutezici1','soutezici2','soutezici3','soutezici4','soutezici5']

    def save(self, commit=True):
        if self.is_valid():
            user = super().save(commit=False)
            aktualni_rok = date.today().strftime("%Y")
            user.cislo=get_next_value(aktualni_rok)
            user.login=slugify(self.cleaned_data["jmeno"]).replace("-", "")+aktualni_rok
            user.set_password(self.cleaned_data["password"])
            if commit:
                user.save()
            return user
    
    def clean_jmeno(self):
        jmeno = self.cleaned_data["jmeno"]
        # kontrola na unikátnost jména
        login = slugify(jmeno)+date.today().strftime("%Y").replace("-", "")
        if Tym.objects.filter(login=login).count() > 0:
           raise forms.ValidationError('Login týmu není jedinečný, musíte zvolit jiné jméno týmu.')
        return jmeno

class TymChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label = 'Heslo týmu',help_text = ("Heslo týmu lze změnit <a href=\"../password/\">zde</a>."))
    login = forms.CharField(disabled=True)

    class Meta:
        model = Tym
        fields = ['jmeno','skola','email','soutezici1','soutezici2','soutezici3','soutezici4','soutezici5']
        readonly_fields = ['cislo']

    def __init__(self, *args, **kwargs):
        super(TymChangeForm, self).__init__(*args, **kwargs)
        self.Meta.fields.remove('password')

    def save(self, commit=True):
        if self.is_valid():
            aktualni_rok = date.today().strftime("%Y")
            user = super().save(commit=False)
            user.login=slugify(self.cleaned_data["jmeno"]).replace("-", "")+aktualni_rok
            if commit:
                user.save()
            return user

    def clean_jmeno(self):
        jmeno = self.cleaned_data["jmeno"]
        # kontrola na unikátnost jména
        login = slugify(jmeno)+date.today().strftime("%Y").replace("-", "")
        if Tym.objects.filter(login=login).count() > 0:
           raise forms.ValidationError('Login týmu není jedinečný, musíte zvolit jiné jméno týmu.')
        return jmeno

class TymAdmin(UserAdmin):
    form = TymChangeForm
    add_form = TymCreationForm

    list_display = ['login', 'jmeno','cislo', 'skola', 'cas_vytvoreni' ]
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

class TymSoutezAdmin(admin.ModelAdmin):
    list_display = ('tym', 'soutez', 'penize')

class SoutezCreationForm(forms.ModelForm):

    class Meta:
        model = Soutez
        fields = ['typ', 'limit', 'regod', 'regdo', 'zahajena', 'delkam'] 

    def clean(self):
        super().clean()
        rdo=self.cleaned_data.get('regdo')
        rod=self.cleaned_data.get('regod')
        typ=self.cleaned_data.get('typ')
        if rod.date() < now().date():
            self.add_error('regod', "Registrace začíná dříve než dnes.")
        if rdo < rod:
            self.add_error('regdo', "Registrace končí dříve než začíná.")
        dbsoutez = Soutez.objects.filter(typ=typ, rok=rdo.year)
        if dbsoutez:
            if  dbsoutez.count()>1 or dbsoutez.first() != self.instance:
                self.add_error('typ', "Nelze vypsat dvě soutěže stejného typu na jeden rok.")

class SoutezChangeForm(forms.ModelForm):
    class Meta:
        model = Soutez
        fields = ['typ', 'limit', 'regod', 'regdo', 'zahajena', 'delkam' ] 

    def clean(self):
        super().clean()
        rdo=self.cleaned_data.get('regdo')
        rod=self.cleaned_data.get('regod')
        typ=self.cleaned_data.get('typ')
        if rdo < rod:
            self.add_error('regdo', "Registrace končí dříve než začíná.")
        dbsoutez = Soutez.objects.filter(typ=typ, rok=rdo.year)
        if dbsoutez:
            if  dbsoutez.count()>1 or dbsoutez.first() != self.instance:
                self.add_error('typ', "Nelze vypsat dvě soutěže stejného typu na jeden rok.")


class SoutezAdmin(admin.ModelAdmin):
    form = SoutezChangeForm
    add_form = SoutezCreationForm

    list_display = ('typ', 'nazev', 'aktivni', 'rok', 'regod','regdo','limit', 'zahajena','registrace', 'delkam')  
    fieldsets = (
        (None, {'fields': ['typ', 'limit', 'aktivni', 'regod', 'regdo', 'zahajena', 'delkam'] }),
    )
    add_fieldsets =  (
        (None, {'fields': ['typ', 'limit', 'regod', 'regdo',  'zahajena', 'delkam']}),
    )
    def get_form(self, request, obj=None, **kwargs):
        if not obj:
            self.form = self.add_form
        else:
            self.form = self.form
        return super(SoutezAdmin, self).get_form(request, obj, **kwargs)

        
class TymSoutezOtazkaAdmin(admin.ModelAdmin):
    list_display = ('tym', 'soutez','otazka','cisloVSoutezi','stav','odpoved','bazar') 

class OtazkaAdmin(admin.ModelAdmin):
    list_display = ('typ', 'pk','stav','obtiznost','vyhodnoceni')     

class LogTableAdmin(admin.ModelAdmin):
    list_display = ('tym', 'otazka','soutez','staryStav','novyStav')    

class EmailInfoAdmin(admin.ModelAdmin):
    list_display = ('odeslal','soutez','kdy')

class ChatConvosAdmin(admin.ModelAdmin):
    list_display = ('id', 'tym', 'otazka', 'sazka')

admin.site.register(Skola)
admin.site.register(Tym,TymAdmin)
admin.site.register(Soutez, SoutezAdmin)
admin.site.register(Tym_Soutez, TymSoutezAdmin)
admin.site.register(Otazka, OtazkaAdmin)
admin.site.register(Tym_Soutez_Otazka, TymSoutezOtazkaAdmin)
admin.site.register(LogTable, LogTableAdmin)
admin.site.register(EmailInfo, EmailInfoAdmin)
admin.site.register(ChatConvos, ChatConvosAdmin)
admin.site.register(ChatMsgs)

