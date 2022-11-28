from django.core import mail
from django.core.cache import cache
from . models import KeyValueStore, Soutez, Skola
from django.utils.timezone import now
from django.contrib import messages
from django.utils.text import slugify
import re, sys, threading, logging
from . constants import CZ_NUTS_NAMES

logger = logging.getLogger(__name__)

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

def vokalizace_z_ze(skola: Skola, kratky_nazev:bool = True) -> str:
    """
    vytvoří správně skloněný název školy s předložkou z/ze
    viz https://prirucka.ujc.cas.cz/?id=770
    """

    cache_key_suffix = 'k' if kratky_nazev else 'd'
    cache_key = f'sk_zze_{skola.pk}_{cache_key_suffix}'
    obj = cache.get(cache_key)
    if obj:
        return obj
    
    souhlasky = 'hkrdtnzscrj'   # h ch k r d t n ž š č ř ď ť ň
    samohlasky = 'aeiyou'
    skola_str = skola.kratky_nazev if kratky_nazev else skola.nazev
    skola_split = slugify(skola_str).split('-')
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
        if skola.nazev[:2].lower() in ('tř', 'dř', 'sl', 'zr', 'zl'):
            z_ze = 'ze'
        else:
            z_ze = 'z'
    elif slovo[0] in souhlasky and slovo[1] in souhlasky and slovo[2] in souhlasky:
        z_ze = 'ze'
    
    skola_out:list[str] = []
    skola_words = skola_str.split()
    for i in range(len(skola_words)):
        ii = skola_words[i]
        iis = slugify(ii)
        if iis == 'skola':
            for j in range(i - 1, -1, -1):
                if skola_out[j].endswith(('á', 'a')) and len(skola_out[j]) > 2:
                    skola_out[j] = skola_out[j][:-1] + 'é'
                else:
                    break
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

def auto_kontrola_odpovedi(odpoved:str, reseni:str, odchylka:float=0.05) -> bool:
    rx = re.compile(r'^[\d\+\-\*/,.\(\)]+$')
    if rx.match(odpoved) and rx.match(reseni):
        try:
            nReseni = eval(reseni.replace(',', '.'))
            nOdpoved = eval(odpoved.replace(',', '.'))
            return abs(nReseni - nOdpoved) < abs(nReseni * odchylka)
        except Exception:
            return False
    else:
        return odpoved == reseni

def get_nuts_kraje() -> "list[tuple[str, str]]":
    rx = re.compile(r'^CZ0..0$')
    out = []
    for nuts, nazev in CZ_NUTS_NAMES.items():
        if rx.match(nuts):
            out.append((nuts, nazev))
    return out

def get_okres_for_kraj(kraj:str) -> "list[tuple[str, str]]":
    rx = re.compile(kraj[:5] + r'[^0]')
    out = []
    for nuts, nazev in CZ_NUTS_NAMES.items():
        if rx.match(nuts):
            out.append((nuts, nazev))
    return out

class BulkMailSender():
    @classmethod
    def add_emails(cls, mails:"set[str]", vip:bool):
        if cache.get('mail_q_appending'):
            raise Exception('Nelze přidávat maily do fronty, do které se zrovna přidává!')
        
        cache.set('mail_q_appending', True)
        top = cache.get('mail_q_top', 0)

        for mail in mails:
            cache.set(f'mail_q_mail_{top}', (mail, vip))
            top += 1
            cache.set('mail_q_top', top)
        
        cache.set('mail_q_appending', False)

    @classmethod
    def send_mails(cls, count:int = -1):
        if cache.get('mail_q_sending'):
            raise Exception('Nelze rozesílat další maily doukud se neposlaly předchozí!')

        cache.set('mail_q_sending', True)
        t = threading.Thread(target=cls._sender, args=(count, 100))
        t.setDaemon(True)
        t.start()

    @classmethod
    def _sender(cls, count, count_per_session):
        n_mails = cache.get('mail_q_top', 0) - cache.get('mail_q_bottom', 0)
        logger.info(f'Rozesílání {n_mails} pozvánek.')
        vip_text = KeyValueStore.objects.get(key='pozvanka_vip').val
        pleb_text = KeyValueStore.objects.get(key='pozvanka').val
        vip_subject = cache.get('mail_q_subject_vip', 'VIP Pozvánka')
        pleb_subject = cache.get('mail_q_subject', 'Pozvánka')
        connection = mail.get_connection()

        connection.open()
        n_sent = 0
        n_sent_this_session = 0
        error_count = 0
        while cache.get('mail_q_sending', False) and ((n_sent < count) if count >= 0 else True):
            read_end = cache.get('mail_q_bottom', 0)
            write_end = cache.get('mail_q_top', 0)
            if read_end == write_end:
                cache.set('mail_q_bottom', 0)
                cache.set('mail_q_top', 0)
                cache.set('mail_q_sending', False)
                break
            
            address, vip = cache.get(f'mail_q_mail_{read_end}', (None, None))
            if address:
                try:
                    msg = mail.EmailMessage(
                        connection = connection,
                        to = (address,)
                    )
                    msg.content_subtype = 'html'
                    if vip:
                        msg.body = vip_text
                        msg.subject = vip_subject
                    else:
                        msg.body = pleb_text
                        msg.subject = pleb_subject
                    
                    msg.send()
                    error_count = 0
                    cache.set('mail_q_last_succesful', read_end)
                    cache.delete(f'mail_q_mail_{read_end}')
                except Exception as e:
                    logger.error(f'Chyba při rezesílání pozvánek: {e}')
                    error_count += 1
                    if error_count > 8:
                        logger.error(f'Príliš mnoho chyb při odesílání mailů! (odesláno {n_sent} mailů)')
                        cache.set('mail_q_bottom', cache.get('mail_q_last_succesful', 0) + 1)
                        break

                n_sent += 1
                n_sent_this_session += 1

                if n_sent_this_session > count_per_session and count_per_session > 0:
                    connection.close()
                    connection.open()
                    n_sent_this_session = 0
                    logger.info(f'Restart spojení, celkem odesláno {n_sent}')
            
            cache.set('mail_q_bottom', read_end + 1)

        connection.close()
        logger.info(f'Rozesílání pozvánek dokončeno (odesláno {n_sent} mailů).')
        cache.set('mail_q_sending', False)