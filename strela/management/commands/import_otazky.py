from optparse import make_option

from django.core.management.base import BaseCommand
from django.db import transaction

from strela.models import Otazka
from strela.utils  import ProgressBar

import re

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
        parser.add_argument('--progressbar',
            action='store_true',
            dest='progressbar',
            default=False,
            help='Ukázat progressbar')
        parser.add_argument('-f',
            dest='file',
            help='Importní soubor')    
        parser.add_argument('-t',
            dest='typotazky',
            help='Typ Otázky')     


    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        progressbar = options['progressbar']        
        file = options['file']
        typotazky = options['typotazky']
        fileobj:list[str] = []
        vstup = open(file, "r")
        for radek in vstup.readlines():
            fileobj.append(radek.strip())
        vstup.close()
        imp = 0
        r = 0
        count = 0
        reseni = ""
        v = 0
        for line in fileobj:
            if progressbar:
                r +=1
                ProgressBar(r, len(fileobj), prefix = 'importováno řádků: ', barLength = 50) 
            count += 1
            if count == 1:
                zadani = line 
            if count == 2:
                obtiznost = chr(64+int(line))
            if count > 2 and line != "":
                if reseni == "":
                    reseni = line
                else:    
                    reseni += "; {}".format(line)
                v += 1 
            if line == "":
                if v > 1:
                    vyhodnoceni = 1 
                else:
                    if re.match('^[\\d\\+\\-\\*/,. ]+$', reseni.strip()):
                        vyhodnoceni = 0
                        reseni = reseni.strip().replace(' ', '').replace(',', '.')
                    else:
                        vyhodnoceni = 1
                if Otazka.objects.filter(zadani=zadani).exists():
                    if dry_run:
                        print("zadani: {} obtiznost: {} reseni: {} vyhodnoceni: {} " .format(zadani,obtiznost,reseni,vyhodnoceni))
                        print("Otázka je duplicitní !!\n")
                        count = 0
                        reseni = ""
                        v = 0
                else:    
                    Otazka.objects.create(typ=typotazky, stav=0, vyhodnoceni=vyhodnoceni, obtiznost=obtiznost, zadani=zadani.strip().replace('___\\n___', '\n'), reseni=reseni.strip().replace('___\\n___', '\n'))
                    count = 0
                    reseni = ""
                    v = 0
                    imp += 1
        if v >1:
            vyhodnoceni = 1
        else: 
            vyhodnoceni = 0     
        if Otazka.objects.filter(zadani=zadani).exists():
            if dry_run:       
                print("zadani: {} obtiznost: {} reseni: {} vyhodnoceni: {}" .format(zadani,obtiznost,reseni,vyhodnoceni))    
                print("Otázka je duplicitní !!\n")
        else:    
            Otazka.objects.create(typ=typotazky, stav=0, vyhodnoceni=vyhodnoceni, obtiznost=obtiznost, zadani=zadani.strip(), reseni=reseni.strip() )
            imp += 1
        print("Zpracováno {} řádků, naimportováno {} zadání".format(len(fileobj), imp))


    