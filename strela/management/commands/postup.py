from django.core.management.base import BaseCommand
from sequences import get_next_value

from strela.models import Soutez, Tym_Soutez
from strela.constants import TYM_DEFAULT_MONEY

class Command(BaseCommand):
    args = ''
    help = 'Posup nejlepších týmů do dalšího kola soutěže.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from',
            required=True,
            dest='from',
            help='ID Soutěže, ze které týmy postupují',
            type=int
        )
        parser.add_argument(
            '--to',
            required=True,
            dest='to',
            help='ID Soutěže, do které týmy postupují',
            type=int
        )
        parser.add_argument(
            '-n',
            required=True,
            dest='pocet',
            help='Počet týmů, které postupují',
            type=int
        )

    def handle(self, *args, **options):
        z  = Soutez.objects.get(id=options['from'])
        do = Soutez.objects.get(id=options['to'])
        pocet = options['pocet']

        if do.prezencni != 'P':
            print('Postup do online soutěže není dovolen!')
            return

        if options['from'] == options['to']:
            print('Z a DO nemohou být tatáž soutěž!')
            return

        prihlaseno = Tym_Soutez.objects.filter(soutez=do).count()
        pocet -= prihlaseno
        print(f'Do soutěže {do} je již přihlášeno {prihlaseno} týmů')

        tymy = Tym_Soutez.objects.filter(soutez=z).order_by('-penize')[:pocet]
        print(f'Postup {tymy.count()} týmů z {z} do {do}')

        for tym in tymy:
            Tym_Soutez.objects.create(tym=tym.tym, soutez=do, cislo=get_next_value(f'ts_{do.pk}'), penize=TYM_DEFAULT_MONEY)
