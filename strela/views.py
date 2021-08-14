from django.core import exceptions
from django.db.models.expressions import OrderBy
from django.utils.timezone import now
from django.shortcuts import render, redirect
from django_tex.shortcuts import render_to_pdf
from django.views.generic import ListView, TemplateView, CreateView, DetailView
from django.views import View
from django.views.generic.edit import FormView, UpdateView, DeleteView, FormMixin
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.db.models import Q, Count
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from sequences import get_next_value

from . models import Tym, Soutez, Skola, Tym_Soutez, LogTable, Otazka, Tym_Soutez_Otazka, EmailInfo, ChatConvos, ChatMsgs
from . utils import eval_registration, tex_escape
from . forms import RegistraceForm, HraOtazkaForm, AdminNovaSoutezForm, AdminNovaOtazka, AdminZalozSoutezForm, AdminEmailInfo, AdminSoutezMoneyForm
from . models import FLAGDIFF, CENIK, OTAZKASOUTEZ

from django import forms

import datetime
import logging
logger = logging.getLogger(__name__)


class AdministraceIndex(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = "admin/admin_index.html"
    permission_required = 'strela.adminsouteze'
    login_url = reverse_lazy("admin_login")

    def get_context_data(self, **kwargs):
        context = super(AdministraceIndex, self).get_context_data(**kwargs)
        context["aktivni_soutez"] = Soutez.get_aktivni()
        context["n_otazek_celkem"] = Tym_Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"]).count()
        stavy = Tym_Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"]).values('stav').annotate(total=Count('stav'))
        s = [0, 0, 0, 0, 0, 0, 0, 0]
        for stav in stavy:
            s[stav["stav"]] = stav["total"]
        context["n_otazek_stav_count"] = s
        context["n_otazek_nove_slozitost"] = Tym_Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"], stav=0).values('otazka__obtiznost').annotate(total=Count('otazka__obtiznost'))
        context["n_otazek_bazar_slozitost"] = Tym_Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"], stav=5).values('otazka__obtiznost').annotate(total=Count('otazka__obtiznost'))
        context["n_otazek_chybne"] = Otazka.objects.filter(stav=2, id__in=Tym_Soutez_Otazka.objects.filter(soutez=context["aktivni_soutez"]).values_list('otazka__id', flat=True)).count()

        context["n_tymu"] = Tym_Soutez.objects.filter(soutez=context["aktivni_soutez"]).count()

        if context["aktivni_soutez"] != None:
            konec = context["aktivni_soutez"].zahajena + datetime.timedelta(minutes = context["aktivni_soutez"].delkam)
            if konec - now() < datetime.timedelta(minutes=5):
                context["color"] = "danger"
            elif konec - now() < datetime.timedelta(minutes=15):
                context["color"] = "warning"
            else:
                context["color"] = "secondary"
            context["konec"] = konec.strftime('%H:%M')
        return context
    

class NovaOtazka(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    template_name = "admin/nova_otazka.html"
    permission_required = ['strela.zadavatel','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Otazka
    success_url = reverse_lazy("otazky")
    form_class = AdminNovaOtazka

    @transaction.atomic
    def form_valid(self, form):
        formular = form.save(commit=False)
        formular.stav = 0
        formular.save()
        if 'b-ulozit' in form.data:
            logger.info("Uživatel {1} uložil otázku {0}.".format(formular,self.request.user))
            return super().form_valid(form)
        if 'b-nahled' in form.data:
            logger.info("Uživatel {1} uložil otázku {0} s náhledem.".format(formular,self.request.user))
            messages.success(self.request, "Nová otázka byla uložena.")
            return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.id,)))


class Otazky(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, ListView):
    template_name = "admin/otazky.html"
    login_url = reverse_lazy("admin_login")
    success_message = "Otázka byla uložena."

    def has_permission(self):
        user = self.request.user
        return user.has_perm('strela.adminsouteze') and (user.has_perm('strela.zadavatel') or user.has_perm('strela.kontrolazadani'))
    
    def get_queryset(self):
        if self.request.user.has_perm('strela.zadavatel'):
            qs = Otazka.objects.filter(stav = 0)
        if self.request.user.has_perm('strela.kontrolazadani'):
            qs =  Otazka.objects.all()
        return qs


class OtazkaAdminDetail(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = "admin/detail_otazky.html"
    login_url = reverse_lazy("admin_login")
    model = Otazka
    fields = ['typ','zadani','reseni','obtiznost','vyhodnoceni']
    
    def has_permission(self):
        user = self.request.user
        return user.has_perm('strela.adminsouteze') and (user.has_perm('strela.zadavatel') or user.has_perm('strela.kontrolazadani'))

    @transaction.atomic
    def form_valid(self, form):
        formular = form.save(commit=False)
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
                    formular.save()
                    messages.success(self.request,"Otázka byla uložena.")    
                    logger.info("Uživatel {} uložil otázku {}".format(self.request.user,formular))
            if 'b-nahled' in form.data:
                if Otazka.objects.filter(zadani=formular.zadani).exclude(pk=formular.pk).exists():
                    messages.warning(self.request,"Otázku nelze uložit s náhledem, protože existuje jiná otázka se stejným zadáním.")
                    logger.warning("Uživatel {} se pokusil uložit s náhledem otázku {}, kterou nelze uložit, protože existuje jiná otázka se stejným zadáním.".format(self.request.user,formular))
                else:    
                    formular.save()
                    messages.success(self.request,"Otázka byla aktualizována.")    
                    logger.info("Uživatel {} uložil s náhledem otázku {}.".format(self.request.user,formular))
                return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
            if 'b-schvalit' in form.data:
                if Otazka.objects.filter(zadani=formular.zadani).exclude(pk=formular.pk).exists():
                    messages.warning(self.request,"Otázku nelze schválit, protože existuje jiná otázka se stejným zadáním.")
                    logger.warning("Uživatel {} se pokusil schválit otázku {}, kterou nelze schválit, protože existuje jiná otázka se stejným zadáním.".format(self.request.user,formular))
                    return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (formular.pk,)))
                else:     
                    formular.stav = 1
                    formular.save()
                    messages.success(self.request,"Otázka byla schválena.")       
                    logger.info("Otázka {} byla schválena uživatelem {} ".format(formular,self.request.user))
        return HttpResponseRedirect(reverse_lazy('otazky'))

    @transaction.atomic
    def form_invalid(self, form):
        if form.instance.stav == 1:
            if 'b-odschvalit' in form.data:
                try:
                    souteze = Soutez.objects.filter(rok=now().year)  
                    otazka = Otazka.objects.get(pk=form.instance.pk)
                    if Tym_Soutez_Otazka.objects.filter(otazka=otazka, soutez__in=souteze).exists():
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
            return self.render_to_response(self.get_context_data(form=form))
        else:
            messages.warning(self.request,"Stav otázky nelze změnit, protože schválení již bylo zrušeno.")
            logger.warning("Uživatel {} se pokusil zrušit schválení otázce {}, které nelze zrušit, protože schválení již bylo zrušeno jiným uživatekem".format(self.request.user,form.instance))
            return HttpResponseRedirect(reverse_lazy('admin-otazka-detail', args = (form.instance.pk,)))


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
        context["is_aktivni_soutez"] = True if Soutez.get_aktivni() != None else False
        return context
    

class KontrolaOdpovediDetail(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    template_name = "admin/kontrola_reseni_detail.html"
    permission_required = ['strela.kontrolareseni','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = Tym_Soutez_Otazka
    fields = []
    success_url = reverse_lazy("kontrola_odpovedi")

    @transaction.atomic
    def form_valid(self, form):
        formular = form.save(commit=False)
        if 'b-spravne' in form.data:
            formular.stav = 3
            try:
                team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.soutez)
                team.penize += CENIK[self.object.otazka.obtiznost][1]
                logger.info("Uživatel {} zkontroloval týmu {} otázku {}. Otázka byla zodpovězena SPRÁVNĚ, týmu bylo přičteno {} DC"
                    .format(self.request.user,self.object.tym, formular, CENIK[self.object.otazka.obtiznost][1]))
                LogTable.objects.create(tym=self.object.tym, otazka=formular.otazka, soutez=self.object.soutez, staryStav=2, novyStav=3)    
                formular.save()
                team.save()
            except Tym_Soutez.DoesNotExist as e:
                logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
                messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))

        if 'b-spatne' in form.data:
            formular.stav = 7
            logger.info("Uživatel {} zkontroloval týmu {} otázku {}. Otázka byla zodpovězena ŠPATNĚ."
                .format(self.request.user,self.object.tym, formular))
            LogTable.objects.create(tym=self.object.tym, otazka=formular.otazka, soutez=self.object.soutez, staryStav=2, novyStav=7) 
            formular.save()
        return super(KontrolaOdpovediDetail, self).form_valid(form)


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
        context["is_aktivni_soutez"] = True if Soutez.get_aktivni() != None else False
        return context
    
    def get_queryset(self):
        return Tym_Soutez_Otazka.objects.filter(soutez=Soutez.get_aktivni(), stav=2)


class AdminSoutez(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'strela.adminsouteze'
    model = Soutez    
    template_name = 'admin/soutez_list.html'
    login_url = reverse_lazy("admin_login")
    ordering = ['-rok']


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
        context["v_soutezi"] = Tym_Soutez_Otazka.objects.filter(soutez=self.object) \
            .values('otazka__obtiznost') \
            .annotate(total=Count('otazka__obtiznost'))
        # vezme součty obtížností z předchozího dotazu, udělá z nich list hodnot součtů a sečte je dohromady.    
        context["v_soutezi_celkem"] = sum(context["v_soutezi"].values_list('total', flat=True))
        # vezme všechny schválené otázky použitelné v soutěži daného typu
        qs = Otazka.objects.filter(stav=1, typ__in=OTAZKASOUTEZ[self.object.typ])
        # ze seznamu otázek vyloučí otázky použité v letošních nebo loňských soutěžích
        # otázky seskupí podle obtížnosti a sečte počty otázek v jednotlivých obtížnostech
        context["dostupne"] = qs.exclude(id__in=list(Tym_Soutez_Otazka.objects  
                .filter(soutez__rok__in=(now().year-1,now().year)) 
                .values_list('otazka__id', flat=True)))  \
            .values('obtiznost') \
            .annotate(total=Count('obtiznost')) 
        # vezme počty otázek v jednotlivých obtížnostech z minulého dotazu,
        # udělá z nich list a sečte je dohromady
        context["dostupne_celkem"] = sum(context["dostupne"].values_list('total',flat=True))    
        context["prihlaseno"]=Tym_Soutez.objects.filter(soutez=self.object).count()
        context['form'] = self.get_form
        context['akt_rok'] = now().year
        context['tymy'] = Tym.objects.filter(id__in = Tym_Soutez.objects.filter(soutez=self.object).values_list('tym__id', flat=True))
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
                        qs = Otazka.objects.filter(stav=1, obtiznost=obtiznost[0])
                        # vezme všechny schválené otázky použitelné v soutěži daného typu
                        qs = qs.filter(typ__in=OTAZKASOUTEZ[self.object.typ])
                        qs = qs.exclude(id__in=list(Tym_Soutez_Otazka.objects
                                    .filter(soutez__rok__in=(now().year-1,now().year))
                                    .values_list('otazka__id', flat=True)))    
                        qs = qs.order_by('?')[:pocet_otazek//5]
                        for o in qs:
                            Tym_Soutez_Otazka.objects.create(soutez=self.object, otazka=o, stav=0,
                                cisloVSoutezi=get_next_value("rok-{}-soutez-{}-id-{}".format(self.object.rok,self.object.zamereni,self.object.pk)))
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
            bezici = Soutez.get_aktivni()
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
        context['prihlaseno'] = Tym_Soutez.objects.filter(soutez=soutez).count()
        #context['form'] = self.get_form

        return context

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs.update(self.kwargs)
        return form_kwargs

    @transaction.atomic
    def form_valid(self, form):
        for key, val in form.cleaned_data.items():
            tym = Tym_Soutez.objects.get(tym__pk=int(key))
            tym.penize = int(val)
            tym.save()
            
        return super().form_valid(form)


class AdminPDFZadani(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    template_name = 'admin/zadani.tex'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model=Soutez

    def get(self, request, *args, **kwargs):
        soutez = self.get_object()
        otazky = Tym_Soutez_Otazka.objects.filter(soutez=soutez)
        pom = []
        for o in otazky:
            pom.append((o.cisloVSoutezi,
                        tex_escape(o.otazka.zadani), 
                        o.otazka.obtiznost,
                        CENIK[o.otazka.obtiznost][0],
                        CENIK[o.otazka.obtiznost][1],
                        CENIK[o.otazka.obtiznost][2]))
        # seřadí otázky podle obtížnosti sestupně a v rámci obtížnosti podle délky,
        # aby se k sobě dostaly otázky s podobnou délkou a PDF vypadalo lépe.    
        pom.sort(key=lambda t: (t[2],len(t[1])), reverse=True)
        context = {'otazky': pom }
        logger.info("Uživatel {} vygeneroval PDF se zadáním pro soutěž {}.".format(self.request.user, soutez))
        return render_to_pdf(request, self.template_name, context, filename='test.pdf')


class AdminPDFVysledky(LoginRequiredMixin, PermissionRequiredMixin,DetailView):
    template_name = 'admin/vysledky.tex'
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model=Soutez

    def get(self, request, *args, **kwargs):
        soutez = self.get_object()
        otazky = Tym_Soutez_Otazka.objects.filter(soutez=soutez)
        pom = []
        for o in otazky:
            pom.append((o.cisloVSoutezi, o.otazka.reseni))
        context = {'otazky': pom,
                   'soutez': tex_escape(soutez.zamereni)+" "+str(soutez.rok) }
        logger.info("Uživatel {} vygeneroval PDF s výsledky pro soutěž {}.".format(self.request.user, soutez))           
        return render_to_pdf(request, self.template_name, context, filename='test.pdf')


class RegistraceIndex(CreateView):
    template_name = "strela/registrace_souteze.html"
    model = Tym
    form_class = RegistraceForm
    success_url = reverse_lazy("index_souteze")

    def get_context_data(self, **kwargs):
        context = super(RegistraceIndex, self).get_context_data(**kwargs)
        context.update(eval_registration(self))
        return context

    def form_valid(self, form):
        formular = form.save(commit=False)
        aktualni_rok = now().year
        formular.login=slugify(formular.jmeno).replace("-", "") + str(aktualni_rok)
        password = Tym.objects.make_random_password(length=8, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        formular.set_password(password)
        formular.cislo=get_next_value(aktualni_rok)
        # zpracujeme seznam soutezi na ktere se prihlasili
        souteze = Soutez.objects.filter(rok=aktualni_rok)
        formular.save()
        soutez_txt = ""
        try:
            for s in souteze:
                if form.data.get("soutez"+s.typ):
                    Tym_Soutez.objects.create(tym=formular, soutez=s)
                    soutez_txt += str(s) +" "
        except Exception as e:
            logger.error("Došlo k chybě {} při registraci týmu {}  z IP {}".format(e, formular ,self.request.META['REMOTE_ADDR']))    
            messages.error(self.request, "Došlo k chybě {} při registraci týmu {}  z IP {}".format(e, formular ,self.request.META['REMOTE_ADDR']))

        logger.info("Z IP {} byla provedena registrace týmu {}.".format(self.request.META['REMOTE_ADDR'], form.instance))
        # odeslání emailu s potvrzením registrace
        context = {
            'prijemce': formular.email,
            'heslo': password,
            'login': formular.login,
            'souteze': soutez_txt
        }
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
            subject = "Potvrzení registrace.",
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


class EmailInfo(LoginRequiredMixin, PermissionRequiredMixin,CreateView):
    template_name = "admin/mail_info.html"
    permission_required = ['strela.novasoutez','strela.adminsouteze']
    login_url = reverse_lazy("admin_login")
    model = EmailInfo
    form_class = AdminEmailInfo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.request.session.update({'soutez-email':self.kwargs['soutez']})
        return context

    def form_valid(self, form):
        formular = form.save(commit=False)
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
        for p in prijemci:
            email = EmailMessage(
                subject = "Informace k soutěži {}".format(soutez),
                body = formular.zprava,
                to = (p,) 
            )
            try:
                email.content_subtype = 'html'
                email.send()
                logger.info("Byl odeslán informační email o soutěži {} na adresu {}.".format(soutez, p))
                ok_list.append(p)

            except Exception as e:
                logger.error("Došlo k chybě {} při odesílání informačního emailu o soutěži {} na adresu {}. ".format(e, soutez, p))
                err_list.append(p)

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
        return context


class SoutezVysledky(ListView):
    template_name = "soutez/soutez_vysledky.html"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(eval_registration(self))
        return context

    def get_queryset(self):
        return Soutez.objects.filter(zahajena__isnull=False).order_by("-rok")


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
        context["cenik_o"] = list(zip(CENIK.items(), FLAGDIFF))
        try:
            context["aktivni_soutez"] = Soutez.get_aktivni()
            context["tym"] = Tym_Soutez.objects.get(tym=self.request.user, soutez=context["aktivni_soutez"]) 
            context["otazky"] = Tym_Soutez_Otazka.objects.filter(tym=self.request.user, soutez=context["aktivni_soutez"]).exclude(otazka__id__in=Otazka.objects.filter(stav=2).values_list('id', flat=True))
            context["o_vyreseno"] = context["otazky"].filter(stav=3).count()
            context["o_zakoupene"] = context["otazky"].filter(Q(stav=1)|Q(stav=6)).count()
            context["o_problemy"] = context["otazky"].filter(Q(stav=4)|Q(stav=7)).count()
            context["is_user_tym"] = isinstance(self.request.user, Tym)
        except Soutez.DoesNotExist as e:
            context["aktivni_soutez"] = None
            logger.error("Tým {} se snaží soutěžit když není aktivní žádná soutěž.".format(self.request.user))
        except Tym_Soutez.DoesNotExist:
            logger.error("Tým {} se pokouší soutěžit v {} kam ale není přihlášen.".format(self.request.user, context["aktivni_soutez"]))
        except Exception as e:
            context["api_db_err"] = "{0}".format(e) #nechutny ale nevim jak jinak a tohle funguje
            logger.error("Došlo k chybě {}. Tým {} Soutěž {}".format(e, self.request.user, context["aktivni_soutez"]))
        
        if context["aktivni_soutez"] != None:
            konec = context["aktivni_soutez"].zahajena + datetime.timedelta(minutes = context["aktivni_soutez"].delkam)
            if konec - now() < datetime.timedelta(minutes=5):
                context["color"] = "danger"
            elif konec - now() < datetime.timedelta(minutes=15):
                context["color"] = "warning"
            else:
                context["color"] = "secondary"
            context["konec"] = konec.strftime('%H:%M')
        return context


class HraIndex(LoginRequiredMixin, TemplateView):
    template_name = "soutez/hra_index.html"
    login_url = reverse_lazy("login_souteze")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_user_tym"] = isinstance(self.request.user, Tym)
        try:
            context["aktivni_soutez"] = Soutez.get_aktivni()
        except Soutez.DoesNotExist as e:
            context["aktivni_soutez"] = None
            logger.error("Tým {} se snaží soutěžit když není aktivní žádná soutěž.".format(self.request.user))
        except Exception as e:
            messages.error(self.request, "Chyba databáze: " + e)
            logger.error("Došlo k chybě {}. Tým {} Soutěž {}".format(e, self.request.user, context["aktivni_soutez"]))
        return context


class HraUdalostitymu(LoginRequiredMixin, TemplateView):
    template_name = "soutez/hra_udalostitymu.html"
    login_url = reverse_lazy("login_souteze")
    
    def get_context_data(self, **kwargs):
        context = super(HraUdalostitymu, self).get_context_data(**kwargs)
        aktivni_soutez = Soutez.get_aktivni()

        if aktivni_soutez:
            try:
                context["aktivni_soutez"] = aktivni_soutez
                context["log_tymu"] = LogTable.objects.filter(tym=self.request.user, soutez=aktivni_soutez).order_by('-cas')
            except Exception as e:
                messages.error(self.request, "Chyba: {0}".format(e))
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
            context["max_penize"] = Tym_Soutez.objects.get(tym=self.request.user, soutez=self.object.soutez).penize
            if self.object.soutez.aktivni:
                context["aktivni_soutez"] = True
            else:             
                messages.warning(self.request, "Není spuštěna žádná soutěž")
            if self.object.tym != self.request.user:
                context["nepatri"] = True
        except Exception as e:
            messages.error(self.request, "Chyba: {0}".format(e))
            logger.error("Tým {} chyba databáze: {}".format(self.request.user, e))
        if self.object.bylaPodpora:
            self.request.session['chat_redirect_target'] = reverse_lazy('otazka-detail', args=(self.object.pk,))
            try:
                konverzace = ChatConvos.objects.get(otazka=self.object, tym=self.request.user)
                self.request.session['id_konverzace'] = konverzace.pk
                context['sazka_tymu'] = konverzace.sazka
            except ChatConvos.DoesNotExist:
                self.request.session['id_konverzace'] = None

        return context

    @transaction.atomic
    def form_valid(self, form):
        formular = form.save(commit=False)
        if 'b-kontrola' in form.data:
            if self.object.otazka.vyhodnoceni == 0:
                if eval(form.cleaned_data.get("odpoved")) == eval(self.object.otazka.reseni):
                    LogTable.objects.create(tym=formular.tym, otazka=formular.otazka, soutez=formular.soutez, staryStav=formular.stav, novyStav=3)
                    messages.info(self.request, "Otázka byla vyřešena")
                    formular.stav = 3
                    formular.odpoved = form.cleaned_data.get("odpoved")
                    try:
                        team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.soutez)
                        team.penize += CENIK[self.object.otazka.obtiznost][1]
                        logger.info("Tým {} odevzdal otázku {}, kterou zodpověděl SPRÁVNĚ a získal {} DC.".format(self.request.user, formular.otazka, CENIK[self.object.otazka.obtiznost][1]))
                        formular.save()
                        team.save()
                    except Tym_Soutez.DoesNotExist as e:
                        logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
                        messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))
                else:
                    LogTable.objects.create(tym=formular.tym, otazka=formular.otazka, soutez=formular.soutez, staryStav=formular.stav, novyStav=7)
                    messages.info(self.request, "Otázka byla zodpovězena špatně")
                    formular.stav = 7
                    formular.odpoved = form.cleaned_data.get("odpoved")
                    logger.info("Tým {} odevzdal otázku {}, na kterou odpověděl CHYBNĚ.".format(self.request.user, formular.otazka))
                    formular.save()
            else:
                messages.info(self.request, "Otázka byla odeslána k hodnocení")
                LogTable.objects.create(tym=formular.tym, otazka=formular.otazka, soutez=formular.soutez, staryStav=formular.stav, novyStav=2)
                formular.stav = 2
                formular.odpoved = form.cleaned_data.get("odpoved")
                logger.info("Tým {} odevzdal otázku {} k ruční kontrole".format(self.request.user, formular.otazka))
                formular.save()
        elif 'b-bazar' in form.data:
            LogTable.objects.create(tym=formular.tym, otazka=formular.otazka, soutez=formular.soutez, staryStav=formular.stav, novyStav=5)
            messages.info(self.request, "Otázka byla prodána do bazaru")
            team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.soutez)
            formular.tym = None
            if formular.otazka.obtiznost != "A":
                formular.bazar = True
            formular.stav = 5
            formular.odpoved = ""
            team.penize += CENIK[self.object.otazka.obtiznost][2]
            logger.info("Tým {} prodal otázku {} do bazaru za {} DC.".format(self.request.user, formular.otazka, CENIK[self.object.otazka.obtiznost][1]))
            formular.save()
            team.save()
        elif 'b-podpora' in form.data:
            LogTable.objects.create(tym=formular.tym, otazka=formular.otazka, soutez=formular.soutez, staryStav=formular.stav, novyStav=4)
            formular.odpoved = form.cleaned_data.get("odpoved")
            formular.stav = 4
            formular.bylaPodpora = True
            try:
                konverzace = ChatConvos.objects.get(otazka=formular, tym=self.request.user)
                konverzace.uzavreno = False
            except Exception:
                konverzace = ChatConvos.objects.create(otazka=formular, tym=self.request.user, uzavreno=False)
            konverzace.sazka = form.cleaned_data.get('sazka')
            team = Tym_Soutez.objects.get(tym=self.object.tym, soutez=self.object.soutez)
            if konverzace.sazka > CENIK[self.object.otazka.obtiznost][0] * 2:
                konverzace.sazka = CENIK[self.object.otazka.obtiznost][0] * 2
                messages.warning(self.request, "Byla překročena maximální výše sázky")
            if team.penize >= konverzace.sazka:
                team.penize -= konverzace.sazka
                messages.info(self.request, f'Bylo vsazeno {konverzace.sazka} DC')
            else:
                konverzace.sazka = team.penize  #tym nema dost penez, vsadi se vsechno
                team.penize = 0
                messages.warning(self.request, "Nedostatečná výše aktiv týmu, bylo vsazeno {} DC".format(konverzace.sazka))
            logger.info("Tým {} odeslal otázku {} na technickou podporu.".format(self.request.user, formular.otazka))
            if konverzace.sazka > 0:
                logger.info("Tým {} vsadil {} DC na otázku {}.".format(self.request.user, konverzace.sazka, formular.otazka))
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
        tym_soutez = Tym_Soutez.objects.get(tym=request.user, soutez=Soutez.get_aktivni())
        
        if (tym_soutez.penize >= CENIK[obtiznost][0]) and not is_bazar:
            otazky = Tym_Soutez_Otazka.objects.filter(stav=0, soutez=Soutez.get_aktivni(), otazka__obtiznost=obtiznost).order_by("?")[:1]
            if len(otazky) == 0:
                messages.error(request, "došly otázky s obtížností {} :/".format(obtiznost))
                logger.error("Tým {} se pokusil koupit otázku s obtížností {}, které došly.".format(request.user, obtiznost))
                return redirect("herni_server")
            otazka = otazky[0]
            otazka.stav = 1
            tym_soutez.penize -= CENIK[obtiznost][0]
            otazka.tym=request.user
            LogTable.objects.create(tym=request.user, otazka=otazka.otazka, soutez=tym_soutez.soutez, staryStav=0, novyStav=1)
            logger.info("Tým {} zakoupil otázku {} s obtížností {} za {} DC.".format(request.user, otazka, obtiznost, CENIK[obtiznost][0]))
            otazka.save()
            tym_soutez.save()
        elif (tym_soutez.penize >= CENIK[obtiznost][2]) and is_bazar:
            otazky = Tym_Soutez_Otazka.objects.filter(stav=5, soutez=Soutez.get_aktivni(), otazka__obtiznost=obtiznost).order_by("?")[:1]
            if len(otazky) == 0:
                messages.error(request, "došly otázky s obtiznosti {} v bazaru :/".format(obtiznost))
                logger.error("Tým {} se pokusil koupit otázku s obtížností {} Z BAZARU, které došly.".format(request.user, obtiznost))
                return redirect("herni_server")
            otazka = otazky[0]
            otazka.stav = 6
            tym_soutez.penize -= CENIK[obtiznost][2]
            otazka.tym=request.user
            LogTable.objects.create(tym=request.user, otazka=otazka.otazka, soutez=tym_soutez.soutez, staryStav=5, novyStav=6)
            logger.info("Tým {} zakoupil otázku {} s obtížností {} za {} DC.".format(request.user, otazka, obtiznost, CENIK[obtiznost][0]))
            otazka.save()
            tym_soutez.save()
        return redirect("otazka-detail", otazka.pk)


class SoutezVysledkyJsAPI(TemplateView):
    template_name = "soutez/soutez_vysledek_jsapi.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            aktivni_soutez = Soutez.get_aktivni()
        except Soutez.DoesNotExist as e:
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
        context["aktivni_soutez"] = True if Soutez.get_aktivni() else False
        return context


class ConvoListJsAPI(ListView):
    template_name = "soutez/convo_list_jsapi.html"
    model = ChatConvos

    def get_queryset(self):
        if isinstance(self.request.user, Tym):
            return ChatConvos.objects.filter(Q(otazka__soutez=Soutez.get_aktivni())|Q(otazka=None), tym=self.request.user)
        elif self.request.user.has_perm('strela.podpora'):
            return ChatConvos.objects.filter(Q(otazka__soutez=Soutez.get_aktivni()) | Q(otazka=None))
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
                convo = ChatConvos.objects.get(id=convo_id, tym=self.request.user)
            except ChatConvos.DoesNotExist:
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
                convo = ChatConvos.objects.get(id=convo_id, tym=self.request.user)
            except ChatConvos.DoesNotExist:
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
        context["is_aktivni_soutez"] = True if Soutez.get_aktivni() != None else False
        return context

    @transaction.atomic
    def form_valid(self, form):
        try:
            konverzace = ChatConvos.objects.get(pk=self.request.session['id_konverzace'])
        except Exception:
            messages.error(self.request, "Konverzace nebyla nalezena")
            return HttpResponseRedirect(reverse_lazy('admin_index'))

        aktivni_soutez = Soutez.get_aktivni()

        try:
            team = Tym_Soutez.objects.get(tym=konverzace.tym, soutez=aktivni_soutez)
        except Tym_Soutez.DoesNotExist as e:
            logger.error("Nepodařilo se nalézt tým v soutěži {}".format(e))
            messages.error(self.request, "Nepodařilo se nalézt tým v soutěži {}".format(e))
            return HttpResponseRedirect(reverse_lazy('admin_index'))
        
        if konverzace.otazka != None:
            if 'chybnaotazka' in form.data:
                konverzace.otazka.otazka.stav = 2
                konverzace.otazka.otazka.save()
                if isinstance(konverzace.sazka, int):
                    team.penize += konverzace.sazka * 2
                    logger.info("Uživatel {} uznal týmu {} otázku {}. Otázka byla zadána špatně, týmvyhrál sázku {} DC"
                        .format(self.request.user,konverzace.tym, konverzace.otazka, konverzace.sazka * 2))
                
        if 'b-uznat' in form.data:
            if konverzace.otazka != None:
                konverzace.otazka.stav = 3
                konverzace.uzavreno = True
                konverzace.uznano = True
                
                team.penize += CENIK[konverzace.otazka.otazka.obtiznost][1]
                logger.info("Uživatel {} uznal týmu {} otázku {}. Otázka byla zodpovězena SPRÁVNĚ, týmu bylo přičteno {} DC"
                    .format(self.request.user,konverzace.tym, konverzace.otazka, CENIK[konverzace.otazka.otazka.obtiznost][1]))
                
                LogTable.objects.create(tym=konverzace.tym, otazka=konverzace.otazka.otazka, soutez=aktivni_soutez, staryStav=4, novyStav=3)
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
                    .format(self.request.user,konverzace.tym, konverzace.otazka))
                LogTable.objects.create(tym=konverzace.tym, otazka=konverzace.otazka.otazka, soutez=aktivni_soutez, staryStav=4, novyStav=7)
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
            convo = ChatConvos.objects.get(pk=id_konverzace)
            context['sazka_tymu'] = convo.sazka
            context['vyreseno'] = convo.uzavreno
            context['otazka'] = convo.otazka
            context['uznano'] = convo.uznano
        except Exception as e:
            messages.error(self.request, "Chyba {}".format(e))
            logger.error("Konverzace s id {} nenalezena".format(id_konverzace))
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
        context["aktivni_soutez"] = True if Soutez.get_aktivni() != None else False
        return context

    @transaction.atomic
    def form_valid(self, form):
        if 'b-kontaktovat' in form.data:
            try:
                konverzace = ChatConvos.objects.get(tym=self.request.user, otazka=None)
                konverzace.uzavreno = False
                konverzace.save()
            except ChatConvos.DoesNotExist:
                konverzace = ChatConvos.objects.create(tym=self.request.user, uzavreno=False)
            return HttpResponseRedirect(reverse_lazy('tym_chat', args=(konverzace.pk,)))
        return HttpResponseRedirect(reverse_lazy('tym_chat_list'))


class TymChat(LoginRequiredMixin, TemplateView):
    login_url = reverse_lazy('login_souteze')
    template_name = 'soutez/tym_chat.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        id_konverzace = self.kwargs['pk']
        context["aktivni_soutez"] = True if Soutez.get_aktivni() != None else False
        self.request.session['id_konverzace'] = id_konverzace
        self.request.session['chat_redirect_target'] = reverse_lazy('tym_chat', args=(id_konverzace,))
        try:
            convo = ChatConvos.objects.get(pk=id_konverzace, tym=self.request.user)
            context['sazka_tymu'] = convo.sazka
            context['vyreseno'] = convo.uzavreno
            context['otazka'] = convo.otazka
            context['uznano'] = convo.uznano
        except Exception as e:
            logger.error("Konverzace s id {} u týmu {} nenalezena".format(id_konverzace, self.request.user))
            messages.error(self.request, "Chyba: {}".format(e))
        return context