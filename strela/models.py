from __future__ import annotations

from django.db import models, transaction
from django.core.cache import cache
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, User
from django.utils.timezone import now

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
    nazev:str = models.CharField(max_length=200)

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
    login:str = models.CharField(max_length=50, unique=True)
    jmeno:str = models.CharField(max_length=200)
    skola:Skola = models.ForeignKey(Skola, on_delete=models.CASCADE, related_name='tymy')
    email:str = models.EmailField(max_length = 200)
    soutezici1:str = models.CharField(max_length=100)
    soutezici2:str = models.CharField(max_length=100, blank=True)
    soutezici3:str = models.CharField(max_length=100, blank=True)
    soutezici4:str = models.CharField(max_length=100, blank=True)
    soutezici5:str = models.CharField(max_length=100, blank=True)
    cas_zmeny:datetime.datetime = models.DateTimeField(auto_now=True)
    cas_vytvoreni:datetime.datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name="Tým"
        verbose_name_plural="Týmy"

    USERNAME_FIELD = "login"

    objects = TymManager()

    def __str__(self):
        from . utils import vokalizace_z_ze # musí to být tady, jinak to padá na chybě importu
        return self.jmeno + ' ' + vokalizace_z_ze(self.skola)

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
    typ:str = models.CharField(max_length=1, choices = FLAGMF)
    prezencni:str = models.CharField(max_length=1, choices = FLAGPREZENCNI)
    aktivni:bool = models.BooleanField(verbose_name="Soutež probíhá", default=False)
    limit:int = models.PositiveIntegerField(verbose_name = "Max. počet týmů",default=30)
    regod:datetime.datetime = models.DateTimeField(verbose_name = "Zahájení registrace",default=now)
    regdo:datetime.datetime = models.DateTimeField(verbose_name = "Konec registrace",default=now)
    rok:int = models.PositiveIntegerField(default=0)
    zahajena:datetime.datetime = models.DateTimeField(verbose_name = "Zahájení soutěže",blank = True, null = True)
    delkam:int = models.PositiveIntegerField(verbose_name = "Délka soutěže",default=120)

    def __str__(self):
        """`Matematika 2020 [O]`"""
        return "{} {} [{}]".format(self.get_typ_display(), self.rok, self.prezencni)

    def save(self, *args, **kwargs):
        self.rok = self.regdo.strftime("%Y")
        super(Soutez, self).save(*args, **kwargs)    
    
    @classmethod
    @transaction.atomic
    def get_aktivni(cls, throw:bool=False, admin:bool=False) -> Soutez | None:
        try:
            soutez:Soutez = Soutez.objects.get(rok=now().year, aktivni=True)
            cache.set('act_soutez_admin', soutez.pk, timeout=300)
        except Soutez.DoesNotExist as e:
            if admin:
                cache_val = cache.get('act_soutez_admin')
                return Soutez.objects.get(pk=cache_val) if cache_val is not None else None
            if not throw:
                return None
            else:
                raise e
        if now() < (soutez.zahajena + datetime.timedelta(minutes = soutez.delkam)):
            return soutez
        else:
            Tym_Soutez_Otazka.sellall(soutez)
            soutez.aktivni = False 
            logger.info(f"Soutěž {soutez} byla ukončena.")
            soutez.save()
            if not throw:
                return None
            else:
                raise Soutez.DoesNotExist()

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
    
    def pretty_name(self, add_rok=False) -> str:
        """
        `Pražská střela (Matematika) [Prezenční]`

        `Pražská střela (Matematika) [Prezenční] (rok)`
        """
        if add_rok:
            return self.nazev + ' (' + self.zamereni + ') [' + self.get_prezencni_display() + '] (' + str(self.rok) + ')'
        else:
            return self.nazev + ' (' + self.zamereni + ') [' + self.get_prezencni_display() + ']'
    

class Tym_Soutez(models.Model):
    tym:Tym = models.ForeignKey(Tym, on_delete=models.CASCADE, related_name="tymy")
    soutez:Soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE, related_name="souteze")
    penize:int = models.PositiveIntegerField(default=40)
    cislo:int = models.PositiveIntegerField(default=0)

    def __str__(self):
        return "{0} v soutěži {1} ({2})".format(self.tym.jmeno, self.soutez.get_typ_display(), self.soutez.rok)

    class Meta:
        verbose_name="Tým v soutěži"
        verbose_name_plural="Týmy v soutěžích"

class Otazka(models.Model):
    typ:str = models.CharField(max_length = 1, choices = FLAGMF)
    stav:int = models.PositiveIntegerField(choices = FLAGSTATE)
    vyhodnoceni:int = models.PositiveSmallIntegerField(choices = FLAGEVAL)
    obtiznost:str = models.CharField(max_length = 1, choices = FLAGDIFF)
    zadani:str = models.TextField()
    reseni:str = models.CharField(max_length = 250)

    def __str__(self):
        """F-23: schválená lehká (automaticky)"""
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
    tym:Tym = models.ForeignKey(Tym, on_delete=models.CASCADE, blank=True, null=True)
    soutez:Soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE)
    otazka:Otazka = models.ForeignKey(Otazka, on_delete=models.CASCADE, related_name='otazky')
    stav:int = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)
    odpoved:str = models.CharField(max_length = 128, blank=True)
    bazar:bool = models.BooleanField(verbose_name="Zakoupena z bazaru", default=False)
    cisloVSoutezi:int = models.IntegerField(verbose_name="Číslo otázky v soutěži", default=0)
    bylaPodpora:bool = models.BooleanField(verbose_name="Vyskytla se na technické podpoře", default=False)

    def __str__(self):
        """`F-23 [4] (2020): V bazaru`"""
        return "{0}-{1} [{4}] ({2}): {3}".format(self.otazka.typ, self.otazka.id, self.soutez.rok, self.get_stav_display(), self.cisloVSoutezi)

    class Meta:
        verbose_name="Otázka v soutěži"
        verbose_name_plural="Otázky v soutéžích"

    @classmethod
    @transaction.atomic
    def buy(cls, tym:Tym, soutez:Soutez, obtiznost:str) -> Tym_Soutez_Otazka:
        tym_soutez:Tym_Soutez = Tym_Soutez.objects.get(tym=tym, soutez=soutez)
        konec = soutez.zahajena + datetime.timedelta(minutes=soutez.delkam)

        if konec - now() < datetime.timedelta(minutes=15):
            raise Exception('Obchod se na posledních 15 minut soutěže zavírá')
        
        if tym_soutez.penize >= CENIK[obtiznost][0]:
            otazky = Tym_Soutez_Otazka.objects.filter(stav=0, soutez=soutez, otazka__obtiznost=obtiznost).order_by("?")[:1]
            if len(otazky) == 0:
                if obtiznost == 'A':
                    logger.info(f'Tým {tym} zakoupil otázku z obchodu, ale koupila se z bazaru')
                    return cls.buy_bazar(tym, soutez, obtiznost)
                else:
                    logger.error("Tým {} se pokusil koupit otázku s obtížností {}, které došly.".format(tym, obtiznost))
                    raise Exception("došly otázky s obtížností {} :/".format(obtiznost))
            otazka:Tym_Soutez_Otazka = otazky[0]
            otazka.stav = 1
            tym_soutez.penize -= CENIK[obtiznost][0]
            otazka.tym=tym
            LogTable.objects.create(tym=tym, otazka=otazka.otazka, soutez=soutez, staryStav=0, novyStav=1)
            logger.info("Tým {} zakoupil otázku {} s obtížností {} za {} DC.".format(tym, otazka, obtiznost, CENIK[obtiznost][0]))
            otazka.save()
            tym_soutez.save()
            return otazka
        else: raise Exception("nedostatek prostředků pro nákup otázky")

    @classmethod
    @transaction.atomic
    def buy_bazar(cls, tym:Tym, soutez:Soutez, obtiznost:str) -> Tym_Soutez_Otazka:
        tym_soutez:Tym_Soutez = Tym_Soutez.objects.get(tym=tym, soutez=soutez)

        if tym_soutez.penize >= CENIK[obtiznost][2]:
            otazky = Tym_Soutez_Otazka.objects.filter(stav=5, soutez=soutez, otazka__obtiznost=obtiznost).order_by("?")[:1]
            if len(otazky) == 0:
                logger.error("Tým {} se pokusil koupit otázku s obtížností {} Z BAZARU, které došly.".format(tym, obtiznost))
                raise Exception("došly otázky s obtiznosti {} v bazaru :/".format(obtiznost))
            otazka:Tym_Soutez_Otazka = otazky[0]
            otazka.stav = 6
            tym_soutez.penize -= CENIK[obtiznost][2]
            otazka.tym=tym
            LogTable.objects.create(tym=tym, otazka=otazka.otazka, soutez=soutez, staryStav=5, novyStav=6)
            logger.info("Tým {} zakoupil otázku {} s obtížností {} za {} DC.".format(tym, otazka, obtiznost, CENIK[obtiznost][0]))
            otazka.save()
            tym_soutez.save()
            return otazka
        else: raise Exception("nedostatek prostředků pro nákup otázky z bazaru")

    @transaction.atomic
    def sell(self):
        if self.bazar: return
        LogTable.objects.create(tym=self.tym, otazka=self.otazka, soutez=self.soutez, staryStav=self.stav, novyStav=5)
        
        team:Tym_Soutez = Tym_Soutez.objects.get(tym=self.tym, soutez=self.soutez)
        self.tym = None
        if self.otazka.obtiznost != "A":
            self.bazar = True
        self.stav = 5
        self.odpoved = ""
        team.penize += CENIK[self.otazka.obtiznost][2]
        logger.info("Tým {} prodal otázku {} do bazaru za {} DC.".format(team.tym, self.otazka, CENIK[self.otazka.obtiznost][2]))
        self.save()
        team.save()

    @classmethod
    def sellall(cls, soutez:Soutez):
        logger.info(f'Automatické prodávání otázek v soutěži {soutez}')
        otazky:list[Tym_Soutez_Otazka] = Tym_Soutez_Otazka.objects.filter(stav__in=[1, 6, 7], soutez=soutez)
        for o in otazky:
            o.sell()
    
    

class LogTable(models.Model):
    tym:Tym = models.ForeignKey(Tym, on_delete=models.CASCADE, null=True)
    otazka:Otazka = models.ForeignKey(Otazka, on_delete=models.CASCADE, null=True)
    soutez:Soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE, null=True)
    cas:datetime.datetime = models.DateTimeField(auto_now=True, db_index=True)
    staryStav:int = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)
    novyStav:int = models.PositiveIntegerField(choices = FLAGSOUTEZSTATE)

    def __str__(self):
        # 31.12.2020 19:54 <tým>: F-23 <staryStav> -> <novyStav>
        return "{0} {1}: {2}-{3} {4} -> {5}".format(self.cas.strftime("%d.%m.%Y %H:%M"), self.tym.jmeno, self.otazka.typ, self.otazka.id, self.get_staryStav_display(), self.get_novyStav_display())

    class Meta:
        verbose_name="Log akcí"
        verbose_name_plural="Log akcí"

    @property
    def cisloVSoutezi(self) -> int:
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
    def typOtazky(self) -> str:
        cache_key = "to_{}-{}".format(self.otazka_id,self.soutez_id) 
        cached = cache.get(cache_key)
        if not cached:
            try:
                to = self.otazka.typ
                cache.set(cache_key, to)
                return to
            except Exception as e:
                logger.error("Chyba {} při získávání atributu typOtazky".format(e))
                return 0
        else:
            return cached  


class EmailInfo(models.Model):
    odeslal:User = models.ForeignKey(User, on_delete=models.CASCADE)
    zprava:str = models.TextField()
    kdy:datetime.datetime = models.DateTimeField(auto_now=True)
    soutez:Soutez = models.ForeignKey(Soutez, on_delete=models.CASCADE)

    def __str__(self):
        return "Email id={} odeslal {}".format(self.id, self.odeslal)

    class Meta:
        verbose_name="Informační email"
        verbose_name_plural="Informační emaily"

class ChatConvos(models.Model):
    otazka:Tym_Soutez_Otazka = models.ForeignKey(Tym_Soutez_Otazka, on_delete=models.CASCADE, null=True)
    tym:Tym = models.ForeignKey(Tym, on_delete=models.CASCADE)
    uzavreno:bool = models.BooleanField(default=False)
    uznano:bool = models.BooleanField(default=False)
    sazka:int = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Konverzace"
        verbose_name_plural = "Konverzace"

    def __str__(self):
        return "Konverzace týmu '{1}' ohledně otázky '{0}'".format(self.otazka, self.tym)

class ChatMsgs(models.Model):
    smer:bool = models.BooleanField(verbose_name="směr komunikace (0: tym->podpora; 1: podpora->tym)")   # 0: tym->podpora; 1: podpora->tym
    text:str = models.TextField()
    konverzace:ChatConvos = models.ForeignKey(ChatConvos, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Zpráva chatu"
        verbose_name_plural = "Zprávy chatu"

    def __str__(self):
        if self.smer == 0:
            return "{} ({}) -> {}".format(self.konverzace.tym, self.konverzace.otazka, self.text)
        else:
            return "{} ({}) <- {}".format(self.konverzace.tym, self.konverzace.otazka, self.text)