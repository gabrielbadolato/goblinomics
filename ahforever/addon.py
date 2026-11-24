"""Addon pessoal do jogo: o arquivo de dados (site/addon/Dados.lua) e o zip para instalar.

O jogo não acessa a internet. Um .bat no Windows baixa o Dados.lua do site para a pasta do addon,
e o jogo o lê ao entrar com o personagem ou com /reload. Vai só a casa padrão, com as mesmas contas
simples do bot (consulta.py), para os números baterem com os do site.
"""
import json
import os
import zipfile
from datetime import datetime

from . import consulta
from .config import RAIZ

FONTES = RAIZ / "addon" / "Goblinomics"
# Arquivos que o Windows lê: precisam de fim de linha CRLF.
DO_WINDOWS = (".bat", ".vbs", ".txt")
# O que o atualizar.bat baixa do site, e o texto que cada arquivo certo contém ("-" = não confere, é imagem).
# Código novo do addon entra aqui; o .bat só aceita .lua, .toc e .tga.
ARQUIVOS = (("Dados.lua", "GoblinomicsDados"), ("Goblinomics.lua", "SLASH_GOBLINOMICS1"),
            ("Goblinomics.toc", "Interface"), ("Icone.tga", "-"))
# O atualizar.bat também fica no site para ser baixado à mão com curl (arquivo baixado assim não fica
# bloqueado pelo Windows, ao contrário do que sai de um zip); ele não se atualiza sozinho.
NO_SITE = tuple(nome for nome, _ in ARQUIVOS if nome != "Dados.lua") + ("atualizar.bat",)


MAX_NOMES = 4      # quem faz, vendedores, monstros e mapas por linha da dica
QUEDA_MUNDIAL = 20   # acima disto são tantos monstros que só o total interessa


def _texto(valor):
    """Texto entre aspas para o Lua."""
    return '"' + str(valor).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _lista(nomes, limite=MAX_NOMES):
    nomes = list(nomes)
    return ", ".join(nomes[:limite]) + (f" +{len(nomes) - limite}" if len(nomes) > limite else "")


def onde_conseguir(o, origens, faccao):
    """A origem de um item de receita numa frase curta; os vendedores da facção da casa primeiro."""
    def npc(i, nivel=False):
        nome, zona, lado, minimo, maximo = origens["npcs"][str(i)]
        extras = []
        if nivel and minimo:
            extras.append(f"nv {minimo}" + (f"-{maximo}" if maximo and maximo != minimo else ""))
        if zona is not None and str(zona) in origens["zonas"]:
            extras.append(origens["zonas"][str(zona)][0])
        if lado in ("A", "H") and lado != faccao:
            extras.append("Aliança" if lado == "A" else "Horda")
        return nome + (f" ({', '.join(extras)})" if extras else "")

    partes = []
    if o.get("v"):
        ordem = sorted(o["v"], key=lambda i: {faccao: 0, "AH": 1, "": 1}.get(origens["npcs"][str(i)][2], 2))
        partes.append("vendido por " + _lista(npc(i) for i in ordem))
    if o.get("d"):
        if o.get("dn", 0) > QUEDA_MUNDIAL:
            partes.append(f"queda mundial ({o['dn']} monstros)")
        else:
            partes.append("cai de " + _lista((npc(i, True) for i in o["d"]), 3))
    if o.get("o"):
        partes.append("em " + _lista((nome for nome, _ in o["o"]), 2))
    if o.get("i"):
        partes.append("dentro de " + _lista(o["i"], 2))
    if o.get("q"):
        partes.append(f"recompensa de {o['q']} missão" if o["q"] == 1 else f"recompensa de {o['q']} missões")
    return "; ".join(partes)


def linhas(dados, origens=None, zonas=None):
    """Uma linha Lua por item. Preços em cobre: m menor preço, h média de 7 dias, d vendas por dia,
    q quantidade à venda, c custo e l lucro da receita que mais rende (por unidade), n quanto o NPC paga
    quando isso supera o leilão sem a taxa. Textos: g quem da guilda faz, o onde conseguir (item de
    receita), z mapas onde se coleta (menos os da tabela feita à mão). Números: r item que ensina a receita, u em quantas receitas o
    material entra e ul em quantas delas com lucro agora."""
    origens, zonas = origens or {}, zonas or {}
    faccao = "H" if "horde" in dados.casa["nome"].lower() else "A" if "alliance" in dados.casa["nome"].lower() else ""
    receitas = getattr(dados, "receitas", {})
    fabricados = {item_id: dados.fabricar(item_id) for item_id in receitas}
    usado, com_lucro = {}, {}
    for item_id, lista in receitas.items():
        lucra = any((f["lucro"] or 0) > 0 for f in fabricados[item_id])
        for material in {m for *_, reagentes in lista for m, _ in reagentes}:
            usado[material] = usado.get(material, 0) + 1
            com_lucro[material] = com_lucro.get(material, 0) + lucra
    ensina = getattr(dados, "ensina", {})
    saida = []
    for item_id in sorted(set(dados.precos) | set(dados.habituais) | set(receitas) | set(usado)
                          | {int(i) for i in origens.get("itens", {})}):
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
        if p["min"] is not None and p.get("npc_paga") and p["npc_paga"] > p["min"] * (1 - consulta.TAXA):
            campos.append(f"n={p['npc_paga']}")
        feitas = [f for f in fabricados.get(item_id, ()) if f["custo"] is not None]
        if feitas:
            # Por unidade fabricada, para comparar com o preço da unidade na mesma dica.
            melhor = max(feitas, key=lambda f: f["lucro"] if f["lucro"] is not None else -f["custo"])
            campos.append(f"c={round(melhor['custo'] / melhor['feitos'])}")
            if melhor["lucro"] is not None:
                campos.append(f"l={round(melhor['lucro'] / melhor['feitos'])}")
        quem = sorted({nome for f in fabricados.get(item_id, ()) for nome in f.get("quem", ())})
        if quem:
            campos.append("g=" + _texto(_lista(quem)))
        if ensina.get(item_id):
            campos.append(f"r={ensina[item_id][0][0]}")
        origem = origens.get("itens", {}).get(str(item_id))
        if origem:
            campos.append("o=" + _texto(onde_conseguir(origem, origens, faccao)))
        if item_id in usado:
            campos.append(f"u={usado[item_id]}")
            if com_lucro[item_id]:
                campos.append(f"ul={com_lucro[item_id]}")
        mapas = zonas.get("materiais", {}).get(str(item_id))
        # Só os mapas que vêm da QuestieDB ou da guilda: a tabela feita à mão (couros, por faixa de nível)
        # precisa do aviso que o site dá, e na dica do jogo não cabe.
        if mapas and mapas.get("origem") != "classic":
            campos.append("z=" + _texto(_lista(zonas["zonas"][k]["en"] for k in mapas["zonas"])))
        if campos:
            saida.append(f"[{item_id}]={{{','.join(campos)}}},")
    return saida


def lua(dados, origens=None, zonas=None):
    coletado = int(datetime.fromisoformat(dados.coletado_em.replace("Z", "+00:00")).timestamp())
    itens = linhas(dados, origens, zonas)
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


def _para_windows(fonte):
    """O conteúdo do arquivo, com fim de linha CRLF nos que o Windows executa ou abre no Bloco de Notas."""
    conteudo = fonte.read_bytes()
    if fonte.suffix in DO_WINDOWS:
        conteudo = conteudo.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return conteudo


def gerar(cfg):
    """Grava <pasta_site>/addon/Dados.lua e Goblinomics.zip (addon pronto, com os dados de agora)."""
    dados = consulta.Dados(cfg.pasta_site / "dados", cfg.casa_padrao)
    dados.atualizar()
    destino = cfg.pasta_site / "addon"
    destino.mkdir(parents=True, exist_ok=True)
    extras = [json.loads(arquivo.read_text()) if arquivo.exists() else None
              for arquivo in (cfg.pasta_site / "origens.json", cfg.pasta_site / "zonas.json")]
    texto = lua(dados, *extras).encode()
    _trocar(destino / "Dados.lua", texto)
    # O código do addon também vai ao site: o atualizar.bat baixa o que a lista manda, e um ajuste
    # chega sem reinstalar.
    for nome in NO_SITE:
        if (FONTES / nome).exists():
            _trocar(destino / nome, _para_windows(FONTES / nome))
    _trocar(destino / "arquivos.txt", "".join(f"{nome} {marca}\r\n" for nome, marca in ARQUIVOS).encode())
    if FONTES.is_dir():
        temporario = destino / "Goblinomics.tmp"
        with zipfile.ZipFile(temporario, "w", zipfile.ZIP_DEFLATED) as z:
            for fonte in sorted(FONTES.iterdir()):
                z.writestr(f"Goblinomics/{fonte.name}", _para_windows(fonte))
            z.writestr("Goblinomics/Dados.lua", texto)
        os.replace(temporario, destino / "Goblinomics.zip")
    print(f"addon: {dados.casa['nome']}, {texto.count(b'\n') - 8} itens")
