from __future__ import annotations

from django.db import models, transaction
from django.core.cache import cache
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, User

from django.utils.timezone import now
#import json
import datetime
import logging
logger = logging.getLogger(__name__)

FLAGMF = (
    ("M", "Matematika"),
    ("F", "Fyzika"),
    ("X", "Matematika & Fyzika"),
)

FLAGPREZENCNI = (
    ("P", "Prezenční"),
    ("O", "Online")
)

FLAGDIFF = (
    ("A", "Nejlehčí"),
    ("B", "Lehká"),
    ("C", "Střední"),
    ("D", "Těžká"),
    ("E", "Nejtěžší")
)

FLAGSTATE = (
    (0, "Nová"),
    (1, "Schválená"),
    (2, "Chybná")
)

FLAGSOUTEZSTATE = (
    (0, "Nová"),
    (1, "Zakoupená"),
    (2, "Odevzdaná"),
    (3, "Vyřešená"),
    (4, "Technická podpora"),
    (5, "V bazaru"),
    (6, "Zakoupená z bazaru"),
    (7, "Chybně zodpovězená")
)

FLAGEVAL = (
    (0, "Vyhodnotit automaticky"),
    (1, "Vyhodnotit ručně")
)

FLAGNAME = {
    "M": "Pražská střela",
    "F": "Doplerova vlna",
    "X": "Pražská vlna",
}

OTAZKASOUTEZ = {
    "M": ("M",),
    "F": ("F",),
    "X": ("M","F","X"),
}

CENIK = {
    "A": (20, 30, 20), #nakup, zisk, bazar
    "B": (50, 70, 20),
    "C": (70, 110, 30),
    "D": (80, 160, 40),
    "E": (100, 210, 50)
}

class Skola(models.Model):
    nazev = models.CharField(max_length=200)

    def __str__(self):
        return self.nazev

    def get_queryset(self):
        return Skola.objects.all().order_by("-nazev")

    class Meta:
        verbose_name="Škola"
        verbose_name_plural="Školy"

class TymManager(BaseUserManager):

    def create_user(self, login, email, password):
        print(self.model)
        if self.login and password:
            user = self.model(email=self.normalize_email(email))
            user.set_password(password)
            user.save()
        return user

    def create_superuser(self, login, email, password):
        pass

class Tym(AbstractBaseUser):
    login = models.CharField(max_length=50, unique=True)
    jmeno = models.CharField(max_length=200)
    skola = models.ForeignKey(Skola, on_delete=models.CASCADE, related_name='tymy')
    email = models.EmailField(max_length = 200)
    cislo = models.PositiveIntegerField(default=0)
    soutezici1 = models.CharField(max_length=100)
    soutezici2 = models.CharField(max_length=100, blank=True)
    soutezici3 = models.CharField(max_length=100, blank=True)
    soutezici4 = models.CharField(max_length=100, blank=True)
    soutezici5 = models.CharField(max_length=100, blank=True)
    cas_zmeny = models.DateTimeField(auto_now=True)
    cas_vytvoreni = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name="Tým"
        verbose_name_plural="Týmy"

    USERNAME_FIELD = "login"

    objects = TymManager()

    def __str__(self):
        return "{0} ze {1}".format(self.jmeno, self.skola.nazev)

    def get_queryset(self):
        return Tym.objects.all().order_by("-cislo")

    @property
    def is_staff(self):
        return False

    def has_perm(self, perm, obj=None):
        return perm == "strela.soutezici"

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label):
        return app_label == "strela"

class Soutez(models.Model):
    typ = models.CharField(max_length=1, choices = FLAGMF)
    prezencni = models.CharField(max_length=1, choices = FLAGPREZENCNI)
    aktivni = models.BooleanField(verbose_name="Soutež probíhá", default=False)
    limit = models.PositiveIntegerField(verbose_name = "Max. počet týmů",default=30)
    regod = models.DateTimeField(verbose_name = "Zahájení registrace",default=now)
    regdo = models.DateTimeField(verbose_name = "Konec registrace",default=now)
    rok = models.PositiveIntegerField(default=0)
    zahajena = models.DateTimeField(verbose_name = "Zahájení soutěže",blank = True, null = True)
    delkam = models.PositiveIntegerField(verbose_name = "Délka soutěže",default=120)

    def __str__(self):
        return "{} {} [{}]".format(self.get_typ_display(), self.rok, self.prezencni) #"Matematika 2020"

    def save(self, *args, **kwargs):
        self.rok = self.regdo.strftime("%Y")
        super(Soutez, self).save(*args, **kwargs)    
    
    @classmethod
    @transaction.atomic
    def get_aktivni(cls) -> Soutez | None:
        try:
            soutez = Soutez.objects.get(rok=now().year, aktivni=True)
        except Soutez.DoesNotExist:
            #logger.warning("Nenalezena aktivní soutěž.")
            return None
        if now() < (soutez.zahajena + datetime.timedelta(minutes = soutez.delkam)):
            return soutez
        else:
            soutez.aktivni = False 
            logger.info(f"Soutěž {soutez} byla ukončena.")
            soutez.save()
            return None

    @property
    def registrace(self) -> bool:
        t = now()
        return (self.regod <= t) and (t <= self.regdo)

    @property
    def nazev(self):
        return FLAGNAME[self.typ]

    @property
    def zamereni(self) -> str:
        return self.get_typ_display()

    @property
    def is_soutez_full(self) -> bool:
        prihlaseni = Tym_Soutez.objects.filter(soutez=self).count()
        return prihlaseni >= self.limit

    class Meta:
        verbose_name="Soutěž"
        verbose_name_plural="Soutěže"
    
    def pretty_name(self) -> str:
        """`Pražská střela (Matematika) [Prezenční]`"""
        return self.nazev + ' (' + self.zamereni + ') [' + self.get_prezencni_display() + ']'
    

class Tym_Soutez(models.Model):
    tym = models.ForeignKey(Tym, on_delete=models.CASCADE, related_name="tymy")
    soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE, related_name="souteze")
    penize = models.PositiveIntegerField(default=40)

    def __str__(self):
        return "{0} v soutěži {1} ({2})".format(self.tym.jmeno, self.soutez.get_typ_display(), self.soutez.rok)

    class Meta:
        verbose_name="Tým v soutěži"
        verbose_name_plural="Týmy v soutěžích"

class Otazka(models.Model):
    typ = models.CharField(max_length = 1, choices = FLAGMF)
    stav = models.PositiveIntegerField(choices = FLAGSTATE)
    vyhodnoceni = models.PositiveSmallIntegerField(choices = FLAGEVAL)
    obtiznost = models.CharField(max_length = 1, choices = FLAGDIFF)
    zadani = models.TextField()
    reseni = models.CharField(max_length = 250)

    def __str__(self):
        # F-23: schvalena, lehka (auto)
        return "{0}-{1}: {2} {3} ({4})".format(self.typ, self.id, self.get_stav_display().lower(), self.get_obtiznost_display().lower(), self.get_vyhodnoceni_display().split()[1])

    class Meta:
        verbose_name="Otázka"
        verbose_name_plural="Otázky"
        permissions = [
            ("zadavatel","Může zadávat nové otázky"),
            ("kontrolazadani","Kontroluje a schvaluje zadané otázky"),
            ("soutezici","Soutěžící"),
            ("kontrolareseni","Kontroluje odevzdané řešení"),
            ("podpora","Technická podopora"),
            ("adminsouteze","Administrace soutěže"),
            ("novasoutez","Může založit novou soutěž"),
        ]

class Tym_Soutez_Otazka(models.Model):
    tym = models.ForeignKey(Tym, on_delete=models.CASCADE, blank=True, null=True)
    soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE)
    otazka = models.ForeignKey(Otazka, on_delete=models.CASCADE, related_name='otazky')
    stav = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)
    odpoved = models.CharField(max_length = 128, blank=True)
    bazar = models.BooleanField(verbose_name="Zakoupena z bazaru", default=False)
    cisloVSoutezi = models.IntegerField(verbose_name="Číslo otázky v soutěži", default=0)
    bylaPodpora = models.BooleanField(verbose_name="Vyskytla se na technické podpoře", default=False)

    def __str__(self):
        # F-23 [4] (2020): V bazaru
        return "{0}-{1} [{4}] ({2}): {3}".format(self.otazka.typ, self.otazka.id, self.soutez.rok, self.get_stav_display(), self.cisloVSoutezi)

    class Meta:
        verbose_name="Otázka v soutěži"
        verbose_name_plural="Otázky v soutéžích"

class LogTable(models.Model):
    tym = models.ForeignKey(Tym, on_delete=models.CASCADE, null=True)
    otazka = models.ForeignKey(Otazka, on_delete=models.CASCADE, null=True)
    soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE, null=True)
    cas = models.DateTimeField(auto_now=True, db_index=True)
    staryStav = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)
    novyStav = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)

    def __str__(self):
        # 31.12.2020 19:54 <tým>: F-23 <staryStav> -> <novyStav>
        return "{0} {1}: {2}-{3} {4} -> {5}".format(self.cas.strftime("%d.%m.%Y %H:%M"), self.tym.jmeno, self.otazka.typ, self.otazka.id, self.get_staryStav_display(), self.get_novyStav_display())

    class Meta:
        verbose_name="Log akcí"
        verbose_name_plural="Log akcí"

    @property
    def cisloVSoutezi(self):
        cache_key = "cvs_{}-{}".format(self.otazka_id,self.soutez_id) 
        cached = cache.get(cache_key)
        if not cached:
            try:
                cvs = Tym_Soutez_Otazka.objects.get(otazka=self.otazka, soutez=self.soutez).cisloVSoutezi
                cache.set(cache_key, cvs)
                return cvs
            except Tym_Soutez_Otazka.DoesNotExist as e:
                logger.error("Chyba {} při získávání atributu cisloVSoutezi".format(e))
                return 0
        else:
            return cached  
    @property
    def typOtazky(self):
        cache_key = "to_{}-{}".format(self.otazka_id,self.soutez_id) 
        cached = cache.get(cache_key)
        if not cached:
            try:
                to = self.otazka.typ
                cache.set(cache_key, to)
                return to
            except Exception as e:
                logger.error("Chyba {} při získávání atributu cisloVSoutezi".format(e))
                return 0
        else:
            return cached  


class EmailInfo(models.Model):
    odeslal = models.ForeignKey(User, on_delete=models.CASCADE)
    zprava = models.TextField()
    kdy = models.DateTimeField(auto_now=True)
    soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE)

    def __str__(self):
        return "Email id={} odeslal {}".format(self.id, self.odeslal)

    class Meta:
        verbose_name="Informační email"
        verbose_name_plural="Informační emaily"

class ChatConvos(models.Model):
    otazka = models.ForeignKey(Tym_Soutez_Otazka, on_delete=models.CASCADE, null=True)
    tym = models.ForeignKey(Tym, on_delete=models.CASCADE)
    uzavreno = models.BooleanField(default=False)
    uznano = models.BooleanField(default=False)
    sazka = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Konverzace"
        verbose_name_plural = "Konverzace"

    def __str__(self):
        return "Konverzace týmu '{1}' ohledně otázky '{0}'".format(self.otazka, self.tym)

class ChatMsgs(models.Model):
    smer = models.BooleanField(verbose_name="směr komunikace (0: tym->podpora; 1: podpora->tym)")   # 0: tym->podpora; 1: podpora->tym
    text = models.TextField()
    konverzace = models.ForeignKey(ChatConvos, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Zpráva chatu"
        verbose_name_plural = "Zprávy chatu"

    def __str__(self):
        if self.smer == 0:
            return "{} ({}) -> {}".format(self.konverzace.tym, self.konverzace.otazka, self.text)
        else:
            return "{} ({}) <- {}".format(self.konverzace.tym, self.konverzace.otazka, self.text)