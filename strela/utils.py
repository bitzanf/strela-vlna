from django.core.cache import cache
from . models import Soutez, Skola
from django.utils.timezone import now
from django.contrib import messages
from django.utils.text import slugify
import re, sys

def eval_registration(self):
    context: dict[str, ] = {}
    reg = Soutez.objects.filter(rok=now().year)

    if reg.count() == 0:
        messages.info(self.request, "Registrace na letošní rok ještě nebyla založena")
    else:
        context["soutez"] = reg
        context["is_aktivni_soutez"] = any(r.aktivni for r in reg)
        for r in reg:
            if r.registrace:
                if r.is_soutez_full:
                    messages.warning(self.request, "Kapacita soutěže {0} již byla naplněna".format(r.nazev))
                else:
                    context["registrace"] = True        
    return context

def make_tym_login(jmeno: str) -> str:
    """vytvori login tymu na zaklade jmena a aktualniho roku"""
    return slugify(jmeno).replace("-", "") + str(now().year)

def ProgressBar(iteration: int, total: int, prefix: str = '', suffix: str = '', decimals: int = 2, barLength: int = 100):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : number of decimals in percent complete (Int) 
        barLength   - Optional  : character length of bar (Int) 
    """
    filledLength    = int(round(barLength * iteration / float(total)))
    percents        = round(100.00 * (iteration / float(total)), decimals)
    bar             = '#' * filledLength + '-' * (barLength - filledLength)
    sys.stdout.write('%s [%s] %s%s %s\r' % (prefix, bar, percents, '%', suffix)),
    sys.stdout.flush()
    if iteration == total:
        print(u"\n")

def tex_escape(text: str):
    """
        :param text: a plain text message
        :return: the message escaped to appear correctly in LaTeX
    """
    conv = {
        '&': r'\&',
        '%': r'\%',
        '\$': r'$',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
        'π': r'\pi',  # pozor dodelat, latex ted neumi znak pi
    }
    if text.find('$') == -1: 
        conv.update({ 
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
    })
    regex = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))))
    return regex.sub(lambda match: conv[match.group()], text)

def vokalizace_z_ze(skola: Skola) -> str:
    """
    vytvoří správně skloněný název školy s předložkou z/ze
    viz https://prirucka.ujc.cas.cz/?id=770
    """

    cache_key = f'sk_zze_{skola.pk}'
    obj = cache.get(cache_key)
    if obj:
        return obj
    
    souhlasky = 'hkrdtnzscrj'   # h ch k r d t n ž š č ř ď ť ň
    samohlasky = 'aeiyou'
    skola_split = slugify(skola.nazev).split('-')
    slovo = skola_split[0]
    z_ze = 'z'

    if len(slovo) < 2:
        z_ze = 'z'
    elif slovo[0] in samohlasky:
        z_ze = 'z'
    elif slovo[0] in 'zs':
        z_ze = 'ze'
    elif slovo[0] in souhlasky and slovo[1] in samohlasky:
        z_ze = 'z'
    elif slovo[0] in souhlasky and slovo[1] in souhlasky:
        if skola.nazev[:2] in ('tř', 'dř', 'sl', 'zr', 'zl'):
            z_ze = 'ze'
        else:
            z_ze = 'z'
    elif slovo[0] in souhlasky and slovo[1] in souhlasky and slovo[2] in souhlasky:
        z_ze = 'ze'
    
    skola_out:list[str] = []
    skola_words = skola.nazev.split()
    for i in range(len(skola_words)):
        ii = skola_words[i]
        iis = slugify(ii)
        if iis == 'skola':
            if ii[0].islower():
                skola_out.append('školy')
            else:
                skola_out.append('Školy')
        elif iis == 'gymnazium':
            for j in range(i - 1, -1, -1):
                if skola_out[j].endswith(('ní', 'ni')):
                    skola_out[j] += 'ho'
                else:
                    break
            if ii[0].islower():
                skola_out.append('gymnázia')
            else:
                skola_out.append('Gymnázia')
        else:
            skola_out.append(ii)

    out = z_ze + ' ' + ' '.join(skola_out)
    cache.set(cache_key, out)
    return out