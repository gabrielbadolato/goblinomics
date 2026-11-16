"""Bot do Discord do Goblinomics: consultas de preço, receita e artesãos da guilda.

Separado do bot dos servidores de jogo. Só lê site/dados; não grava nada e não fala com a Blizzard.
Rodar: python -m ahforever.botdiscord  (precisa do pacote python3-discord e do token em segredos/).

Dois jeitos de usar: os comandos de barra (/preco, /receita, /quemfaz), com a resposta à vista de
todos, e o painel fixo de botões (/painel), em que cada pessoa consulta em privado.
"""
import asyncio
import json
import logging
import time
from datetime import datetime

import discord
from discord import app_commands

from . import botpessoal, config, consulta, guilda

log = logging.getLogger("goblinomics-bot")
DOURADO = 0xF5C542
MAX_RECEITAS = 3


def _numero(v):
    return f"{v:,.0f}".replace(",", ".")


def _por_dia(v):
    return "–" if v is None else _numero(v) if v >= 10 else f"{v:.1f}".replace(".", ",")


def _variacao(atual, habitual):
    """'📉 −12%' frente ao habitual; vazio sem os dois preços."""
    if not atual or not habitual:
        return ""
    d = round((atual - habitual) / habitual * 100)
    return f"{'📈' if d > 0 else '📉' if d < 0 else '➖'} {'+' if d > 0 else '−' if d < 0 else ''}{abs(d)}%"


# Símbolos das moedas. Começam com círculos comuns; ao ligar, o bot troca pelos emojis do
# próprio aplicativo (moeda_ouro, moeda_prata, moeda_cobre: os ícones do jogo, em servico/moedas).
MOEDAS = {"ouro": "🟡", "prata": "⚪", "cobre": "🟤"}


def moedas(cobre):
    """Preço com as moedas do jogo: ouro e prata, ou prata e cobre quando não chega a 1 de ouro."""
    if cobre is None:
        return "–"
    cobre = round(cobre)
    ouro, prata, resto = cobre // 10000, cobre // 100 % 100, cobre % 100
    if ouro:
        partes = [f"{_numero(ouro)}{MOEDAS['ouro']}"] + ([f"{prata}{MOEDAS['prata']}"] if prata else [])
    else:
        partes = ([f"{prata}{MOEDAS['prata']}"] if prata else []) + ([f"{resto}{MOEDAS['cobre']}"] if resto or not prata else [])
    return " ".join(partes)


caber = botpessoal.caber


CORES = {"POOR": 0x9D9D9D, "COMMON": 0xE8E8E8, "UNCOMMON": 0x1EFF00, "RARE": 0x0070DD, "EPIC": 0xA335EE, "LEGENDARY": 0xFF8000}
WOWHEAD = "https://www.wowhead.com/forever/pt/item={}"


class Cartoes:
    """As respostas do bot, montadas dos dados; servem aos comandos e ao painel."""

    def __init__(self, cfg, dados, guardado=None):
        self.cfg, self.d, self.guardado = cfg, dados, guardado

    def m(self, cobre):
        return moedas(cobre)

    def variacao(self, atual, habitual):
        return _variacao(atual, habitual)

    def elo(self, item_id):
        """O nome do item como link para a página dele no Wowhead."""
        return f"[{self.d.nome(item_id)}]({WOWHEAD.format(item_id)})"

    def base(self, titulo, item_id=None):
        """Cartão com o rodapé da foto. Com item: cor da raridade, ícone e atalhos para o Wowhead e o site."""
        d = self.d
        item = d.itens.get(item_id) if item_id else None
        url = self.cfg.url_site + (f"#item={item_id}&casa={d.casa['id']}" if item_id else "")
        cartao = discord.Embed(title=titulo, color=CORES.get(item[1], DOURADO) if item else DOURADO, url=url or None)
        if item and item[7]:
            cartao.set_thumbnail(url=f"https://wow.zamimg.com/images/wow/icons/large/{item[7]}.jpg" if item[8] == "wowhead"
                                 else f"https://render.worldofwarcraft.com/{item[8]}/icons/56/{item[7]}.jpg")
        faccao = {"Horde": "Horda", "Alliance": "Aliança"}.get(d.casa["nome"].split()[0], "Neutra")
        cartao.set_footer(text=f"{faccao} {d.casa['id']} · foto de {d.quando():%d/%m %H:%M}")
        return cartao

    def atalhos(self, item_id):
        partes = [f"[Wowhead]({WOWHEAD.format(item_id)})"]
        if self.cfg.url_site:
            partes.append(f"[Histórico no site]({self.cfg.url_site}#item={item_id}&casa={self.d.casa['id']})")
        return "🔗 " + " · ".join(partes)

    def consumiveis(self):
        return botpessoal.cartao_dos_consumiveis(self, self.guardado.lista("consumiveis"))

    def desejos(self):
        return botpessoal.cartao_dos_desejos(self, self.guardado.lista("desejos"))

    def preco(self, item_id):
        d, p = self.d, self.d.preco(item_id)
        cartao = self.base(d.nome(item_id), item_id)
        if p["min"] is None:
            destaque = "Sem anúncio com preço de compra agora."
        else:
            variacao = _variacao(p["min"], p["habitual"])
            destaque = f"**{moedas(p['min'])}**" + (f"　{variacao} frente ao habitual" if variacao else "")
            cartao.add_field(name="📦 À venda", value=_numero(p["qtd"]))
        cartao.description = f"{destaque}\n{self.atalhos(item_id)}"
        if p["habitual"]:
            cartao.add_field(name="📊 Habitual (7 dias)", value=moedas(p["habitual"]))
        if p["por_dia"] is not None:
            cartao.add_field(name="🔁 Vendas por dia", value="~" + _por_dia(p["por_dia"]))
        if p["npc_paga"]:
            cartao.add_field(name="🏪 NPC paga", value=moedas(p["npc_paga"]))
        return cartao

    def receita(self, item_id):
        d, receitas = self.d, self.d.fabricar(item_id)
        cartao = self.base(d.nome(item_id), item_id)
        if not receitas:
            cartao.description = f"Nenhuma receita conhecida fabrica este item.\n{self.atalhos(item_id)}"
            return cartao
        cartao.description = self.atalhos(item_id)
        for r in receitas[:MAX_RECEITAS]:
            materiais = [f"`{q:g}×` {self.elo(mid)}　{moedas(preco)}" + ("" if fonte == "leilão" else f" · {fonte}")
                         if preco is not None else f"`{q:g}×` {self.elo(mid)}　{fonte}" for mid, q, preco, fonte in r["materiais"]]
            fecho = [f"Materiais **{moedas(r['custo']) if r['custo'] is not None else 'sem preço completo'}**"
                     f"　Venda (−5%) **{moedas(r['liquido'])}**"]
            if r["lucro"] is not None:
                fecho.append(f"{'✅ Lucro' if r['lucro'] >= 0 else '❌ Prejuízo'} **{moedas(abs(r['lucro']))}**")
            fecho.append("👥 " + (", ".join(r["quem"]) if r["quem"] else "ninguém da guilda sabe ainda"))
            fecho += self.como_aprender(r)
            titulo = "🛠️ " + r["profissao"] + (f" · faz {r['feitos']:g} por vez" if r["feitos"] != 1 else "")
            cartao.add_field(name=titulo, inline=False,
                             value=caber(materiais, 1000 - len("\n".join(fecho))) + "\n" + "\n".join(fecho))
        cartao.set_footer(text=cartao.footer.text + " · conta simples; a do site é mais completa")
        return cartao

    def como_aprender(self, r):
        """Linhas sobre como se aprende a receita: o item que a ensina, com o preço no leilão, ou o aviso
        de que esse item nunca apareceu no leilão (em geral, receita de instrutor)."""
        if not r["aprender"]:
            return ["📜 Receita de instrutor ou não negociável: nunca apareceu no leilão"]
        linhas = []
        for a in r["aprender"]:
            exige = f"　exige {a['nivel']}" if a["nivel"] else ""
            preco = (f"no leilão por **{moedas(a['min'])}**" + (f" {_variacao(a['min'], a['habitual'])}" if a["habitual"] else "")
                     if a["min"] is not None else "sem anúncio no leilão agora" +
                     (f" (habitual {moedas(a['habitual'])})" if a["habitual"] else ""))
            linhas.append(f"📜 {self.elo(a['item'])}\n　　{preco}{exige}")
        return linhas

    def quemfaz(self, item_id):
        d, receitas = self.d, self.d.fabricar(item_id)
        nomes = sorted({n for r in receitas for n in r["quem"]})
        cartao = self.base(d.nome(item_id), item_id)
        cartao.description = ("👥 " + ", ".join(f"**{n}**" for n in nomes) if nomes else
                              "👥 Ninguém da guilda sabe fazer ainda." if receitas else
                              "Nenhuma receita conhecida fabrica este item.") + f"\n{self.atalhos(item_id)}"
        return cartao

    def montar(self, consulta_id, item_id=None):
        """O cartão de uma consulta pelo nome dela; as de item recebem o número do item."""
        return getattr(self, consulta_id)(item_id) if item_id is not None else getattr(self, consulta_id)()

    def ofertas(self):
        d = self.d
        cartao = self.base("📉 Ofertas: bem abaixo do preço habitual")
        linhas = [f"`{n:>2}.` {self.elo(i)}\n　　**{moedas(minimo)}**　habitual {moedas(habitual)}　"
                  f"{_variacao(minimo, habitual)}　~{_por_dia(por_dia)}/dia"
                  for n, (i, minimo, habitual, por_dia) in enumerate(d.ofertas(), 1)]
        cartao.description = caber(linhas, 3900) if linhas else "Nenhuma oferta com esses critérios agora."
        cartao.set_footer(text=cartao.footer.text + " · 30% ou mais abaixo da média de 7 dias, 10+ vendas por dia")
        return cartao

    def resumo(self, novidades, promocoes):
        """O resumo diário da guilda; None quando não há nada a contar."""
        d, blocos = self.d, []
        if novidades:
            linhas = []
            for nome, novas, marcos in novidades:
                elos = [self.elo(d.receita_por_id[r][0]) for r in novas if r in d.receita_por_id]
                if novas:
                    mostradas = ", ".join(elos[:4]) or "receitas novas"
                    resto = len(novas) - min(len(elos), 4)
                    linhas.append(f"📜 **{nome}** aprendeu {mostradas}" + (f" e mais {resto}" if resto and elos else ""))
                linhas += [f"🎉 **{nome}** chegou a **{marco}** em {d.profissoes.get(str(prof), 'uma profissão')}"
                           for prof, marco in marcos]
            blocos.append("**Novidades da guilda**\n" + caber(linhas, 2200))
        if promocoes:
            blocos.append("**Receitas que ninguém da guilda sabe, abaixo do habitual**\n" + caber(
                [f"🏷️ {self.elo(i)}\n　　**{moedas(minimo)}**　habitual {moedas(habitual)}　{_variacao(minimo, habitual)}"
                 for i, minimo, habitual in promocoes], 1500))
        if not blocos:
            return None
        cartao = self.base("🗞️ Resumo do dia")
        cartao.description = "\n\n".join(blocos)
        return cartao

    def lucrativas(self):
        d = self.d
        cartao = self.base("💰 Receitas com lucro que a guilda sabe fazer")
        linhas = [f"`{n:>2}.` {self.elo(i)} · {r['profissao']}\n　　lucro **{moedas(r['lucro'])}**　~{_por_dia(d.por_dia.get(i))}/dia"
                  f"　👥 {', '.join(r['quem'][:3])}{' …' if len(r['quem']) > 3 else ''}"
                  for n, (i, r) in enumerate(d.lucrativas(), 1)]
        cartao.description = caber(linhas, 3900) if linhas else "Nenhuma receita da guilda dá lucro agora."
        cartao.set_footer(text=cartao.footer.text + " · conta simples, ordenada pelo lucro vezes as vendas por dia")
        return cartao


# ---- Painel de botões ----

TITULOS = {"preco": "Preço de qual item?", "receita": "Receita de qual item?", "quemfaz": "Quem faz qual item?"}


SEGUNDOS_NO_CANAL = 3600
SEGUNDOS_NO_PAINEL = 300    # quanto uma mensagem avulsa dura no canal do painel
SEGUNDOS_DA_PRIVADA = 600   # precisa ficar abaixo dos 15 minutos que o Discord dá para mexer na resposta
SEGUNDOS_ENTRE_COMANDOS = 8


class Publicar(discord.ui.View):
    """Sob uma resposta privada: botão que mostra o mesmo resultado no canal público, por uma hora.
    Só existe quando um canal público foi escolhido com /canalpublico."""

    def __init__(self, bot, consulta_id, item_id=None):
        super().__init__(timeout=900)
        self.bot, self.consulta_id, self.item_id = bot, consulta_id, item_id

    @discord.ui.button(label="Mostrar no canal", emoji="📣", style=discord.ButtonStyle.secondary)
    async def mostrar(self, interacao, botao):
        canal_id = self.bot.painel_fixo.estado.get("publico")
        if not canal_id:
            await interacao.response.edit_message(view=None)
            return
        cartao = (await self.bot.cartoes()).montar(self.consulta_id, self.item_id)
        cartao.set_author(name=f"Pedido por {interacao.user.display_name}")
        cartao.set_footer(text=cartao.footer.text + " · some em 1 hora")
        try:
            mensagem = await self.bot.get_partial_messageable(canal_id).send(embed=cartao)
        except discord.HTTPException:
            await interacao.response.send_message("Não consegui publicar no canal público.", ephemeral=True)
            return
        self.bot.painel_fixo.anotar_publica(canal_id, mensagem.id)
        botao.disabled, botao.label = True, "Mostrado"
        await interacao.response.edit_message(view=self)


def resposta_privada(bot, consulta_id, item_id=None):
    """Os argumentos de uma resposta só para quem pediu, com o botão de publicar quando há canal público."""
    if bot.painel_fixo.estado.get("publico"):
        return {"view": Publicar(bot, consulta_id, item_id), "ephemeral": True}
    return {"ephemeral": True}


class Escolha(discord.ui.View):
    """Vários itens bateram com o texto: quem pediu escolhe um na lista."""

    def __init__(self, bot, consulta_id, itens):
        super().__init__(timeout=120)
        self.bot, self.consulta_id = bot, consulta_id
        self.lista = discord.ui.Select(placeholder="Escolha o item", options=[
            discord.SelectOption(label=bot.dados.nome(i)[:100], value=str(i)) for i in itens])
        self.lista.callback = self.escolher
        self.add_item(self.lista)

    async def escolher(self, interacao):
        cartoes = await self.bot.cartoes()
        item_id = int(self.lista.values[0])
        await interacao.response.edit_message(content=None, embed=cartoes.montar(self.consulta_id, item_id),
                                              view=resposta_privada(self.bot, self.consulta_id, item_id).get("view"))


class Pergunta(discord.ui.Modal):
    """Janela que pede o nome do item (os botões não têm o autocompletar dos comandos)."""

    def __init__(self, bot, consulta_id):
        super().__init__(title=TITULOS[consulta_id])
        self.bot, self.consulta_id = bot, consulta_id
        self.item = discord.ui.TextInput(label="Nome do item", placeholder="Português ou inglês; pode ser só um pedaço",
                                         min_length=2, max_length=80)
        self.add_item(self.item)

    async def on_submit(self, interacao):
        cartoes = await self.bot.cartoes()
        texto = self.item.value
        achados = cartoes.d.buscar(texto)
        if not achados:
            await interacao.response.send_message(f"Não achei nenhum item com “{texto}”.", ephemeral=True)
        elif len(achados) == 1:
            await interacao.response.send_message(embed=cartoes.montar(self.consulta_id, achados[0]),
                                                  **resposta_privada(self.bot, self.consulta_id, achados[0]))
        else:
            quantos = f"{len(achados)}{'+' if len(achados) == consulta.MAX_SUGESTOES else ''}"
            await interacao.response.send_message(f"{quantos} itens com “{texto}”. Qual deles?",
                                                  view=Escolha(self.bot, self.consulta_id, achados), ephemeral=True)


class Painel(discord.ui.View):
    """Mensagem fixa com botões. As respostas vão só para quem clicou. Os custom_id não mudam:
    é por eles que os botões de um painel antigo continuam funcionando depois de reiniciar o bot."""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        if bot.cfg.url_site:
            self.add_item(discord.ui.Button(label="Abrir o site", url=bot.cfg.url_site, row=3))

    @discord.ui.button(label="Preço", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="gbx:preco", row=0)
    async def preco(self, interacao, _):
        await interacao.response.send_modal(Pergunta(self.bot, "preco"))

    @discord.ui.button(label="Receita", emoji="🛠️", style=discord.ButtonStyle.primary, custom_id="gbx:receita", row=0)
    async def receita(self, interacao, _):
        await interacao.response.send_modal(Pergunta(self.bot, "receita"))

    @discord.ui.button(label="Quem faz", emoji="👥", style=discord.ButtonStyle.primary, custom_id="gbx:quemfaz", row=0)
    async def quemfaz(self, interacao, _):
        await interacao.response.send_modal(Pergunta(self.bot, "quemfaz"))

    @discord.ui.button(label="Ofertas", emoji="📉", style=discord.ButtonStyle.secondary, custom_id="gbx:ofertas", row=1)
    async def ofertas(self, interacao, _):
        await interacao.response.send_message(embed=(await self.bot.cartoes()).ofertas(),
                                              **resposta_privada(self.bot, "ofertas"))

    @discord.ui.button(label="Lucro da guilda", emoji="💰", style=discord.ButtonStyle.secondary, custom_id="gbx:lucro", row=1)
    async def lucro(self, interacao, _):
        await interacao.response.send_message(embed=(await self.bot.cartoes()).lucrativas(),
                                              **resposta_privada(self.bot, "lucrativas"))

    @discord.ui.button(label="Consumíveis", emoji="🧪", style=discord.ButtonStyle.secondary, custom_id="gbx:consumiveis", row=1)
    async def consumiveis(self, interacao, _):
        await interacao.response.send_message(embed=(await self.bot.cartoes()).consumiveis(),
                                              **resposta_privada(self.bot, "consumiveis"))

    @discord.ui.button(label="Desejos", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="gbx:desejos", row=1)
    async def desejos(self, interacao, _):
        await interacao.response.send_message(embed=(await self.bot.cartoes()).desejos(),
                                              **resposta_privada(self.bot, "desejos"))

    @discord.ui.button(label="Meu personagem", emoji="🧙", style=discord.ButtonStyle.success, custom_id="gbx:personagem", row=2)
    async def personagem(self, interacao, _):
        await botpessoal.abrir_personagem(self.bot, interacao)

    @discord.ui.button(label="Meus alertas", emoji="🔔", style=discord.ButtonStyle.success, custom_id="gbx:alertas", row=2)
    async def alertas(self, interacao, _):
        await botpessoal.abrir_alertas(self.bot, interacao)

    @discord.ui.button(label="Como usar", emoji="❓", style=discord.ButtonStyle.secondary, custom_id="gbx:ajuda", row=3)
    async def ajuda(self, interacao, _):
        cartao = discord.Embed(title="❓ Como usar o Goblinomics", color=DOURADO, url=self.bot.cfg.url_site or None)
        for titulo, texto in INSTRUCOES:
            cartao.add_field(name=titulo, value=texto, inline=False)
        await interacao.response.send_message(embed=cartao, ephemeral=True)

    async def on_error(self, interacao, erro, item):
        log.exception("erro no painel", exc_info=erro)
        if not interacao.response.is_done():
            await interacao.response.send_message("Não deu para responder agora. Tente de novo em instantes.", ephemeral=True)


# Instruções do botão "Como usar": (título, texto) de cada bloco. Ao mudar o bot, revisar aqui.
INSTRUCOES = (
    ("🔎 Consultar um item",
     "**Preço**, **Receita** e **Quem faz** abrem uma janela pedindo o item. Digite um pedaço do nome, em português "
     "ou inglês, sem se preocupar com acento nem com a ordem das palavras. Se vários itens baterem, escolha na lista."),
    ("📊 Listas prontas",
     "**Ofertas**: itens 30% ou mais abaixo do habitual e com boa saída.\n"
     "**Lucro da guilda**: receitas que alguém da guilda sabe e dão lucro agora.\n"
     "**Consumíveis**: custo de hoje da lista de raide, por pessoa.\n"
     "**Desejos**: o que a guilda está juntando; ✅ marca o que está bom para comprar."),
    ("🧙 Só seu",
     "**Meu personagem**: escolha o seu uma vez e veja quais das suas receitas dão lucro. Dá para trocar quando quiser.\n"
     "**Meus alertas**: até 10. Escolha item, preço-alvo e se quer aviso abaixo ou acima. O bot confere a cada foto "
     "nova e avisa em mensagem privada, uma vez por cruzamento. Precisa das mensagens diretas abertas para membros "
     "do servidor."),
    ("📣 Privado ou à vista de todos",
     "Tudo que sai dos botões aparece só para você e some sozinho em 10 minutos. Para mostrar um resultado aos outros, use o botão "
     "**Mostrar no canal** que vem embaixo da resposta, ou os comandos `/preco`, `/receita` e `/quemfaz` em outro canal. "
     "O que é publicado some sozinho em 1 hora. O **resumo do dia** sai uma vez por dia no canal de avisos, só "
     "quando há novidade."),
    ("🧾 Como ler uma resposta",
     "• O **título** leva ao item no site, com o histórico de preço. Cada **nome de item** é um link para o Wowhead.\n"
     "• **Menor preço**: o anúncio mais barato na última foto da casa de leilões.\n"
     "• **Habitual**: a média do menor preço em 7 dias. 📈 e 📉 comparam o preço de agora com ela.\n"
     "• **Vendas por dia**: estimativa, pelo que some entre uma foto e outra.\n"
     "• **Lucro**: venda pelo menor preço menos a taxa de 5%, menos os materiais ao preço de agora. É a conta simples; "
     "a do site é mais completa.\n"
     "• **👥 Na guilda**: quem sabe fabricar, lido do jogo duas vezes por dia.\n"
     "• **📜 Receita**: o item que ensina a fabricar e quanto custa no leilão agora. Sem item, é receita de "
     "instrutor ou que não se negocia; a página do Wowhead diz onde conseguir.\n"
     "• A **cor** do cartão é a raridade do item."),
    ("⚠️ Limites",
     "• A Blizzard só atualiza os preços de hora em hora: confira no jogo antes de comprar ou vender.\n"
     "• Os preços são da casa de leilões da Horda, ruleset Normal.\n"
     "• O bot só consulta: não compra, não vende e não anuncia nada."),
    ("🛠️ Para quem gerencia o servidor",
     "`/consumivel` e `/desejo` montam as duas listas · `/personagem` inclui alguém de fora da guilda · "
     "`/painel`, `/canalpublico` e `/canalavisos` escolhem os canais."),
    ("🌐 No site há mais",
     "Histórico de preço, caminho para subir profissão, lista de compras com exportação para o Auctionator "
     "e a conta completa das receitas."),
)

TEXTO_DO_PAINEL = (
    "Preços da casa de leilões, direto do Goblinomics. As respostas aparecem só para você.\n\n"
    "🔎 **Preço**: menor preço, habitual e vendas por dia de um item\n"
    "🛠️ **Receita**: custo, lucro e quem da guilda fabrica\n"
    "👥 **Quem faz**: os artesãos da guilda para um item\n"
    "📉 **Ofertas**: itens bem abaixo do preço habitual\n"
    "💰 **Lucro da guilda**: receitas que a guilda sabe fazer e dão lucro agora\n"
    "🧪 **Consumíveis**: custo de hoje dos consumíveis de raide, por pessoa\n"
    "📋 **Desejos**: o que a guilda está juntando e se está bom para comprar\n"
    "🧙 **Meu personagem**: quais das suas receitas dão lucro agora\n"
    "🔔 **Meus alertas**: aviso em privado quando um item chegar ao seu preço\n"
    "❓ **Como usar**: instruções e como ler os números\n\n"
    "Para mostrar um resultado aos outros, use `/preco`, `/receita` ou `/quemfaz` em outro canal.")


HORAS_DE_ATRASO = 3
MARCA_DO_PAINEL = "Painel do Goblinomics"


class PainelFixo:
    """Uma só mensagem de painel, num canal escolhido com /painel: o bot a recria se for apagada
    e reescreve o trecho dos dados a cada foto nova. O canal e a mensagem ficam num arquivo."""

    def __init__(self, bot, arquivo):
        self.bot, self.arquivo, self.fixado = bot, arquivo, None
        # Arquivo quebrado não pode virar um painel novo em silêncio: o erro aparece no registro.
        self.estado = json.loads(arquivo.read_text()) if arquivo.exists() else {}

    def guardar(self):
        temporario = self.arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(self.estado))
        temporario.replace(self.arquivo)

    def cartao(self):
        d = self.bot.dados
        foto = int(d.quando().timestamp())
        atrasada = time.time() - foto > HORAS_DE_ATRASO * 3600
        dados = (f"**Dados:** foto de <t:{foto}:f> (<t:{foto}:R>) · {_numero(len(d.precos))} itens à venda"
                 + (f"\n⚠️ Sem foto nova há mais de {HORAS_DE_ATRASO} horas: a coleta pode estar parada." if atrasada else ""))
        cartao = discord.Embed(title="Goblinomics", description=TEXTO_DO_PAINEL + "\n\n" + dados, color=DOURADO,
                               url=self.bot.cfg.url_site or None)
        cartao.set_footer(text=MARCA_DO_PAINEL)
        return cartao

    def _e_painel(self, mensagem):
        return (mensagem.author.id == self.bot.user.id and bool(mensagem.components)
                and any(e.title == "Goblinomics" for e in mensagem.embeds))

    async def _achar(self, canal):
        """A mensagem do painel: a guardada ou, se o arquivo se perdeu, a que já está no canal."""
        if self.estado.get("canal") == canal.id and self.estado.get("mensagem"):
            try:
                return await canal.fetch_message(self.estado["mensagem"])
            except discord.NotFound:
                pass
        try:
            async for mensagem in canal.history(limit=200):
                if self._e_painel(mensagem):
                    return mensagem
        except discord.Forbidden:
            log.warning("sem permissão para ler o histórico do canal do painel")
        return None

    async def conferir(self):
        """Garante que o painel existe no canal escolhido e está com os dados da foto atual."""
        if not self.estado.get("canal"):
            return
        await self.bot.cartoes()
        canal = self.bot.get_partial_messageable(self.estado["canal"])
        cartao, mensagem = self.cartao(), await self._achar(canal)
        if mensagem is None:
            mensagem = await canal.send(embed=cartao, view=Painel(self.bot))
            log.info("painel publicado")
        else:
            # Reescreve quando muda o texto (foto nova) ou o conjunto de botões (versão nova do bot).
            esperados = [b.custom_id for b in Painel(self.bot).children]
            atuais = [getattr(b, "custom_id", None) for linha in mensagem.components for b in getattr(linha, "children", [])]
            if not mensagem.embeds or mensagem.embeds[0].description != cartao.description or atuais != esperados:
                mensagem = await mensagem.edit(embed=cartao, view=Painel(self.bot))
                log.info("painel atualizado")
        if self.estado.get("mensagem") != mensagem.id:
            self.estado.update(canal=canal.id, mensagem=mensagem.id)
            self.guardar()
        if self.fixado != mensagem.id:
            self.fixado = mensagem.id
            try:
                if not mensagem.pinned:
                    await mensagem.pin(reason="Painel do Goblinomics")
            except discord.HTTPException:
                log.info("painel publicado, mas sem permissão para fixar; fixe à mão no Discord")

    def anotar_publica(self, canal_id, mensagem_id):
        """Guarda uma resposta pública para apagar depois; no arquivo, para valer mesmo se o bot reiniciar."""
        self.estado.setdefault("publicas", []).append([canal_id, mensagem_id, int(time.time())])
        self.guardar()

    async def limpar(self):
        """Apaga as respostas públicas que já passaram de uma hora."""
        vencidas = [m for m in self.estado.get("publicas", []) if time.time() - m[2] >= SEGUNDOS_NO_CANAL]
        if not vencidas:
            return
        for canal_id, mensagem_id, _ in vencidas:
            try:
                await self.bot.get_partial_messageable(canal_id).get_partial_message(mensagem_id).delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                log.warning("não consegui apagar uma resposta pública vencida")
        self.estado["publicas"] = [m for m in self.estado["publicas"] if m not in vencidas]
        self.guardar()

    async def resumir(self):
        """Uma vez por dia, a partir da hora do config, publica o resumo da guilda no canal de avisos:
        o que cada membro aprendeu desde o resumo anterior e as receitas desconhecidas em promoção.
        Sem novidade não publica nada; o resumo novo substitui o anterior."""
        canal_id, agora = self.estado.get("avisos"), datetime.now()
        hoje = agora.strftime("%Y-%m-%d")
        if not canal_id or agora.hour < self.bot.cfg.bot_resumo_hora or self.estado.get("resumo_dia") == hoje:
            return
        d, antes = self.bot.dados, self.estado.get("retrato")
        cartao = Cartoes(self.bot.cfg, d).resumo(d.novidades(antes) if antes else [], d.receitas_em_promocao())
        # O dia e o retrato são gravados antes de enviar: uma falha no envio não vira resumo repetido.
        anterior = self.estado.get("resumo_msg")
        self.estado.update(resumo_dia=hoje, retrato=d.retrato())
        self.guardar()
        if cartao is None:
            return
        canal = self.bot.get_partial_messageable(canal_id)
        if anterior:
            try:
                await canal.get_partial_message(anterior).delete()
            except discord.HTTPException:
                pass
        mensagem = await canal.send(embed=cartao)
        self.estado["resumo_msg"] = mensagem.id
        self.guardar()
        log.info("resumo do dia publicado")

    async def varrer(self):
        """O canal do painel fica só com o painel: apaga o que mais aparecer lá, de pessoas ou do bot,
        depois de alguns minutos. Mensagens fixadas são preservadas. Pedido do dono do servidor."""
        if not self.estado.get("canal") or not self.estado.get("mensagem"):
            return
        canal = self.bot.get_partial_messageable(self.estado["canal"])
        try:
            async for mensagem in canal.history(limit=50):
                velha = time.time() - mensagem.created_at.timestamp() >= SEGUNDOS_NO_PAINEL
                if mensagem.id != self.estado["mensagem"] and not mensagem.pinned and velha:
                    await mensagem.delete()
                    log.info("canal do painel: mensagem avulsa apagada")
        except discord.Forbidden:
            log.warning("sem permissão para limpar o canal do painel (ler histórico e gerenciar mensagens)")

    async def alertar(self):
        await botpessoal.conferir_alertas(self.bot)

    async def vigiar(self):
        """Avisa o dono do bot, em privado e uma vez só, quando a coleta para e quando volta."""
        atrasada = time.time() - self.bot.dados.quando().timestamp() > HORAS_DE_ATRASO * 3600
        if atrasada == bool(self.estado.get("atraso")):
            return
        self.estado["atraso"] = atrasada
        self.guardar()
        dono = (await self.bot.application_info()).owner
        foto = int(self.bot.dados.quando().timestamp())
        texto = (f"⚠️ Goblinomics: sem foto nova da casa de leilões desde <t:{foto}:f>. A coleta pode estar parada."
                 if atrasada else f"✅ Goblinomics: a coleta voltou. Foto nova de <t:{foto}:f>.")
        try:
            await (await self.bot.fetch_user(dono.id)).send(texto)
            log.info("dono avisado: coleta %s", "parada" if atrasada else "de volta")
        except discord.HTTPException:
            log.warning("não consegui avisar o dono em privado (mensagens diretas fechadas?)")

    async def mudar_de_canal(self, canal_id):
        """O painel passa a morar neste canal; o do canal antigo é apagado."""
        antigo = dict(self.estado)
        self.estado = {**{k: v for k, v in antigo.items() if k != "mensagem"}, "canal": canal_id}
        self.guardar()
        if antigo.get("mensagem") and antigo.get("canal") != canal_id:
            try:
                await self.bot.get_partial_messageable(antigo["canal"]).get_partial_message(antigo["mensagem"]).delete()
            except discord.HTTPException:
                pass
        await self.conferir()

    async def rodar(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for tarefa in (self.bot.cartoes, self.vigiar, self.limpar, self.conferir, self.varrer, self.resumir, self.alertar):
                try:
                    await tarefa()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("falha em %s; nova tentativa no próximo ciclo", tarefa.__name__)
            await asyncio.sleep(120)


class Bot(discord.Client):
    def __init__(self, cfg):
        super().__init__(intents=discord.Intents.none(), allowed_mentions=discord.AllowedMentions.none())
        self.cfg = cfg
        self.dados = consulta.Dados(cfg.pasta_site / "dados", cfg.casa_padrao)
        self.tree = app_commands.CommandTree(self)
        self._sumicos = set()
        self._registrar()

    async def setup_hook(self):
        await asyncio.to_thread(self.dados.atualizar)
        try:
            for emoji in await self.fetch_application_emojis():
                if emoji.name.startswith("moeda_") and emoji.name[6:] in MOEDAS:
                    MOEDAS[emoji.name[6:]] = str(emoji)
        except Exception as e:
            log.warning("sem os emojis das moedas, ficam os círculos: %s", e)
        self.add_view(Painel(self))
        self.painel_fixo = PainelFixo(self, self.cfg.banco.parent / "painel_bot.json")
        self.guardado = botpessoal.Guardado(self.cfg.banco.parent / "bot_guilda.json")
        self._tarefa_do_painel = asyncio.create_task(self.painel_fixo.rodar())
        # Com servidores no config os comandos aparecem na hora; sem eles, valem em todo lugar
        # onde o bot for convidado, e o Discord pode levar até uma hora para mostrar.
        if self.cfg.bot_servidores:
            for servidor in self.cfg.bot_servidores:
                alvo = discord.Object(id=servidor)
                self.tree.copy_global_to(guild=alvo)
                registrados = await self.tree.sync(guild=alvo)
            # Sem isto os comandos ficariam em dobro: os do servidor e os globais de antes.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            registrados = await self.tree.sync()
        log.info("comandos registrados: %s", ", ".join(sorted(c.name for c in registrados)))

    async def on_ready(self):
        log.info("conectado como %s", self.user)

    async def on_interaction(self, interacao):
        # Só o tipo e o nome do comando ou botão: serve para saber se o pedido chegou até aqui.
        dados = interacao.data or {}
        log.info("pedido: %s %s", interacao.type.name, dados.get("name") or dados.get("custom_id") or "")
        if interacao.channel_id == self.painel_fixo.estado.get("canal"):
            tarefa = asyncio.create_task(self._sumir(interacao))
            self._sumicos.add(tarefa)
            tarefa.add_done_callback(self._sumicos.discard)

    async def _sumir(self, interacao):
        """No canal do painel as respostas são privadas, mas ficam na tela de quem pediu até a pessoa
        dispensar. Aqui elas são apagadas sozinhas depois de alguns minutos. Só apaga resposta privada:
        o painel e qualquer mensagem pública ficam de fora."""
        await asyncio.sleep(SEGUNDOS_DA_PRIVADA)
        try:
            mensagem = await interacao.original_response()
            if mensagem.flags.ephemeral and mensagem.id != self.painel_fixo.estado.get("mensagem"):
                await interacao.delete_original_response()
        except discord.HTTPException:
            pass   # já foi dispensada, era só uma janela de pergunta, ou o prazo do Discord (15 min) passou

    async def cartoes(self):
        """As respostas sobre a foto mais recente; uma falha na releitura mantém os dados anteriores."""
        try:
            await asyncio.to_thread(self.dados.atualizar)
        except Exception as e:
            log.warning("não deu para reler os dados: %s", e)
        return Cartoes(self.cfg, self.dados, getattr(self, "guardado", None))

    def _registrar(self):
        async def sugerir(interacao, atual):
            d = self.dados
            return [app_commands.Choice(name=d.nome(i)[:100], value=str(i)) for i in d.buscar(atual)]

        def consultar(nome, descricao, rotulo):
            @self.tree.command(name=nome, description=descricao)
            @app_commands.describe(item=rotulo)
            @app_commands.autocomplete(item=sugerir)
            @app_commands.checks.cooldown(1, SEGUNDOS_ENTRE_COMANDOS)
            async def comando(interacao, item: str):
                cartoes = await self.cartoes()
                item_id = cartoes.d.achar(item)
                if item_id is None:
                    await interacao.response.send_message(f"Não achei nenhum item com “{item[:80]}”.", ephemeral=True)
                    return
                cartao = cartoes.montar(nome, item_id)
                # No canal do painel a resposta é privada: lá só fica a mensagem do painel.
                if interacao.channel_id == self.painel_fixo.estado.get("canal"):
                    await interacao.response.send_message(embed=cartao, **resposta_privada(self, nome, item_id))
                    return
                cartao.set_footer(text=cartao.footer.text + " · some em 1 hora")
                await interacao.response.send_message(embed=cartao)
                self.painel_fixo.anotar_publica(interacao.channel_id, (await interacao.original_response()).id)

        consultar("preco", "Preço de um item na casa de leilões", "Nome do item, em português ou inglês")
        consultar("receita", "Custo e lucro de fabricar um item, e quem da guilda faz", "Item fabricado, em português ou inglês")
        consultar("quemfaz", "Quem da guilda sabe fabricar um item", "Item fabricado, em português ou inglês")

        @self.tree.error
        async def ao_falhar(interacao, erro):
            if isinstance(erro, app_commands.CommandOnCooldown):
                texto = f"Calma: espere {erro.retry_after:.0f} s antes de usar esse comando de novo."
            else:
                log.exception("erro num comando", exc_info=erro)
                texto = "Não deu para responder agora. Tente de novo em instantes."
            if not interacao.response.is_done():
                await interacao.response.send_message(texto, ephemeral=True)

        @self.tree.command(name="canalpublico", description="Define este canal como o lugar do botão Mostrar no canal")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def canalpublico(interacao):
            estado = self.painel_fixo.estado
            if estado.get("publico") == interacao.channel_id:
                estado.pop("publico")
                texto = "Canal público desligado: o botão Mostrar no canal some das respostas."
            elif estado.get("canal") == interacao.channel_id:
                texto = "Este é o canal do painel. Escolha outro canal para as respostas públicas."
            else:
                estado["publico"] = interacao.channel_id
                texto = ("Pronto: as respostas privadas ganham o botão Mostrar no canal, que publica aqui por 1 hora. "
                         "Rode o comando de novo neste canal para desligar.")
            self.painel_fixo.guardar()
            await interacao.response.send_message(texto, ephemeral=True)

        def lista_da_guilda(nome, chave, descricao, rotulo_do_valor, ler_valor, cartao):
            @self.tree.command(name=nome, description=descricao)
            @app_commands.describe(item="Item, em português ou inglês", valor=rotulo_do_valor,
                                   remover="Marque para tirar o item da lista")
            @app_commands.autocomplete(item=sugerir)
            @app_commands.default_permissions(manage_guild=True)
            @app_commands.guild_only()
            async def comando(interacao, item: str, valor: str = "", remover: bool = False):
                cartoes = await self.cartoes()
                item_id, lido = cartoes.d.achar(item), ler_valor(valor)
                if item_id is None:
                    texto = f"Não achei nenhum item com “{item[:80]}”."
                elif lido is False:
                    texto = "Não entendi o valor."
                else:
                    resultado = botpessoal.mexer_na_lista(self.guardado.lista(chave), item_id, lido, remover)
                    self.guardado.guardar()
                    texto = {"posto": "Incluído.", "trocado": "Atualizado.", "tirado": "Retirado.",
                             "ausente": "Esse item não estava na lista.",
                             "cheia": f"A lista já tem {botpessoal.MAX_LISTA} itens."}[resultado]
                await interacao.response.send_message(texto, embed=getattr(cartoes, cartao)(), ephemeral=True)

        def quantidade(texto):
            return int(texto) if texto.strip().isdigit() and int(texto) > 0 else 1 if not texto.strip() else False

        def alvo(texto):
            return None if not texto.strip() else botpessoal.ler_ouro(texto) or False

        lista_da_guilda("consumivel", "consumiveis", "Põe ou tira um item da lista de consumíveis de raide",
                        "Quantidade por pessoa por raide (padrão 1)", quantidade, "consumiveis")
        lista_da_guilda("desejo", "desejos", "Põe ou tira um item da lista de desejos da guilda",
                        "Preço-alvo em ouro (opcional), ex.: 50 ou 30s", alvo, "desejos")

        @self.tree.command(name="personagem", description="Inclui ou tira um personagem de fora da guilda")
        @app_commands.describe(nome="Nome e sobrenome, como no jogo", remover="Marque para tirar o personagem")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def personagem(interacao, nome: str, remover: bool = False):
            slug = "-".join(nome.lower().split())
            arquivo = self.cfg.banco.parent / guilda.EXTRAS
            lista = json.loads(arquivo.read_text()) if arquivo.exists() else []
            if not slug.replace("-", "").isalpha() or len(slug) > 60:
                texto = "Escreva o nome e o sobrenome do personagem, só com letras. Ex.: Glom Gazingo"
            elif remover:
                texto = "Retirado. Ele some do site e do bot na próxima foto nova, em até cerca de uma hora." if slug in lista else "Esse personagem não estava na lista."
                lista = [s for s in lista if s != slug]
            elif slug in lista:
                texto = "Esse personagem já está na lista."
            elif len(lista) >= 20:
                texto = "A lista de personagens de fora já tem 20 nomes."
            else:
                lista.append(slug)
                texto = (f"Anotado: `{slug}`. Na próxima foto nova da casa de leilões (até cerca de uma hora) o personagem é lido do jogo e passa a "
                         "aparecer no site, em Outros personagens, e no botão Meu personagem. Se o nome estiver errado "
                         "ou ele não tiver profissões, simplesmente não aparece.")
            arquivo.write_text(json.dumps(lista))
            await interacao.response.send_message(texto, ephemeral=True)

        @self.tree.command(name="canalavisos", description="Define este canal como o do resumo diário da guilda")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def canalavisos(interacao):
            estado = self.painel_fixo.estado
            if estado.get("avisos") == interacao.channel_id:
                estado.pop("avisos")
                texto = "Resumo diário desligado."
            elif estado.get("canal") == interacao.channel_id:
                texto = "Este é o canal do painel. Escolha outro canal para os avisos."
            else:
                estado["avisos"] = interacao.channel_id
                estado.pop("resumo_dia", None)
                texto = (f"Pronto: o resumo diário da guilda sai aqui, uma vez por dia, a partir das {self.cfg.bot_resumo_hora}h, "
                         "e só quando há novidade. O resumo novo substitui o anterior. Rode o comando de novo para desligar.")
            self.painel_fixo.guardar()
            await interacao.response.send_message(texto, ephemeral=True)

        @self.tree.command(name="painel", description="Fixa neste canal o painel de botões do Goblinomics")
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def painel(interacao):
            await interacao.response.defer(ephemeral=True)
            try:
                await self.painel_fixo.mudar_de_canal(interacao.channel_id)
            except discord.Forbidden:
                await interacao.followup.send("Não consegui publicar aqui: o bot precisa ver o canal, ler o histórico, "
                                              "enviar mensagens e inserir links.", ephemeral=True)
                return
            await interacao.followup.send("Painel fixo neste canal. Se ele for apagado, eu publico de novo; a linha dos "
                                          "dados se atualiza a cada foto nova.", ephemeral=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = config.carregar()
    if not cfg.bot_token.exists():
        raise SystemExit(f"Grave o token do bot em {cfg.bot_token} (permissão 600).")
    token = cfg.bot_token.read_text().strip()
    if not token:
        raise SystemExit(f"{cfg.bot_token} está vazio.")
    Bot(cfg).run(token, log_handler=None)


if __name__ == "__main__":
    main()
