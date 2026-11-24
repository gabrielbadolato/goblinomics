"""Addon pessoal do jogo: o arquivo de dados (site/addon/Dados.lua) e o zip para instalar.

O jogo não acessa a internet. Um .bat no Windows baixa o Dados.lua do site para a pasta do addon,
e o jogo o lê ao entrar com o personagem ou com /reload. Vai só a casa padrão, com as mesmas contas
simples do bot (consulta.py), para os números baterem com os do site.
"""
import os
import zipfile
from datetime import datetime

from . import consulta
from .config import RAIZ

FONTES = RAIZ / "addon" / "Goblinomics"
# Arquivos que o Windows lê: precisam de fim de linha CRLF.
DO_WINDOWS = (".bat", ".vbs", ".txt")
NO_SITE = ("Goblinomics.lua", "Goblinomics.toc")


def linhas(dados):
    """Uma linha Lua por item com preço ou média: m menor preço, h média de 7 dias, d vendas por
    dia, q quantidade à venda, c custo e l lucro da receita que mais rende. Tudo em cobre."""
    saida = []
    for item_id in sorted(set(dados.precos) | set(dados.habituais)):
        p = dados.preco(item_id)
        campos = []
        if p["min"] is not None:
            campos.append(f"m={round(p['min'])}")
        if p["habitual"] is not None:
            campos.append(f"h={round(p['habitual'])}")
        if p["por_dia"]:
            campos.append(f"d={round(p['por_dia'], 1)}")
        if p["qtd"]:
            campos.append(f"q={p['qtd']}")
        feitas = [f for f in dados.fabricar(item_id) if f["custo"] is not None]
        if feitas:
            # Por unidade fabricada, para comparar com o preço da unidade na mesma dica.
            melhor = max(feitas, key=lambda f: f["lucro"] if f["lucro"] is not None else -f["custo"])
            campos.append(f"c={round(melhor['custo'] / melhor['feitos'])}")
            if melhor["lucro"] is not None:
                campos.append(f"l={round(melhor['lucro'] / melhor['feitos'])}")
        if campos:
            saida.append(f"[{item_id}]={{{','.join(campos)}}},")
    return saida


def lua(dados):
    coletado = int(datetime.fromisoformat(dados.coletado_em.replace("Z", "+00:00")).timestamp())
    itens = linhas(dados)
    casa = f"{dados.casa['nome']} {dados.casa['id']}".replace("\\", "").replace('"', "")
    return "\n".join([
        "-- Gerado pelo Goblinomics a cada coleta. Não edite: o atualizar.bat sobrescreve.",
        "GoblinomicsDados = {",
        f"coletado={coletado},",
        f'casa="{casa}",',
        f"n={len(itens)},",
        "itens={",
        *itens,
        "},",
        "}",
        "",
    ])


def _trocar(caminho, conteudo):
    temporario = caminho.with_suffix(".tmp")
    temporario.write_bytes(conteudo)
    os.replace(temporario, caminho)


def gerar(cfg):
    """Grava <pasta_site>/addon/Dados.lua e Goblinomics.zip (addon pronto, com os dados de agora)."""
    dados = consulta.Dados(cfg.pasta_site / "dados", cfg.casa_padrao)
    dados.atualizar()
    destino = cfg.pasta_site / "addon"
    destino.mkdir(parents=True, exist_ok=True)
    texto = lua(dados).encode()
    _trocar(destino / "Dados.lua", texto)
    # O código do addon também vai ao site: o atualizar.bat o baixa, e um ajuste chega sem reinstalar.
    # Só o Lua e o .toc, que rodam presos dentro do jogo; os scripts do Windows não se atualizam sozinhos.
    for nome in NO_SITE:
        if (FONTES / nome).exists():
            _trocar(destino / nome, (FONTES / nome).read_bytes())
    if FONTES.is_dir():
        temporario = destino / "Goblinomics.tmp"
        with zipfile.ZipFile(temporario, "w", zipfile.ZIP_DEFLATED) as z:
            for fonte in sorted(FONTES.iterdir()):
                conteudo = fonte.read_bytes()
                if fonte.suffix in DO_WINDOWS:
                    conteudo = conteudo.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                z.writestr(f"Goblinomics/{fonte.name}", conteudo)
            z.writestr("Goblinomics/Dados.lua", texto)
        os.replace(temporario, destino / "Goblinomics.zip")
    print(f"addon: {dados.casa['nome']}, {texto.count(b'\n') - 8} itens")
