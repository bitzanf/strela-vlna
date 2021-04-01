from optparse import make_option

from django.core.management.base import BaseCommand
from django.db import transaction

from strela.models import Otazka
from strela.utils  import ProgressBar

import logging
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    args = ''
    help =  'Kontroluje duplicitu zadání s odstraněním mezer uvnitř zadání.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help='Nic nedělat, jen ukázat, co by bylo uděláno')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        otazky = Otazka.objects.all()
        pocet_otazek = otazky.count()
        jednotlive = Otazka.objects.all()
        r = 0
        rv = []
        s = []
        for o in otazky:
            r += 1
            ProgressBar(r, pocet_otazek, prefix = 'Zkontrolováno otázek: ', barLength = 50) 
            for j in jednotlive:
                if (o.zadani.replace(" ", "") == j.zadani.replace(" ", "")) and j.pk != o.pk and (o.pk,j.pk) not in s:
                    s.append((j.pk,o.pk))
                    rv.append("Shoda zadání {}-{} s {}-{}".format(o.typ,o.pk,j.typ,j.pk))

        
        for i in rv:
            print(i) 
 
