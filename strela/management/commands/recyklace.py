from django.core.management.base import BaseCommand

from strela.models import Soutez, Tym_Soutez_Otazka

class Command(BaseCommand):
    args = ''
    help = 'Recykluje otázky z již proběhlých soutěží v případě nouze.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-d',
            required=True,
            dest='obtiznosti',
            help='Obtížnost příkladů (např. "BCE")'
        )
        parser.add_argument(
            '-n',
            required=True,
            dest='pocet',
            help='Počet příkladů v daných obtížnostech'
        )
        parser.add_argument(
            '-s',
            required=True,
            dest='soutez_id',
            help='ID Soutěže'
        )

    def handle(self, *args, **options):
        obtiznosti:str = options['obtiznosti']
        pocet = int(options['pocet'])
        soutez = Soutez.objects.get(id=int(options['soutez_id']))
        print(f'\t{soutez.pretty_name(True)}')

        for o in obtiznosti.upper():
            try:
                otazky = Tym_Soutez_Otazka.objects.filter(otazka__soutez=soutez, otazka__otazka__obtiznost=o).order_by('?')[:pocet]
                print(f'Recyklace {otazky.count()} otázek obtížnosti {o}')
                otazky.delete()
            except Exception as e:
                print(f'Chyba při recyklaci otázek! {e}')