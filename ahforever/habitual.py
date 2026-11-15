"""Preço habitual de cada item, e o que conta como anúncio absurdo.

A referência é o histórico do próprio item (o menor preço de cada foto dos últimos dias), não os
outros anúncios do momento: neste mercado a maioria dos anúncios costuma ser cara, e o preço de
verdade está na ponta barata. Um ensaio de 15/11/2026 mostrou que comparar com a mediana dos
anúncios do momento jogaria fora justamente os preços certos (Crawler Claw: 15c de menor preço,
17c de histórico, 15s de mediana dos anúncios).
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

from .compactar import DIAS_POR_HORA, SERIE

# Tantas vezes acima ou abaixo do habitual, o preço fica fora das contas.
VEZES = 5
# O habitual só vale com um mínimo de fotos; antes disso um item novo pareceria sempre fora do normal.
FOTOS_MINIMAS = 6
FORMATO = "%Y-%m-%dT%H:%M:%SZ"


def precos(con, ruleset_id, casa_id, agora):
    """{item: cobre}: média do menor preço de cada foto dos últimos dias, sem as fotos absurdas.

    Fotos em que o menor preço ficou a mais de VEZES da mediana do período não entram na média:
    são o anúncio único a preço de brincadeira, ou o engano de quem anunciou barato demais.
    """
    desde = (agora - timedelta(days=DIAS_POR_HORA)).strftime(FORMATO)
    series = defaultdict(list)
    for _, item_id, minimo, _ in con.execute(SERIE, (ruleset_id, casa_id, desde, "9999")):
        if minimo is not None:
            series[item_id].append(minimo)
    habituais = {}
    for item_id, minimos in series.items():
        if len(minimos) < FOTOS_MINIMAS:
            continue
        centro = median(minimos)
        normais = [m for m in minimos if centro <= m * VEZES and m <= centro * VEZES]
        habituais[item_id] = int(sum(normais) / len(normais))
    return habituais


def absurdo(preco, habitual):
    """O preço está muito acima do que o item costuma custar. Sem histórico, não dá para dizer."""
    return bool(habitual) and preco > VEZES * habitual
