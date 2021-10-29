from optparse import make_option

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tex.core import compile_template_to_pdf

from strela.models import Soutez, Tym_Soutez_Otazka, CENIK
from strela.utils  import ProgressBar, tex_escape

import logging
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    args = ''
    help =  'Naimportuje příklady z roku 2020'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Nic nedělat, jen ukázat, co by bylo uděláno')
        parser.add_argument('-s',
            dest='soutez_id',
            help='ID soutěže')        

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        id_soutez = options['soutez_id']
        template_name = 'admin/zadani.tex'
        try:
            soutez = Soutez.objects.get(id=id_soutez)
            otazky = Tym_Soutez_Otazka.objects.filter(soutez=soutez)
            pom = []
            r = 0
            pocet_otazek = otazky.count()
            for o in otazky:
                r += 1
                ProgressBar(r, pocet_otazek, prefix = 'generuji LaTeX ', barLength = 50) 
                pom.append({'cislo': o.cisloVSoutezi,
                    'zadani': tex_escape(o.otazka.zadani), 
                    'typ': o.otazka.typ,
                    'obtiznost': o.otazka.obtiznost,
                    'cenik':CENIK[o.otazka.obtiznost]
                    })
            # seřadí otázky podle obtížnosti sestupně a v rámci obtížnosti podle délky,
            # aby se k sobě dostaly otázky s podobnou délkou a PDF vypadalo lépe.    
            pom.sort(key=lambda t: (t['obtiznost'],len(t['zadani'])), reverse=True)
            f = open("zadani-{}.pdf".format(id_soutez),"wb")
            print("generuji PDF")
            f.write(compile_template_to_pdf(template_name, {'otazky': pom }))
            f.close()
        except Exception as e:
            print(e)
