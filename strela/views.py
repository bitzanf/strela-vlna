from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from django import forms
from django.utils.timezone import now
from django.utils.text import slugify
from django.shortcuts import redirect
from django_tex.shortcuts import render_to_pdf
from django.views.generic import ListView, TemplateView, CreateView, DetailView
from django.views import View
from django.views.generic.edit import FormView, UpdateView, DeleteView, FormMixin
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.db.models import Q, Count
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.crypto import get_random_string
from django.core.cache import cache
from sequences import get_next_value

from . models import KeyValueStore, Soutez_Otazka, Tym, Soutez, Tym_Soutez, LogTable, Otazka, Tym_Soutez_Otazka, EmailInfo, ChatConvos, ChatMsgs, Skola
from . utils import eval_registration, tex_escape, make_tym_login, auto_kontrola_odpovedi, BulkMailSender
from . forms import AdminPozvankyForm, AdminTextForm, RegistraceForm, HraOtazkaForm, AdminNovaSoutezForm, AdminNovaOtazka, AdminZalozSoutezForm, AdminEmailInfo, AdminSoutezMoneyForm, OtazkaDetailForm
from . constants import CZ_NUTS_NAMES, FLAGDIFF, CENIK, OTAZKASOUTEZ, TYM_DEFAULT_MONEY

import lxml.html as lxhtml

import re, datetime, logging
logger = logging.getLogger(__name__)


class AdministraceIndex(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "admin/admin_index.html"
    permission_required = 'strela.adminsouteze'
    login_url = reverse_lazy("admin_login")

    def cache_otazky(self, soutez:Soutez):
        skoly = Tym_Soutez.objects.filter(soutez=soutez).values_list('tym__skola', flat=True).distinct()
        otazky = Soutez_Otazka.objects.filter(soutez=soutez)

        stavy = []
        for skola in skoly:
            skola_obj = Skola.objects.get(id=skola)
            stavy_obtiznosti = [{}, {}, {}, {}, {}, {}, {}, {}]
            otazky_skoly = Tym_Soutez_Otazka.objects.filter(skola=skola, otazka__in=otazky)
            dostupne = otazky.exclude(
                id__in=otazky_skoly.values_list('otazka', flat=True)
            )

            stavy_list = [0, 0, 0, 0, 0, 0, 0, 0]

            stavy_list[0] = dostupne.count()
            for o in dostupne.values('otazka__obtiznost').annotate(count=Count('otazka__obtiznost')):
                stavy_obtiznosti[0].update({o['otazka__obtiznost']:o['count']})


            for o in otazky_skoly:
                if not o.otazka.otazka.obtiznost in stavy_obtiznosti[o.stav].keys():
                    stavy_obtiznosti[o.stav].update({o.otazka.otazka.obtiznost:1})
                else:
                    stavy_obtiznosti[o.stav][o.otazka.otazka.obtiznost] += 1

            for i in range(1, len(stavy_list)):
                stavy_list[i] = sum(stavy_obtiznosti[i].values())
            
            if stavy_list[0] == 0:
                messages.warning(self.request, f'Škole {skola_obj} došly otázky!')

            stavy.append((
                (
                    skola_obj.kratce,
                    skola_obj.nazev,
                    Tym_Soutez.objects.filter(
                        soutez=soutez,
                        tym__skola=skola).count()
                ),
                zip(
                    stavy_list,
                    [', '.join([f'{k}:{v}' for k, v in o.items()]) for o in stavy_obtiznosti]
                )
            ))

        cache.set('admin_soutez_otazky', stavy, timeout=60)
        return stavy

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        soutez = Soutez.get_aktivni(admin=True)
        otazky_souteze = Tym_Soutez_Otazka.objects.filter(otazka__soutez=soutez)
        ctx['n_otazek_celkem'] = Soutez_Otazka.objects.filter(soutez=soutez).count()
        ctx['n_otazek_podpora'] = ChatConvos.objects.filter(uzavreno=False, tym__soutez=soutez).count()
        ctx['n_otazek_kontrola'] = otazky_souteze.filter(stav=2).count()
        ctx['n_otazek_vyreseno'] = otazky_souteze.filter(stav=3).count()
        ctx['n_otazek_chybne'] = Otazka.objects.filter(stav=2, id__in=Soutez_Otazka.objects.filter(soutez=soutez).values_list('otazka__id', flat=True)).count()
        ctx['n_tymu'] = Tym_Soutez.objects.filter(soutez=soutez).count()

        stavy = cache.get('admin_soutez_otazky')
        if not stavy: stavy = self.cache_otazky(soutez)
        ctx['n_otazek_skoly'] = stavy

        ctx['aktivni_soutez'] = soutez
        if soutez is not None: ctx['soutez_valid'] = True if soutez.prezencni == 'O' else False

        if soutez != None:
            konec = soutez.zahajena + datetime.timedelta(minutes = soutez.delkam)
            if konec - now() < datetime.timedelta(minutes=5):
                ctx["color"] = "danger"
            elif konec - now() < datetime.timedelta(minutes=15):
                ctx["color"] = "warning"
            else:
                ctx["color"] = "secondary"
            ctx["konec"] = konec.strftime('%H:%M')
        return ctx
    

class NovaOtazka(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    template_name = "admin/nova_otazka.html"
    permission_required = ['strela.zadavatel','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Otazka
    success_url = reverse_lazy("otazky")
    form_class = AdminNovaOtazka

    @transaction.atomic
    def form_valid(self, form):
        formular:Otazka = form.save(commit=False)
        formular.stav = 0
        formular.save()
        if 'b-ulozit' in form.data:
            logger.info("Uživatel {1} uložil otázku {0}.".format(formular,self.request.user))
            messages.success(self.request, f'Otázka {formular} byla vytvořena [pk:{formular.pk}]')
            return super().form_valid(form)
        if 'b-nahled' in form.data:
            logger.info("Uživatel {1} uložil otázku {0} s náhledem.".format(formular,self.request.user))
            messages.success(self.request, f'Otázka {formular} byla vytvořena [pk:{formular.pk}]')
            return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.id,)))


class Otazky(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, ListView):
    template_name = "admin/otazky.html"
    login_url = reverse_lazy("admin_login")
    success_message = "Otázka byla uložena."

    def has_permission(self):
        user = self.request.user
        return user.has_perm('strela.adminsouteze') and (user.has_perm('strela.zadavatel') or user.has_perm('strela.kontrolazadani'))
    
    def get_queryset(self):
        return Otazka.objects.all()


class OtazkaAdminDetail(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = "admin/detail_otazky.html"
    login_url = reverse_lazy("admin_login")
    model = Otazka
    form_class = OtazkaDetailForm
    
    def has_permission(self):
        user = self.request.user
        return user.has_perm('strela.adminsouteze') and (user.has_perm('strela.zadavatel') or user.has_perm('strela.kontrolazadani'))
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object.obrazek:
            ctx['img_url'] = self.object.obrazek.url
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        formular:Otazka = form.save(commit=False)

        def clear_obrazek():
            if 'obrazek-clear' in form.data and formular.obrazek:
                formular.obrazek.delete()

        if form.instance.stav == 1:
            messages.warning(self.request,"Stav otázky nelze změnit, protože byla již schválena")
            return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
        else:
            if 'b-ulozit' in form.data:
                if Otazka.objects.filter(zadani=formular.zadani).exclude(pk=formular.pk).exists():
                    messages.warning(self.request,"Otázku nelze uložit, protože existuje jiná otázka se stejným zadáním.")
                    logger.warning("Uživatel {1} se pokusil uložit otázku {0} kterou nelze uložit, protože existuje jiná otázka se stejným zadáním.".format(formular,self.request.user))
                    return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
                else:
                    clear_obrazek()
                    formular.save()
                    messages.success(self.request,"Otázka byla uložena.")
                    logger.info("Uživatel {} uložil otázku {}".format(self.request.user,formular))
            if 'b-nahled' in form.data:
                if Otazka.objects.filter(zadani=formular.zadani).exclude(pk=formular.pk).exists():
                    messages.warning(self.request,"Otázku nelze uložit s náhledem, protože existuje jiná otázka se stejným zadáním.")
                    logger.warning("Uživatel {} se pokusil uložit s náhledem otázku {}, kterou nelze uložit, protože existuje jiná otázka se stejným zadáním.".format(self.request.user,formular))
                else:
                    clear_obrazek()
                    formular.save()
                    messages.success(self.request,"Otázka byla aktualizována.")
                    logger.info("Uživatel {} uložil s náhledem otázku {}.".format(self.request.user,formular))
                return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
            if 'b-schvalit' in form.data:
                if not self.request.user.has_perm('strela.kontrolazadani'):
                    messages.error(self.request, 'Ke schvalování otázek nemáte oprávnění!')
                    logger.warning(f'Uživatel {self.request.user} se pokusil schválit otázku {formular}, ale nemá k tomu oprávnění')
                    return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
                if Otazka.objects.filter(zadani=formular.zadani).exclude(pk=formular.pk).exists():
                    messages.warning(self.request,"Otázku nelze schválit, protože existuje jiná otázka se stejným zadáním.")
                    logger.warning("Uživatel {} se pokusil schválit otázku {}, kterou nelze schválit, protože existuje jiná otázka se stejným zadáním.".format(self.request.user,formular))
                    return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
                else:
                    clear_obrazek()
                    formular.stav = 1
                    formular.save()
                    messages.success(self.request, f"Otázka {formular.pk} byla schválena.")
                    logger.info("Otázka {} byla schválena uživatelem {} ".format(formular,self.request.user))
        return HttpResponseRedirect(reverse_lazy('otazky'))

    @transaction.atomic
    def form_invalid(self, form):
        if form.instance.stav == 1:
            if 'b-odschvalit' in form.data:
                if not self.request.user.has_perm('strela.kontrolazadani'):
                    messages.error(self.request, 'K odschválení otázek nemáte oprávnění!')
                    logger.warning(f'Uživatel {self.request.user} se pokusil odschválit otázku {form.instance}, ale nemá k tomu oprávnění')
                    return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (form.instance.pk,)))
                try:
                    souteze = Soutez.objects.filter(rok=now().year)  
                    otazka = Otazka.objects.get(pk=form.instance.pk)
                    if Soutez_Otazka.objects.filter(otazka=otazka, soutez__in=souteze).exists():
                        messages.warning(self.request, "Schválení nelze zrušit, protože otázka je použita v letošní soutěži.")
                        logger.warning("Uživatel {} se pokusil zrušit schválení otázce {}, které nelze zrušit, protože otázka je použita v letošní soutěži.".format(self.request.user,form.instance))
                        return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (form.instance.pk,)))
                    else:    
                        otazka.stav = 0
                        otazka.save()        
                        logger.info("Uživatel {1} zrušil schválení otázky {0}.".format(form.instance,self.request.user))
                        return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (form.instance.pk,)))    
                except Otazka.DoesNotExist as e:
                    messages.error(self.request,"Chyba - otázka nenalezena") 
                    logger.error("Chyba - otázka nenalezena {}".format(e))
        elif 'b-odschvalit' in form.data:
            messages.warning(self.request,"Stav otázky nelze změnit, protože schválení již bylo zrušeno.")
            logger.warning("Uživatel {} se pokusil zrušit schválení otázce {}, které nelze zrušit, protože schválení již bylo zrušeno jiným uživatekem".format(self.request.user,form.instance))
            return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (form.instance.pk,)))    
        return self.render_to_response(self.get_context_data(form=form))


class OtazkaAdminDelete(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    template_name = "admin/otazka_confirm_delete.html"
    model = Otazka
    success_url = reverse_lazy('otazky')
    permission_required = ['strela.kontrolazadani','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    success_message = "Otázka byla smazána."

    # SuccessMessageMixin nejde použít, protože závisí na form_valid, 
    # která je jen v potomcích  FormView 
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        logger.info("Uživatel {} smazal otázku {}.".format(request.user, self.get_object()))
        return super(OtazkaAdminDelete, self).delete(request, *args, **kwargs)


class KontrolaOdpovediIndex(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "admin/kontrola_reseni.html"
    permission_required = ['strela.kontrolareseni','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        soutez = Soutez.get_aktivni(admin=True)
        if soutez is not None:
            context["is_aktivni_soutez"] = True
            context["soutez_valid"] = True if soutez.prezencni == 'O' else False
        else:
            context["is_aktivni_soutez"] = False
        return context
    

class KontrolaOdpovediDetail(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = "admin/kontrola_reseni_detail.html"
    permission_required = ['strela.kontrolareseni','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Tym_Soutez_Otazka
    fields = []
    success_url = reverse_lazy("kontrola_odpovedi")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.object.otazka.otazka.obrazek:
            ctx['img_url'] = self.object.otazka.otazka.obrazek.url
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        formular:Tym_Soutez_Otazka = form.save(commit=False)
        if formular.stav != 2:
            return HttpResponseRedirect(self.get_success_url())

        try:
            team:Tym_Soutez = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.otazka.soutez)
        except Tym_Soutez.DoesNotExist as e:
            logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
            messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))
            return HttpResponseRedirect(self.get_success_url())

        if 'chybnaotazka' in form.data:
            formular.otazka.otazka.stav = 2
            formular.otazka.otazka.save()

        if 'b-spravne' in form.data:
            formular.stav = 3
            try:
                team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.otazka.soutez)
                team.penize += CENIK[self.object.otazka.otazka.obtiznost][1]
                logger.info("Uživatel {} zkontroloval týmu {} otázku {}. Otázka byla zodpovězena SPRÁVNĚ, týmu bylo přičteno {} DC"
                    .format(self.request.user,self.object.tym, formular, CENIK[self.object.otazka.otazka.obtiznost][1]))
                LogTable.objects.create(tym=self.object.tym, otazka=formular.otazka.otazka, soutez=self.object.otazka.soutez, staryStav=2, novyStav=3)    
                formular.save()
                team.save()
            except Tym_Soutez.DoesNotExist as e:
                logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
                messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))

        if 'b-spatne' in form.data:
            formular.stav = 7
            logger.info("Uživatel {} zkontroloval týmu {} otázku {}. Otázka byla zodpovězena ŠPATNĚ."
                .format(self.request.user,self.object.tym, formular))
            LogTable.objects.create(tym=self.object.tym, otazka=formular.otazka.otazka, soutez=self.object.otazka.soutez, staryStav=2, novyStav=7) 
            formular.save()

        if 'b-podpora' in form.data:
            formular.send_to_brazil(formular.tym, 0)
            logger.info("Uživatel {} zkontroloval týmu {} otázku {}. Otázka byla odeslána na technickou podporu."
                .format(self.request.user,self.object.tym, formular))
            LogTable.objects.create(tym=self.object.tym, otazka=formular.otazka.otazka, soutez=self.object.otazka.soutez, staryStav=2, novyStav=4)
            formular.save()

        return HttpResponseRedirect(self.get_success_url())


class AdminLogin(LoginView):
    template_name = "admin/admin_login.html"

    def form_valid(self, form):
        logger.info("Uživatel {} z IP {} byl úspěšně přihlášen do administrace soutěže.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
        messages.success(self.request, "Uživatel {} z IP {} byl úspěšně přihlášen do administrace soutěže.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
        return super().form_valid(form)


class AdminLogout(LogoutView):
    next_page = reverse_lazy("admin_index")

    def dispatch(self, request, *args, **kwargs):
        logger.info("Uživatel {} byl úspěšně odhlášen z administrace soutěže".format(request.user))
        messages.success(request, "Uživatel {} byl úspěšně odhlášen z administrace soutěže".format(request.user))
        response = super().dispatch(request, *args, **kwargs)
        return response


class KontrolaOdpovediJsAPI(PermissionRequiredMixin, ListView):
    permission_required = ['strela.kontrolareseni','strela.adminsouteze']
    template_name = 'admin/kontrola_reseni_jsapi.html'
    model = Tym_Soutez_Otazka

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        soutez = Soutez.get_aktivni(admin=True)
        if soutez is not None:
            context["is_aktivni_soutez"] = True
            context["soutez_valid"] = True if soutez.prezencni == 'O' else False
        else:
            context["is_aktivni_soutez"] = False
        return context
    
    def get_queryset(self):
        return Tym_Soutez_Otazka.objects.filter(otazka__soutez=Soutez.get_aktivni(admin=True), stav=2)


class AdminSoutez(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'strela.adminsouteze'
    model = Soutez    
    template_name = 'admin/soutez_list.html'
    login_url = reverse_lazy("admin_login")
    ordering = ['-rok']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['n'] = {}
        for s in context['soutez_list']:
            context['n'][s.pk] = Tym_Soutez.objects.filter(soutez=s).count()
        return context


class AdminNovaSoutez(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    template_name = 'admin/soutez_nova.html'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Soutez
    form_class = AdminNovaSoutezForm
    success_url = reverse_lazy("admin_soutez")

    def form_valid(self, form):
        # mala osklivost, zde nelogujeme textovou reprezentaci objektu jako jinde,
        # protoze jeji soucasti je rok, tery se vytvori az v pretizene metode save() v modelu. 
        # ve chvili kdy pouzivame instanci formu ještě rok neexistuje a zobrazuje se rok s hodnotou 0.
        logger.info("Uživatel {} založil novou soutěž {}.".format(self.request.user, form.instance.zamereni))
        messages.success(self.request, "Uživatel {} založil novou soutěž {}.".format(self.request.user, form.instance.zamereni))
        return super().form_valid(form)


class AdminSoutezDetail(LoginRequiredMixin, PermissionRequiredMixin, FormMixin, DetailView):
    template_name = 'admin/soutez_detail.html'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Soutez
    form_class = AdminZalozSoutezForm

    def get_success_url(self):
        return reverse_lazy('admin_soutez_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super(AdminSoutezDetail, self).get_context_data(**kwargs)
        # vybere všechny otázky přiřazené k dané soutěži, seskupí je podle obtížnosti
        # a sečte počty otázek v jednotlivých obtížnostech
        context["v_soutezi"] = Soutez_Otazka.objects.filter(soutez=self.object).order_by('otazka__obtiznost') \
            .values('otazka__obtiznost') \
            .annotate(total=Count('otazka__obtiznost'))
        # vezme součty obtížností z předchozího dotazu, udělá z nich list hodnot součtů a sečte je dohromady.
        context["v_soutezi_celkem"] = sum(context["v_soutezi"].values_list('total', flat=True))
        # vezmeme všechny schválené otázky použitelné v soutěži daného typu
        # a vyloučíme všechny otázky použité v předešlých 2 letech
        qs = Otazka.objects.filter(stav=1, typ__in=OTAZKASOUTEZ[self.object.typ]).exclude(
            Q(id__in=Tym_Soutez_Otazka.objects.filter(
                Q(otazka__soutez__rok__in=(now().year-1,now().year))
              | Q(otazka__soutez=self.object)
            ).values_list('otazka__otazka__id', flat=True))

          | Q(id__in=Soutez_Otazka.objects.filter(
                soutez=self.object
            ).values_list('otazka__id', flat=True))
        )
        # spočítáme všechny dostupné otázky a seskupíme podle obtížností
        context['dostupne'] = qs.values('obtiznost').annotate(total=Count('obtiznost'))

        # vezme počty otázek v jednotlivých obtížnostech z minulého dotazu,
        # udělá z nich list a sečte je dohromady
        context["dostupne_celkem"] = sum(context["dostupne"].values_list('total',flat=True))
        context["prihlaseno"]=Tym_Soutez.objects.filter(soutez=self.object).count()
        context["prihlaseno_skol"] = Tym_Soutez.objects.filter(soutez=self.object).values('tym__skola').distinct().aggregate(Count('tym__skola'))['tym__skola__count']
        context['form'] = self.get_form
        context['akt_rok'] = now().year
        context['tymy'] = Tym_Soutez.objects.filter(soutez=self.object).order_by('cislo')

        context['spustitelna'] = True
        context['nespustitelna_proc'] = ''

        context['tlacitko_vysledky'] = \
            self.object.zahajena \
            and ( \
                Soutez.get_aktivni(admin=True) == self.object \
                or datetime.timedelta(minutes=(120 + self.object.delkam)) + self.object.zahajena > now()
            ) \
            and self.object.rok == now().year \
            and not self.object.registrace

        if self.object.rok != now().year:
            context['spustitelna'] = False
            context['nespustitelna_proc'] = 'Nelze spustit soutěž, která není letošní.'
        elif self.object.get_aktivni():
            context['spustitelna'] = False
            context['nespustitelna_proc'] = 'Nelze spustit soutěž, pokud již nějaká běží.'
        elif self.object.registrace:
            context['spustitelna'] = False
            context['nespustitelna_proc'] = 'Nelze spustit soutěž, do které je ještě možné se registrovat.'
        elif self.object.zahajena:
            context['spustitelna'] = False
            context['nespustitelna_proc'] = 'Nelze spustit soutěž, která již byla spuštěna.'

        if 'cisloOtazky' in self.request.GET:
            try:
                cislo_otazky = int(self.request.GET['cisloOtazky'])
                context['otazka_search'] = Soutez_Otazka.objects.get(cisloVSoutezi=cislo_otazky, soutez=self.object).otazka
                context['otazka_search_num'] = cislo_otazky
            except Exception:
                messages.error(self.request, 'Nepodařilo se nalézt otázku s číslem ' + str(self.request.GET['cisloOtazky']))

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)    

    @transaction.atomic
    def form_valid(self, form):
        if 'b-otazky' in form.data:
            if self.object.rok != now().year:
                messages.error(self.request, "Otázky lze přidávat pouze do letošní soutěže, tj v roce {}".format(now().year))    
                logger.warning("Uživatel {} se pokusil přidat otázky do soutěže, která není letošní.".format(self.request.user))
            else:   
                pocet_otazek=int(form.data['pocet_otazek'])
                s = "Nastaveno přidání {}, přidáno otázek: ".format(pocet_otazek)
                ss = 0
                for obtiznost in FLAGDIFF:
                    try:
                        # vezme všechny schválené otázky použitelné v soutěži daného typu
                        qs = Otazka.objects.filter(stav=1, obtiznost=obtiznost[0], typ__in=OTAZKASOUTEZ[self.object.typ]).exclude(
                            Q(id__in=Tym_Soutez_Otazka.objects.filter(
                                Q(otazka__soutez__rok__in=(now().year-1,now().year))
                              | Q(otazka__soutez=self.object)
                            ).values_list('otazka__otazka__id', flat=True))

                          | Q(id__in=Soutez_Otazka.objects.filter(
                                soutez=self.object
                            ).values_list('otazka__id', flat=True))
                        )

                        qs = qs.order_by('-id')[:pocet_otazek]  # zaruci, ze nove vymyslene otazky se pridaji jako prvni
                        for o in qs:
                            Soutez_Otazka.objects.create(
                                soutez=self.object,
                                otazka=o,
                                cisloVSoutezi=get_next_value("rok-{}-soutez-{}-id-{}".format(self.object.rok,self.object.zamereni,self.object.pk))
                            )

                        pridano = qs.count()
                        s += "{}:{} ".format(obtiznost[0],pridano)
                        ss += pridano
                    except Exception as e:
                        messages.error(self.request, "Chyba při přidávání otázek do soutěže{}.".format(e))    
                        logger.error("Uživatel {} se pokusil přidat otázky do soutěže {}, došlo k chybě {}".format(self.request.user, self.object, e))
                s += ", celkem přidáno {}".format(ss)
                messages.success(self.request, s)
                logger.info("Uživatel {} se pokusil přidat otázky do soutěže {} s výsledkem {}.".format(self.request.user, self.object, s))
        if 'b-start' in form.data:
            bezici = Soutez.get_aktivni(admin=True)
            if self.object.rok != now().year:
                messages.error(self.request, "Lze zahájit pouze letošní soutěž, tj pro rok {}.".format(now().year))
                logger.error("Uživatel {} se pokusil zahájit soutěž, která není letos".format(self.request.user))
            elif self.object == bezici:
                messages.error(self.request, "Tato soutěž již běží.")
                logger.error("Uživatel {} se pokusil zahájit soutěž, která již běží.".format(self.request.user))
            elif bezici:
                messages.error(self.request, "Již běží {}, nelze spustit více soutěží najednou.".format(bezici))
                logger.error("Uživatel {} se pokusil zahájit více soutěží najednou, již běží {}.".format(self.request.user, bezici))
            elif self.object.registrace:
                messages.error(self.request, "Nelze spustit soutěž v průběhu registrace.")
                logger.error("Uživatel {} se pokusil zahájit soutěž v průběhu registrace.".format(self.request.user))
            elif self.object.zahajena is not None:
                messages.error(self.request, "Nelze spustit již dříve spuštěnou soutěž.")
                logger.error("Uživatel {} se pokusil zahájit již dříve spuštěnou soutěž.".format(self.request.user))
            else:    
                try:
                    soutez = self.object
                    soutez.aktivni=True
                    soutez.zahajena=now()
                    soutez.save()
                    messages.success(self.request, "Startuji soutěž {}".format(soutez))
                    logger.info("Uživatel {} odstartoval soutěž {}.".format(self.request.user, soutez))
                except Exception as e:
                    messages.error(self.request, "Chyba při startování soutěže{}.".format(e))
                    logger.error("Uživatel {} se pokusil zahájit soutěž, došlo k chybě {}.".format(self.request.user, e))
        return super(AdminSoutezDetail, self).form_valid(form)


class AdminSoutezSetMoney(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    form_class = AdminSoutezMoneyForm
    template_name = 'admin/soutez_add_money.html'

    def get_success_url(self):
        return reverse_lazy('admin_soutez_detail', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        soutez = Soutez.objects.get(pk=self.kwargs['pk'])
        context = super().get_context_data(**kwargs)
        
        context['soutez'] = soutez
        context['soutez_valid'] = \
            soutez.zahajena \
            and ( \
                Soutez.get_aktivni(admin=True) == soutez \
                or datetime.timedelta(minutes=(120 + soutez.delkam)) + soutez.zahajena > now()
            ) \
            and soutez.rok == now().year \
            and not soutez.registrace \
            and soutez.prezencni == 'P'

        return context

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs.update(self.kwargs)
        return form_kwargs

    @transaction.atomic
    def form_valid(self, form):
        soutez = Soutez.objects.filter(pk=self.kwargs['pk']).first()

        for key, val in form.cleaned_data.items():
            tym = Tym_Soutez.objects.get(tym__pk=int(key), soutez=soutez)
            tym.penize = int(val)
            tym.save()
            
        return super().form_valid(form)


class AdminPDFZadani(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    template_name = 'admin/zadani.tex'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Soutez

    def get(self, request, *args, **kwargs):
        soutez:Soutez = self.get_object()
        otazky = Soutez_Otazka.objects.filter(soutez=soutez)
        pom:list[dict[str, ]] = []
        o:Soutez_Otazka
        for o in otazky:
            if o.otazka.stav == 1:
                pom.append({
                    'cislo': o.cisloVSoutezi,
                    'zadani': tex_escape(o.otazka.zadani),
                    'typ': o.otazka.typ,
                    'obtiznost': o.otazka.obtiznost,
                    'cenik': CENIK[o.otazka.obtiznost],
                    'obrazek': o.otazka.obrazek
                })
        # seřadí otázky podle obtížnosti sestupně a v rámci obtížnosti podle délky,
        # aby se k sobě dostaly otázky s podobnou délkou a PDF vypadalo lépe.    
        pom.sort(key=lambda t: (t['obrazek']==None,t['obtiznost'],len(t['zadani'])), reverse=True)
        context = {'otazky': pom, 'images_path': settings.MEDIA_ROOT}
        logger.info("Uživatel {} vygeneroval PDF se zadáním pro soutěž {}.".format(self.request.user, soutez))
        return render_to_pdf(request, self.template_name, context, filename=slugify(soutez.get_typ_display())+'-'+str(soutez.rok)+'-zadani.pdf')


class AdminPDFVysledky(LoginRequiredMixin, PermissionRequiredMixin,DetailView):
    template_name = 'admin/vysledky.tex'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Soutez

    def get(self, request, *args, **kwargs):
        soutez:Soutez = self.get_object()
        otazky = Soutez_Otazka.objects.filter(soutez=soutez)
        pom:list[tuple[int, str]] = []
        o:Soutez_Otazka
        for o in otazky:
            if o.otazka.stav == 1:
                pom.append((o.cisloVSoutezi, tex_escape(o.otazka.reseni)))
        context = {'otazky': pom,
                   'soutez': tex_escape(soutez.zamereni)+" "+str(soutez.rok) }
        logger.info("Uživatel {} vygeneroval PDF s výsledky pro soutěž {}.".format(self.request.user, soutez))           
        return render_to_pdf(request, self.template_name, context, filename=slugify(soutez.get_typ_display())+'-'+str(soutez.rok)+'-vysledky.pdf')


class RegistraceIndex(CreateView):
    template_name = "strela/registrace_souteze.html"
    model = Tym
    form_class = RegistraceForm
    success_url = reverse_lazy("index_souteze")

    def get_context_data(self, **kwargs):
        context = super(RegistraceIndex, self).get_context_data(**kwargs)
        context.update(eval_registration(self))
        context['NUTS'] = CZ_NUTS_NAMES
        return context

    def form_valid(self, form):
        formular:Tym = form.save(commit=False)
        aktualni_rok = now().year
        formular.login = make_tym_login(formular.jmeno)
        password = Tym.objects.make_random_password(length=8, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        formular.set_password(password)
        formular.skola = Skola.objects.get(id=form.data['skola_1'])
        formular.save()

        # zpracujeme seznam soutezi na ktere se prihlasili
        souteze = Soutez.objects.filter(rok=aktualni_rok)
        soutez_list = []
        rx = re.compile('soutez(?P<pk>\d+)')
        try:
            for s in souteze:
                for k in form.data.keys():
                    m = rx.match(k)
                    if m is not None:
                        pk = int(m.group('pk'))
                        if s.pk == pk:
                            Tym_Soutez.objects.create(tym=formular, soutez=s, cislo=get_next_value(f'ts_{s.pk}'), penize=TYM_DEFAULT_MONEY)
                            soutez_list.append(s.pretty_name(True))
        except Exception as e:
            logger.error("Došlo k chybě {} při registraci týmu {} z IP {}".format(e, formular ,self.request.META['REMOTE_ADDR']))
            messages.error(self.request, "Došlo k chybě {} při registraci týmu {} z IP {}".format(e, formular ,self.request.META['REMOTE_ADDR']))
            return HttpResponseRedirect(reverse_lazy('registrace_souteze'))

        logger.info("Z IP {} byla provedena registrace týmu {}.".format(self.request.META['REMOTE_ADDR'], form.instance))
        # odeslání emailu s potvrzením registrace
        context = {
            'prijemce': formular.email,
            'heslo': password,
            'login': formular.login,
            'souteze': soutez_list,
            'tym': formular,
            'skola': formular.skola.nazev,
            'infotext': ''
        }
        try:
            context['infotext'] = KeyValueStore.objects.get(key='registrace_info').val
        except KeyValueStore.DoesNotExist:
            messages.error('Nenalezen záznam o informačním textu!')

        # finta - abychom nepřenášeli login a heslo mimo server mezi View,
        # vygenerujeme si náhodný klíč a pod tímto klíčem uložíme údaje do session
        # session je uložena v Memcached
        # do View s potvrzením předáme jen náhodný klíč a s jeho pomocí v get_context_data 
        # data ze session zase získáme.
        # oddělený klíč používáme, abychom mohli údaje snadno smazat.
        key = get_random_string(length=10)
        self.request.session.update({key:context})
        message = render_to_string('admin/email_registrace.txt', context)
        email = EmailMessage(
            subject = "Potvrzení registrace",
            body = message,
            to = (formular.email,) 
        )
        try:
            email.content_subtype = 'html'
            email.send()
            logger.info("Byl odeslán potvrzující email o registraci týmu {} na adresu {}.".format(formular, formular.email))

        except Exception as e:
            logger.error("Došlo k chybě {} při odesílání emailu na adresu {} o registraci týmu {}.".format(e, formular.email, formular))
            messages.error(self.request, "Došlo k chybě {} při odesílání emailu na adresu {} o registraci týmu {}.".format(e, formular.email, formular ))
        return HttpResponseRedirect(reverse_lazy('registrace-potvrzeni', args = (key,)))


class RegistracePotvrzeni(TemplateView):
    template_name = 'soutez/registrace_potvrzeni.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(eval_registration(self))
        try:
            context.update(self.request.session[kwargs['skey']])
            self.request.session[kwargs['skey']] = {}
        except KeyError as e: 
            logger.error("Došlo k chybě Key Error při vyzvedávání klíče {} pro potvrzení registrace.".format(e))
            messages.error(self.request, "Došlo k chybě Key Error při vyzvedávání klíče {} pro potvrzení registrace.".format(e))
        return context


class EmailInfo(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    template_name = "admin/mail_info.html"
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = EmailInfo
    form_class = AdminEmailInfo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.request.session.update({'soutez-email':self.kwargs['soutez']})
        context['pk'] = self.kwargs['soutez']
        return context

    def form_valid(self, form):
        formular:EmailInfo = form.save(commit=False)
        formular.odeslal = self.request.user
        try:
            soutez = Soutez.objects.get(id=self.request.session['soutez-email'])
        except Soutez.DoesNotExist as e:
            logger.error("Nastala chyba při vyzvedávání ID soutěže {}, nelze odeslat email.".format(e))
            messages.error(self.request, "Nastala chyba při vyzvedávání ID soutěže {}, nelze odeslat email.".format(e))
            return HttpResponseRedirect(reverse_lazy('admin_soutez'))
        formular.soutez = soutez
        prijemci = list(set(Tym.objects.filter(id__in = Tym_Soutez.objects.filter(soutez=soutez).values_list('tym__id',flat=True)).values_list('email',flat=True)))
        ok_list = []
        err_list = []
        attachments = []

        msg = lxhtml.fromstring(formular.zprava)
        imgs = msg.cssselect('img')
        for img in imgs:
            src = img.get('src')
            scheme, zbytek = src.split(':')

            # pokud je obrazek z internetu (a ne base64), neni treba nic delat
            if scheme != 'data': continue

            mime, content = zbytek.split(',')
            mime = mime.split(';')[0]

            # att_id = get_random_string(8)
            att = MIMEBase(*(mime.split('/')))
            att.set_payload(content)
            att.add_header('Content-Transfer-Encoding', 'base64')
            att['Content-Disposition'] = f'attachment; filename={img.get("title")}'
            # att.add_header('Content-ID', att_id)
            
            attachments.append(att)
            # img.set('src', f'cid:{att_id}')   # gmail nepodporuje vlozene obrazky
            img.drop_tree()

        for p in prijemci:
            email = EmailMessage(
                subject = f"Informace k soutěži {soutez}",
                to = [p]
            )

            email.content_subtype = 'related'
            email.attach(MIMEText(lxhtml.tostring(msg), 'html', 'utf-8'))
            for att in attachments:
                email.attach(att)

            try:
                email.send()
                logger.info("Byl odeslán informační email o soutěži {} na adresu {}.".format(soutez, p))
                ok_list.append(p)

            except Exception as e:
                logger.error("Došlo k chybě {} při odesílání informačního emailu o soutěži {} na adresu {}. ".format(e, soutez, p))
                err_list.append(f"{p} ({e})")

        formular.save()
        if ok_list:
            messages.success(self.request, "Email byl úslěšně odeslán následujícím příjemcům: {}".format(", ".join(ok_list)))
        if err_list:
            messages.error(self.request, "Došlo k chybě při odesílání následujícím příjemcům: {}".format(", ".join(err_list)))
        return HttpResponseRedirect(reverse_lazy('admin_soutez_detail', args = (soutez.pk,)))


class SoutezIndex(TemplateView):
    template_name = "soutez/soutez_index.html"

    def get_context_data(self, **kwargs):
        context = super(SoutezIndex, self).get_context_data(**kwargs)
        context.update(eval_registration(self))
        try:
            context['infotext'] = KeyValueStore.objects.get(key='soutez_index').val
        except KeyValueStore.DoesNotExist:
            messages.error(self.request, 'Článek nenalezen')
        return context


class SoutezLogin(LoginView):
    template_name = "strela/login_souteze.html"

    def form_valid(self, form):
        soutez = Soutez.get_aktivni()
        if soutez is not None:
            try:
                if Tym_Soutez.objects.filter(soutez=soutez, tym=form.get_user()).exists():
                    logger.info("Tým {} z IP {} byl úspěšně přihlášen do hry.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
                    messages.success(self. request, "Tým {} z IP {} byl úspěšně přihlášen do hry.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
                    return super().form_valid(form)
                else:
                    raise Exception
            except Exception:
                messages.error(self.request, 'Nemůžete se přihlásit do soutěže, do které jste se nezaregistrovali!')
                logger.warning("Tým {} z IP {} se pokusil přihlásit do soutěže {}, kam se nezaregistroval".format(form.get_user(),self.request.META['REMOTE_ADDR'], soutez))
                return HttpResponseRedirect(reverse_lazy('login_souteze'))
        else:
            logger.info("Tým {} z IP {} byl úspěšně přihlášen do hry.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
            messages.success(self. request, "Tým {} z IP {} byl úspěšně přihlášen do hry.".format(form.get_user(),self.request.META['REMOTE_ADDR']))
            return super().form_valid(form)


class SoutezLogout(LogoutView):
    next_page = reverse_lazy("herni_server")

    def dispatch(self, request, *args, **kwargs):
        logger.info("Tým {} byl úspěšně odhlášen ze hry.".format(request.user))
        response = super().dispatch(request, *args, **kwargs)
        messages.success(request, 'Byli jste úspěšně odhlášeni.')
        return response


class SoutezPravidla(TemplateView):
    template_name = "soutez/soutez_pravidla_index.html"

    def get_context_data(self, **kwargs):
        context = super(SoutezPravidla, self).get_context_data(**kwargs)
        context.update(eval_registration(self))
        try:
            context['infotext'] = KeyValueStore.objects.get(key='soutez_pravidla').val
        except KeyValueStore.DoesNotExist:
            messages.error(self.request, 'Článek nenalezen')
        return context


class SoutezVysledky(ListView):
    template_name = "soutez/soutez_vysledky.html"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(eval_registration(self))
        return context

    def get_queryset(self):
        return Soutez.objects.filter(zahajena__isnull=False, aktivni=False).order_by("-rok")


class SoutezVysledkyDetail(DetailView):
    template_name = "soutez/soutez_vysledek_detail.html"
    model = Soutez

    def get_context_data(self, **kwargs):
        context = super(SoutezVysledkyDetail, self).get_context_data(**kwargs)
        context.update(eval_registration(self))
        context["TvS"] = Tym_Soutez.objects.filter(soutez=self.object).order_by("-penize")
        return context


class HraIndexJsAPI(TemplateView):
    template_name = "soutez/hra_index_jsapi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["is_user_tym"] = isinstance(self.request.user, Tym)
        if not context["is_user_tym"]: return context

        context["cenik_o"] = list(zip(CENIK.items(), FLAGDIFF))
        try:
            context["aktivni_soutez"] = Soutez.get_aktivni()
            if context["aktivni_soutez"] is not None: context["soutez_valid"] = True if context["aktivni_soutez"].prezencni == 'O' else False
            context["tym"] = Tym_Soutez.objects.get(tym=self.request.user, soutez=context["aktivni_soutez"]) 
            context["otazky"] = Tym_Soutez_Otazka.objects.filter(tym=self.request.user, otazka__soutez=context["aktivni_soutez"]).exclude(otazka__otazka__id__in=Otazka.objects.filter(stav=2).values_list('id', flat=True))
            context["o_vyreseno"] = context["otazky"].filter(stav=3).count()
            context["o_zakoupene"] = context["otazky"].filter(Q(stav=1)|Q(stav=6)).count()
            context["o_problemy"] = context["otazky"].filter(Q(stav=4)|Q(stav=7)).count()
            context["is_user_tym"] = isinstance(self.request.user, Tym)

            n_nove_qs = Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"]).exclude(
                id__in=Tym_Soutez_Otazka.objects.filter(skola=context['tym'].tym.skola).values_list('otazka', flat=True)
            ).values('otazka__obtiznost').annotate(total=Count('otazka__obtiznost'))

            n_bazar_qs = Tym_Soutez_Otazka.objects.filter(
                Q(otazka__soutez=context["aktivni_soutez"])
                    & (
                        (
                            Q(stav=5)
                         & ~Q(skola=context['tym'].tym.skola)
                        )
                      | Q(id__in=Tym_Soutez_Otazka.objects.filter(skola=context['tym'].tym.skola, stav=5).values_list('id', flat=True))
                    )
                    & ~Q(tym=self.request.user)
            ).values('otazka__otazka__obtiznost').annotate(total=Count('otazka__otazka__obtiznost'))

            n_nove:dict[str, int] = { 'A' : 0 }
            n_bazar:dict[str, int] = { 'A' : 0 }
            for nqs in n_nove_qs:
                n_nove.update({ nqs['otazka__obtiznost'] : int(nqs['total']) })
            for nqs in n_bazar_qs:
                n_bazar.update({ nqs['otazka__otazka__obtiznost'] : int(nqs['total']) })

            n_nove['A'] += n_bazar['A']

            context["n_otazek_nove_slozitost"] = n_nove
            context["n_otazek_bazar_slozitost"] = n_bazar

        except Soutez.DoesNotExist as e:
            context["aktivni_soutez"] = None
            logger.error("Tým {} se snaží soutěžit když není aktivní žádná soutěž.".format(self.request.user))
        except Tym_Soutez.DoesNotExist:
            logger.error("Tým {} se pokouší soutěžit v {} kam ale není přihlášen.".format(self.request.user, context["aktivni_soutez"]))
        except Exception as e:
            context["api_db_err"] = f"{e}" #nechutny ale nevim jak jinak a tohle funguje
            logger.error("Došlo k chybě {}. Tým {} Soutěž {}".format(e, self.request.user, context["aktivni_soutez"]))
        
        if context["aktivni_soutez"] != None:
            konec = context["aktivni_soutez"].zahajena + datetime.timedelta(minutes = context["aktivni_soutez"].delkam)
            if konec - now() < datetime.timedelta(minutes=5):
                context["color"] = "danger"
                context['shop_open'] = False
            elif konec - now() < datetime.timedelta(minutes=15):
                context["color"] = "warning"
                context['shop_open'] = False
            else:
                context["color"] = "secondary"
                context['shop_open'] = True
            context["konec"] = konec.strftime('%H:%M')
        return context


class HraIndex(LoginRequiredMixin, TemplateView):
    template_name = "soutez/hra_index.html"
    login_url = reverse_lazy("login_souteze")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_user_tym"] = isinstance(self.request.user, Tym)
        context["soutez_valid"] = False
        if not context["is_user_tym"]: return context
        
        cenik = []
        d_diff = dict(FLAGDIFF)
        for o, c in CENIK.items():
            cenik.append((d_diff[o], c))
        context["cenik"] = cenik

        try:
            context["aktivni_soutez"] = Soutez.get_aktivni()
            if context["aktivni_soutez"] is not None: context["soutez_valid"] = True if context["aktivni_soutez"].prezencni == 'O' else False
        except Soutez.DoesNotExist as e:
            context["aktivni_soutez"] = None
            logger.error("Tým {} se snaží soutěžit když není aktivní žádná soutěž.".format(self.request.user))
        except Exception as e:
            messages.error(self.request, "Chyba databáze: " + e)
            logger.error("Došlo k chybě {}. Tým {} Soutěž {}".format(e, self.request.user, context["aktivni_soutez"]))

        if not context['aktivni_soutez']:
            context['souteze_tymu'] = [s.pretty_name(True) for s in Soutez.objects.filter(
                id__in=Tym_Soutez.objects.filter(tym=self.request.user).values_list('soutez', flat=True)
            )]
            context['soutezici'] = [
                self.request.user.soutezici1,
                self.request.user.soutezici2,
                self.request.user.soutezici3,
                self.request.user.soutezici4,
                self.request.user.soutezici5
            ] if context["is_user_tym"] else []
            context['skola'] = self.request.user.skola if context["is_user_tym"] else None
            context['email'] = self.request.user.email if context["is_user_tym"] else None
        return context


class HraUdalostitymu(LoginRequiredMixin, TemplateView):
    template_name = "soutez/hra_udalostitymu.html"
    login_url = reverse_lazy("login_souteze")
    
    def get_context_data(self, **kwargs):
        context = super(HraUdalostitymu, self).get_context_data(**kwargs)
        context['is_user_tym'] = isinstance(self.request.user, Tym)
        if not context["is_user_tym"]: return context

        aktivni_soutez = Soutez.get_aktivni()

        if aktivni_soutez:
            try:
                context["aktivni_soutez"] = aktivni_soutez
                if aktivni_soutez is not None: context["soutez_valid"] = True if aktivni_soutez.prezencni == 'O' else False
                context["log_tymu"] = LogTable.objects.filter(tym=self.request.user, soutez=aktivni_soutez).order_by('-cas')
            except Exception as e:
                messages.error(self.request, f"Chyba: {e}")
                logger.error("Tým {} chyba databáze: {}".format(self.request.user, e))
        else:
             context["aktivni_soutez"] = None       
        return context


class HraOtazkaDetail(LoginRequiredMixin, UpdateView):
    template_name = "soutez/hra_otazkadetail.html"
    login_url = reverse_lazy("login_souteze")
    model = Tym_Soutez_Otazka
    success_url = reverse_lazy("herni_server")
    form_class = HraOtazkaForm

    def get_context_data(self, **kwargs):
        context = super(HraOtazkaDetail, self).get_context_data(**kwargs)
        try:
            context["otazka"] = self.object.otazka
            context["tym"] = self.request.user
            context["is_user_tym"] = isinstance(self.request.user, Tym)
            context["was_otazka_podpora"] = self.object.bylaPodpora
            context["max_penize"] = Tym_Soutez.objects.get(tym=self.request.user, soutez=self.object.otazka.soutez).penize
            context["soutez_valid"] = True if self.object.otazka.soutez.prezencni == 'O' else False
            context["bazar_cena"] = CENIK[self.object.otazka.otazka.obtiznost][2]
            if self.object.otazka.otazka.obrazek:
                context['img_url'] = self.object.otazka.otazka.obrazek.url
            if self.object.otazka.soutez.aktivni:
                context["aktivni_soutez"] = True
            else:             
                messages.warning(self.request, "Není spuštěna žádná soutěž")
            if self.object.tym != self.request.user:
                context["nepatri"] = True
        except Exception as e:
            messages.error(self.request, f"Chyba: {e}")
            logger.error("Tým {} chyba databáze: {}".format(self.request.user, e))
        if self.object.bylaPodpora:
            self.request.session['chat_redirect_target'] = reverse_lazy('otazka-detail', args=(self.object.pk,))
            try:
                konverzace = ChatConvos.objects.get(otazka=self.object, tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=self.object.otazka.soutez))
                self.request.session['id_konverzace'] = konverzace.pk
                context['sazka_tymu'] = konverzace.sazka
            except (ChatConvos.DoesNotExist, Tym_Soutez.DoesNotExist):
                self.request.session['id_konverzace'] = None

        return context

    @transaction.atomic
    def form_valid(self, form):
        formular:Tym_Soutez_Otazka = form.save(commit=False)
        if formular.stav not in (1, 6, 7):
            messages.warning(self.request, f'Tato otázka nejde odevzdat, jelikož je ve stavu {formular.get_stav_display()}')
            return HttpResponseRedirect(self.get_success_url())
        if 'b-kontrola' in form.data:
            if self.object.otazka.otazka.vyhodnoceni == 0:
                if auto_kontrola_odpovedi(form.cleaned_data.get("odpoved"), self.object.otazka.otazka.reseni):
                    LogTable.objects.create(tym=formular.tym, otazka=formular.otazka.otazka, soutez=formular.otazka.soutez, staryStav=formular.stav, novyStav=3)
                    messages.info(self.request, "Otázka byla vyřešena")
                    formular.stav = 3
                    formular.odpoved = form.cleaned_data.get("odpoved")
                    try:
                        team:Tym_Soutez = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.otazka.soutez)
                        team.penize += CENIK[self.object.otazka.otazka.obtiznost][1]
                        logger.info("Tým {0} odevzdal otázku {1}, kterou zodpověděl SPRÁVNĚ ({3}) a získal {2} DC.".format(self.request.user, formular.otazka.otazka, CENIK[self.object.otazka.otazka.obtiznost][1], formular.odpoved))
                        formular.save()
                        team.save()
                    except Tym_Soutez.DoesNotExist as e:
                        logger.error(f"Nepodařilo se nalézt tým v soutěži {e}")
                        messages.error(self.request, f"Nepodařilo se nalézt tým v soutěži {e}")
                else:
                    LogTable.objects.create(tym=formular.tym, otazka=formular.otazka.otazka, soutez=formular.otazka.soutez, staryStav=formular.stav, novyStav=7)
                    messages.info(self.request, "Otázka byla zodpovězena špatně")
                    formular.stav = 7
                    formular.odpoved = form.cleaned_data.get("odpoved")
                    logger.info("Tým {0} odevzdal otázku {1}, na kterou odpověděl CHYBNĚ ({2}).".format(self.request.user, formular.otazka.otazka, formular.odpoved))
                    formular.save()
                    return HttpResponseRedirect(self.request.path_info)
            else:
                messages.info(self.request, "Otázka byla odeslána k hodnocení")
                LogTable.objects.create(tym=formular.tym, otazka=formular.otazka.otazka, soutez=formular.otazka.soutez, staryStav=formular.stav, novyStav=2)
                formular.stav = 2
                formular.odpoved = form.cleaned_data.get("odpoved")
                logger.info("Tým {} odevzdal otázku {} k ruční kontrole".format(self.request.user, formular.otazka.otazka))
                formular.save()
        elif 'b-bazar' in form.data:
            formular.sell()
            messages.info(self.request, "Otázka byla prodána do bazaru")
        elif 'b-podpora' in form.data:
            LogTable.objects.create(tym=formular.tym, otazka=formular.otazka.otazka, soutez=formular.otazka.soutez, staryStav=formular.stav, novyStav=4)
            formular.odpoved = form.cleaned_data.get("odpoved")

            konverzace = formular.send_to_brazil(self.request.user, form.cleaned_data.get('sazka') or 0)
            team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.otazka.soutez)
            if konverzace.sazka > CENIK[self.object.otazka.otazka.obtiznost][0] * 2:
                konverzace.sazka = CENIK[self.object.otazka.otazka.obtiznost][0] * 2
                messages.warning(self.request, "Byla překročena maximální výše sázky")
            if team.penize >= konverzace.sazka:
                team.penize -= konverzace.sazka
                messages.info(self.request, f'Bylo vsazeno {konverzace.sazka} DC')
            else:
                konverzace.sazka = team.penize  #tym nema dost penez, vsadi se vsechno
                team.penize = 0
                messages.warning(self.request, "Nedostatečná výše aktiv týmu, bylo vsazeno {} DC".format(konverzace.sazka))

            logger.info("Tým {} odeslal otázku {} na technickou podporu.".format(self.request.user, formular.otazka.otazka))
            if konverzace.sazka > 0:
                logger.info("Tým {} vsadil {} DC na otázku {}.".format(self.request.user, konverzace.sazka, formular.otazka.otazka))
            formular.save()
            team.save()
            konverzace.save()
            return HttpResponseRedirect(self.request.path_info)
        return super().form_valid(form)


class KoupitOtazku(LoginRequiredMixin, View):
    login_url = reverse_lazy("login_souteze")
    success_url = reverse_lazy("herni_server")

    @transaction.atomic
    def get(self, request, *args, **kwargs):
        is_bazar = self.kwargs["bazar"]
        obtiznost = self.kwargs["obtiznost"]
        soutez = Soutez.get_aktivni()

        try:
            if is_bazar:
                otazka = Tym_Soutez_Otazka.buy_bazar(request.user, soutez, obtiznost)
            else:
                otazka = Tym_Soutez_Otazka.buy(request.user, soutez, obtiznost)
            return redirect("otazka-detail", otazka.pk)
        except Exception as e:
            messages.error(request, e)
            return redirect("herni_server")


class SoutezVysledkyJsAPI(TemplateView):
    template_name = "soutez/soutez_vysledek_jsapi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            aktivni_soutez = Soutez.get_aktivni()
            if aktivni_soutez is not None: context["soutez_valid"] = True if aktivni_soutez.prezencni == 'O' else False
        except Soutez.DoesNotExist:
            messages.warning(self.request, "Není spuštěna žádná aktivní soutěź")
            logger.error("Není spuštěna žádná aktivní soutěź.")
            return context
        context["TvS"] = Tym_Soutez.objects.filter(soutez=aktivni_soutez).order_by("-penize")
        context["soutez"] = aktivni_soutez
        return context


class HraVysledky(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy("login_souteze")
    template_name = "soutez/hra_vysledky.html"

    def get_context_data(self, **kwargs):
        context = super(HraVysledky, self).get_context_data(**kwargs)
        context["is_user_tym"] = isinstance(self.request.user, Tym)
        if not context["is_user_tym"]: return context

        aktivni_soutez = Soutez.get_aktivni()
        if aktivni_soutez is not None:
            context["aktivni_soutez"] = True
            context["soutez_valid"] = True if aktivni_soutez.prezencni == 'O' else False
        else:
            context["aktivni_soutez"] = False
        return context


class ConvoListJsAPI(ListView):
    template_name = "soutez/convo_list_jsapi.html"
    model = ChatConvos

    def get_queryset(self):
        if isinstance(self.request.user, Tym):
            try:
                return ChatConvos.objects.filter(tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=Soutez.get_aktivni()))
            except Tym_Soutez.DoesNotExist:
                return ChatConvos.objects.none()
        elif self.request.user.has_perm('strela.podpora'):
            return ChatConvos.objects.filter(tym__soutez=Soutez.get_aktivni(admin=True))
        else:
            return ChatConvos.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["canSeeId"] = self.request.user.has_perm('strela.podpora')
        return context
        

class ChatListJsAPI(TemplateView):
    template_name = "soutez/chat_list_jsapi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['chat_errormsg'] = None
        try:
            convo_id = self.request.session['id_konverzace']
        except KeyError:
            context['chat_errormsg'] = "Tato konverzace buď neexistuje anebo k ní nemáte přístup"
            return context

        if isinstance(self.request.user, Tym):
            try:
                convo = ChatConvos.objects.get(id=convo_id, tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=Soutez.get_aktivni()))
            except (ChatConvos.DoesNotExist, Tym_Soutez.DoesNotExist):
                context['chat_errormsg'] = "Tato konverzace buď neexistuje anebo k ní nemáte přístup"
                return context
            tym2podpora = True

        elif self.request.user.has_perm('strela.podpora'):
            try:
                convo = ChatConvos.objects.get(id=convo_id)
            except ChatConvos.DoesNotExist:
                context['chat_errormsg'] = "Tato konverzace neexistuje"
                return context
            tym2podpora = False
        else:
            context['chat_errormsg'] = "K této konverzaci nemáte přístup"
            return context
        
        msgs_raw = ChatMsgs.objects.filter(konverzace=convo)
        msgs_out = []
        for msg in msgs_raw:
                msgs_out.append({
                    'dir_rel':tym2podpora if msg.smer == 0 else not tym2podpora,
                    'text':msg.text
                    })
    
        context['msgs'] = msgs_out
        return context


class ChatSend(FormMixin, View):
    form_class = forms.Form

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @transaction.atomic
    def form_valid(self, form):
        try:
            convo_id = self.request.session['id_konverzace']
            redirect_target = self.request.session['chat_redirect_target']
        except Exception:
            messages.error(self.request, "Konverzace nebyla nalezena")
            return HttpResponseRedirect(reverse_lazy('herni_server'))

        if isinstance(self.request.user, Tym):
            smer = 0
            try:
                convo = ChatConvos.objects.get(id=convo_id, tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=Soutez.get_aktivni()))
            except (ChatConvos.DoesNotExist, Tym_Soutez.DoesNotExist):
                messages.error(self.request, "Konverzace nebyla nalezena")
                return HttpResponseRedirect(reverse_lazy('herni_server'))

        elif self.request.user.has_perm('strela.podpora'):
            smer = 1
            try:
                convo = ChatConvos.objects.get(id=convo_id)
            except ChatConvos.DoesNotExist:
                messages.error(self.request, "Konverzace nebyla nalezena")
                return HttpResponseRedirect(reverse_lazy('herni_server'))

        else:
            messages.error(self.request, "K této konverzaci nemáte přístup")
            return HttpResponseRedirect(reverse_lazy('herni_server'))

        if convo.uzavreno == False:
            if len(form.data['text'].strip()) > 0:
                ChatMsgs.objects.create(smer=smer, konverzace=convo, text=form.data['text'].strip())
        else:
            messages.warning(self.request, "Zpráva nebyla uložena, neboť technická podpora otázku zamítla")
            logger.warning("Zpráva nebyla uložena, neboť technická podpora otázku zamítla ({} {}): '{}'".format(self.request.user, convo.otazka, form.data['text']))
        return HttpResponseRedirect(redirect_target)


class PodporaChatList(LoginRequiredMixin, PermissionRequiredMixin, FormMixin, TemplateView):
    template_name = "admin/podpora_list.html"
    permission_required = ['strela.podpora','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    form_class = forms.Form

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        soutez = Soutez.get_aktivni(admin=True)
        if soutez is not None:
            context["is_aktivni_soutez"] = True
            context["soutez_valid"] = True if soutez.prezencni == 'O' else False
        else:
            context["is_aktivni_soutez"] = False
        return context

    @transaction.atomic
    def form_valid(self, form):
        try:
            konverzace:ChatConvos = ChatConvos.objects.get(pk=self.request.session['id_konverzace'])
        except Exception:
            messages.error(self.request, "Konverzace nebyla nalezena")
            return HttpResponseRedirect(reverse_lazy('admin_index'))

        if konverzace.otazka is not None:
            if konverzace.otazka.stav != 4:
                return HttpResponseRedirect(reverse_lazy('podpora_list'))

        aktivni_soutez = Soutez.get_aktivni(admin=True)

        try:
            team:Tym_Soutez = Tym_Soutez.objects.get(tym=konverzace.tym.tym, soutez=aktivni_soutez)
        except Tym_Soutez.DoesNotExist as e:
            logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
            messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))
            return HttpResponseRedirect(reverse_lazy('admin_index'))
        
        if konverzace.otazka != None:
            if 'chybnaotazka' in form.data:
                konverzace.otazka.otazka.otazka.stav = 2
                konverzace.otazka.otazka.otazka.save()
                if isinstance(konverzace.sazka, int):
                    team.penize += konverzace.sazka * 2
                    logger.info("Uživatel {} uznal týmu {} otázku {}. Otázka byla zadána špatně, tým vyhrál sázku {} DC"
                        .format(self.request.user,konverzace.tym.tym, konverzace.otazka.otazka.otazka, konverzace.sazka * 2))
                
        if 'b-uznat' in form.data:
            if konverzace.otazka != None:
                konverzace.otazka.stav = 3
                konverzace.uzavreno = True
                konverzace.uznano = True
                
                team.penize += CENIK[konverzace.otazka.otazka.otazka.obtiznost][1]
                logger.info("Uživatel {} uznal týmu {} otázku {}. Otázka byla zodpovězena SPRÁVNĚ, týmu bylo přičteno {} DC"
                    .format(self.request.user,konverzace.tym.tym, konverzace.otazka.otazka.otazka, CENIK[konverzace.otazka.otazka.otazka.obtiznost][1]))
                
                LogTable.objects.create(tym=konverzace.tym.tym, otazka=konverzace.otazka.otazka.otazka, soutez=aktivni_soutez, staryStav=4, novyStav=3)
                messages.info(self.request, "Řešení týmu bylo uznáno") 
                konverzace.otazka.save()
                konverzace.save()
                
            else:
                konverzace.uzavreno = True
                konverzace.uznano = True
                konverzace.save()
   
        elif 'b-zamitnout' in form.data:
            if konverzace.otazka != None:
                konverzace.otazka.stav = 7
                konverzace.uzavreno = True
                konverzace.uznano = False
                logger.info("Uživatel {} zamítnul týmu {} otázku {}. Otázka byla zodpovězena ŠPATNĚ."
                    .format(self.request.user,konverzace.tym.tym, konverzace.otazka.otazka.otazka))
                LogTable.objects.create(tym=konverzace.tym.tym, otazka=konverzace.otazka.otazka.otazka, soutez=aktivni_soutez, staryStav=4, novyStav=7)
                messages.info(self.request, "Řešení týmu bylo zamítnuto")
                konverzace.otazka.save()
                konverzace.save()
            else:
                konverzace.uzavreno = True
                konverzace.uznano = False
                konverzace.save()
        
        team.save()
        return HttpResponseRedirect(reverse_lazy('podpora_list'))

    
class PodporaChat(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "admin/podpora_chat.html"
    permission_required = ['strela.podpora','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        id_konverzace = self.kwargs['pk']
        self.request.session['id_konverzace'] = id_konverzace
        self.request.session['chat_redirect_target'] = reverse_lazy('podpora_chat', args=(id_konverzace,))
        try:
            convo:ChatConvos = ChatConvos.objects.get(pk=id_konverzace)
            context['sazka_tymu'] = convo.sazka
            context['vyreseno'] = convo.uzavreno
            if convo.otazka:
                context['otazka'] = convo.otazka.otazka
                context['odpoved'] = convo.otazka.odpoved
                if convo.otazka.otazka.otazka.obrazek:
                    context['img_url'] = convo.otazka.otazka.otazka.obrazek.url
            context['uznano'] = convo.uznano
        except Exception as e:
            messages.error(self.request, "Chyba {}".format(e))
            logger.error("Konverzace s id {} nenalezena ({})".format(id_konverzace, e))
        return context
    

class TymChatList(LoginRequiredMixin, FormMixin, TemplateView):
    login_url = reverse_lazy('login_souteze')
    template_name = 'soutez/tym_chat_list.html'
    form_class = forms.Form

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_user_tym"] = isinstance(self.request.user, Tym)
        if not context["is_user_tym"]: return context

        aktivni_soutez = Soutez.get_aktivni()
        if aktivni_soutez is not None:
            context["aktivni_soutez"] = True
            context["soutez_valid"] = True if aktivni_soutez.prezencni == 'O' else False
        else:
            context["aktivni_soutez"] = False
        return context

    @transaction.atomic
    def form_valid(self, form):
        if 'b-kontaktovat' in form.data:
            soutez = Soutez.get_aktivni()
            if soutez is None:
                messages.error(self.request, 'Nemůžete kontaktovat podporu v soutěži, která neběží.')
                return HttpResponseRedirect(reverse_lazy('tym_chat_list'))
            try:
                konverzace:ChatConvos = ChatConvos.objects.get(tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=soutez), otazka=None)
                konverzace.uzavreno = False
                konverzace.save()
            except ChatConvos.DoesNotExist:
                konverzace = ChatConvos.objects.create(tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=soutez), uzavreno=False)
            return HttpResponseRedirect(reverse_lazy('tym_chat', args=(konverzace.pk,)))
        return HttpResponseRedirect(reverse_lazy('tym_chat_list'))


class TymChat(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy('login_souteze')
    template_name = 'soutez/tym_chat.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        id_konverzace = self.kwargs['pk']
        context["is_user_tym"] = isinstance(self.request.user, Tym)
        if not context["is_user_tym"]: return context

        aktivni_soutez = Soutez.get_aktivni()
        if aktivni_soutez is not None:
            context["aktivni_soutez"] = True
            context["soutez_valid"] = True if aktivni_soutez.prezencni == 'O' else False
        else:
            context["aktivni_soutez"] = False
            return context
        self.request.session['id_konverzace'] = id_konverzace
        self.request.session['chat_redirect_target'] = reverse_lazy('tym_chat', args=(id_konverzace,))
        try:
            convo:ChatConvos = ChatConvos.objects.get(pk=id_konverzace, tym=Tym_Soutez.objects.get(tym=self.request.user, soutez=aktivni_soutez))
            context['sazka_tymu'] = convo.sazka
            context['vyreseno'] = convo.uzavreno
            context['otazka'] = convo.otazka
            context['uznano'] = convo.uznano
        except ChatConvos.DoesNotExist:
            logger.error("Konverzace s id {} u týmu {} nenalezena".format(id_konverzace, self.request.user))
            messages.error(self.request, "Tato konverzace buď neexistuje anebo k ní nemáte přístup")
        except Exception as e:
            logger.error("Konverzace s id {} u týmu {} nenalezena".format(id_konverzace, self.request.user))
            messages.error(self.request, "Chyba: {}".format(e))
        return context


class Clock(TemplateView):
    template_name = 'strela/hodiny.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['soutez'] = Soutez.get_aktivni()
        return context

class QRClanek(TemplateView):
    template_name = 'strela/qr_clanek.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx['clanek'] = KeyValueStore.objects.get(key='qr_clanek').val
        except KeyValueStore.DoesNotExist:
            messages.error(self.request, 'Článek nenalezen')

        return ctx

class AdminTextList(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = ('strela.adminsouteze', 'strela.novasoutez')
    template_name = 'admin/admin_text_list.html'
    login_url = reverse_lazy("admin_login")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        texty = []
        for text in KeyValueStore.get_all_static():
            try: txt = lxhtml.fromstring(text.val).text_content()
            except: txt = ''

            texty.append({
                'key': text.key,
                'val': txt
            })
        
        ctx['texty'] = texty
        ctx['mapping'] = KeyValueStore.key_mapping
        return ctx

class AdminText(LoginRequiredMixin, PermissionRequiredMixin, FormMixin, TemplateView):
    permission_required = ('strela.adminsouteze', 'strela.novasoutez')
    template_name = 'admin/admin_text.html'
    login_url = reverse_lazy("admin_login")
    form_class = AdminTextForm

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(self.kwargs)
        return kwargs

    def form_valid(self, form):
        try:
            infotext = KeyValueStore.objects.get(key=form.infotext_key)
            infotext.val = form.data['infotext']
            infotext.save()
        except Exception as e:
            messages.error(self.request, f'Chyba při uložení informačního textu ({e})')

        return HttpResponseRedirect(reverse_lazy('admin_text_list'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({'nazev': KeyValueStore.key_mapping[kwargs['key']]})
        return ctx

class AdminPozvanky(LoginRequiredMixin, PermissionRequiredMixin, FormMixin, TemplateView):
    permission_required = 'strela.adminsouteze'
    template_name = 'admin/soutez_pozvanky.html'
    login_url = reverse_lazy("admin_login")
    form_class = AdminPozvankyForm

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['soutez'] = Soutez.objects.get(id=kwargs['soutez_pk']).pretty_name(True)
        # ctx['soutez'] = Soutez.objects.get(id=kwargs['form'].soutez_pk).pretty_name(True)
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['soutez_pk'] = self.kwargs['soutez_pk']
        return kwargs

    def form_valid(self, form:AdminPozvankyForm):
        soutez = Soutez.objects.get(id=form.soutez_pk)

        if not soutez.registrace:
            messages.error(self.request, 'Nelze poslat pozvánky na soutěž, kam se nezlze registrovat!')
            return HttpResponseRedirect(reverse_lazy('admin_soutez_detail', args=(form.soutez_pk,)))

        rx = re.compile(r'kraj-CZ0.{3}')
        send_btn = 'b-send' in form.data
        skoly_mails = set()

        cache.set('mail_q_subject', form.data['pleb_subject'])
        cache.set('mail_q_subject_vip', form.data['vip_subject'])
        
        def update_mails(s):
            skoly_mails.update(s.values_list('email1', flat=True))
            skoly_mails.update(s.values_list('email2', flat=True))

        def clean_set(s:"set[str]"):
            try: s.remove(None)
            except: pass
            try: s.remove('')
            except: pass

        vip_skoly_all = Tym_Soutez.objects.filter(
            soutez__in=Soutez.objects.filter(
                rok__in=(now().year, now().year-1)
            ).exclude(id=soutez.id)
        ).distinct()

        # vsechny skoly ze vsech okresu vybranych ve formulari
        allowed_ids = set()
        for k in form.data:
            if not rx.match(k): continue
            else:
                vl = self.request.POST.getlist(k)
                skoly = Skola.objects.filter(region=k[8], kraj=k[9])    # k = (napr.) kraj-CZ0100
                if 'on' in vl:
                    allowed_ids.update(skoly.values_list('id', flat=True))
                    update_mails(skoly.exclude(
                        id__in=vip_skoly_all.values_list('tym__skola__id', flat=True)
                    ))
                else:
                    for v in vl:
                        skoly = skoly.filter(okres=v[5])
                        allowed_ids.update(skoly.values_list('id', flat=True))
                        update_mails(skoly.exclude(
                            id__in=vip_skoly_all.values_list('tym__skola__id', flat=True)
                        ))
        clean_set(skoly_mails)

        # vsechny skoly, ktere jsou ve vybranych regionech a jejichz tymy se
        # v poslednich 2 letech ucastnily nejakych soutezi
        vip_skoly = vip_skoly_all.filter(tym__skola__id__in=allowed_ids).distinct()
        vip_mails = set(vip_skoly.values_list('tym__email', flat=True))
        clean_set(vip_mails)

        skoly_mails = skoly_mails.difference(vip_mails)
        if send_btn:
            try:
                BulkMailSender.add_emails(vip_mails, True)
                BulkMailSender.add_emails(skoly_mails, False)
                BulkMailSender.send_mails()
            except Exception as e:
                messages.error(self.request, e)

        messages.warning(self.request, f'Nastaveno rozeslání {len(skoly_mails)} normálních a {len(vip_mails)} VIP pozvánek.')
        return HttpResponseRedirect(reverse_lazy('admin_soutez_detail', args=(form.soutez_pk,)))

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)