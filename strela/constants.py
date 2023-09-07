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
    (0, "Nová"),    # od V2 nevyuzito
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

TYM_DEFAULT_MONEY = 40

# "Nomenclature of territorial units for statistics"
# jednotný hiearchický evropský systém na určení oblasti ve státě
# popis formátu pro ČR:
#   CZ0 <REGION> <KRAJ> <OKRES>
CZ_NUTS_NAMES = {
    'CZ0100': 'Hlavní město Praha',
    'CZ0101': 'Praha 1',
    'CZ0102': 'Praha 2',
    'CZ0103': 'Praha 3',
    'CZ0104': 'Praha 4',
    'CZ0105': 'Praha 5',
    'CZ0106': 'Praha 6',
    'CZ0107': 'Praha 7',
    'CZ0108': 'Praha 8',
    'CZ0109': 'Praha 9',
    'CZ010A': 'Praha 10',
    'CZ0200': 'Středočeský kraj',
    'CZ0201': 'Benešov',
    'CZ0202': 'Beroun',
    'CZ0203': 'Kladno',
    'CZ0204': 'Kolín',
    'CZ0205': 'Kutná Hora',
    'CZ0206': 'Mělník',
    'CZ0207': 'Mladá Boleslav',
    'CZ0208': 'Nymburk',
    'CZ0209': 'Praha-východ',
    'CZ020A': 'Praha-západ',
    'CZ020B': 'Příbram',
    'CZ020C': 'Rakovník',
    #'CZ0300': 'Jihozápad',
    'CZ0310': 'Jihočeský kraj',
    'CZ0311': 'České Budějovice',
    'CZ0312': 'Český Krumlov',
    'CZ0313': 'Jindřichův Hradec',
    'CZ0314': 'Písek',
    'CZ0315': 'Prachatice',
    'CZ0316': 'Strakonice',
    'CZ0317': 'Tábor',
    'CZ0320': 'Plzeňský kraj',
    'CZ0321': 'Domažlice',
    'CZ0322': 'Klatovy',
    'CZ0323': 'Plzeň-město',
    'CZ0324': 'Plzeň-jih',
    'CZ0325': 'Plzeň-sever',
    'CZ0326': 'Rokycany',
    'CZ0327': 'Tachov',
    #'CZ0400': 'Severozápad',
    'CZ0410': 'Karlovarský kraj',
    'CZ0411': 'Cheb',
    'CZ0412': 'Karlovy Vary',
    'CZ0413': 'Sokolov',
    'CZ0420': 'Ústecký kraj',
    'CZ0421': 'Děčín',
    'CZ0422': 'Chomutov',
    'CZ0423': 'Litoměřice',
    'CZ0424': 'Louny',
    'CZ0425': 'Most',
    'CZ0426': 'Teplice',
    'CZ0427': 'Ústí nad Labem',
    #'CZ0500': 'Severovýchod',
    'CZ0510': 'Liberecký kraj',
    'CZ0511': 'Česká Lípa',
    'CZ0512': 'Jablonec nad Nisou',
    'CZ0513': 'Liberec',
    'CZ0514': 'Semily',
    'CZ0520': 'Královéhradecký kraj',
    'CZ0521': 'Hradec Králové',
    'CZ0522': 'Jičín',
    'CZ0523': 'Náchod',
    'CZ0524': 'Rychnov nad Kněžnou',
    'CZ0525': 'Trutnov',
    'CZ0530': 'Pardubický kraj',
    'CZ0531': 'Chrudim',
    'CZ0532': 'Pardubice',
    'CZ0533': 'Svitavy',
    'CZ0534': 'Ústí nad Orlicí',
    #'CZ0600': 'Jihovýchod',
    'CZ0630': 'Kraj Vysočina',
    'CZ0631': 'Havlíčkův Brod',
    'CZ0632': 'Jihlava',
    'CZ0633': 'Pelhřimov',
    'CZ0634': 'Třebíč',
    'CZ0635': 'Žďár nad Sázavou',
    'CZ0640': 'Jihomoravský kraj',
    'CZ0641': 'Blansko',
    'CZ0642': 'Brno-město',
    'CZ0643': 'Brno-venkov',
    'CZ0644': 'Břeclav',
    'CZ0645': 'Hodonín',
    'CZ0646': 'Vyškov',
    'CZ0647': 'Znojmo',
    #'CZ0700': 'Střední Morava',
    'CZ0710': 'Olomoucký kraj',
    'CZ0711': 'Jeseník',
    'CZ0712': 'Olomouc',
    'CZ0713': 'Prostějov',
    'CZ0714': 'Přerov',
    'CZ0715': 'Šumperk',
    'CZ0720': 'Zlínský kraj',
    'CZ0721': 'Kroměříž',
    'CZ0722': 'Uherské Hradiště',
    'CZ0723': 'Vsetín',
    'CZ0724': 'Zlín',
    'CZ0800': 'Moravskoslezský kraj',
    'CZ0801': 'Bruntál',
    'CZ0802': 'Frýdek-Místek',
    'CZ0803': 'Karviná',
    'CZ0804': 'Nový Jičín',
    'CZ0805': 'Opava',
    'CZ0806': 'Ostrava-město'
}