from . models import Tym, Soutez, Skola, Tym_Soutez
from django.utils.timezone import now
from django.contrib import messages
import re

def eval_registration(self):
    context = {}
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

import sys

def ProgressBar (iteration, total, prefix = '', suffix = '', decimals = 2,
    barLength = 100):
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

def tex_escape(text):
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