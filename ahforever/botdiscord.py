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

import discord
from discord import app_commands

from . import config, consulta
from .consulta import moeda

log = logging.getLogger("goblinomics-bot")
DOURADO = 0xF5C542
MAX_RECEITAS = 3


def _numero(v):
    return f"{v:,.0f}".replace(",", ".")


def _por_dia(v):
    return "–" if v is None else _numero(v) if v >= 10 else f"{v:.1f}".replace(".", ",")


def _pct(atual, habitual):
    if not atual or not habitual:
        return ""
    d = round((atual - habitual) / habitual * 100)
    return f" ({'+' if d > 0 else ''}{d}% frente ao habitual)" if d else " (igual ao habitual)"


class Cartoes:
    """As respostas do bot, montadas dos dados; servem aos comandos e ao painel."""

    def __init__(self, cfg, dados):
        self.cfg, self.d = cfg, dados

    def base(self, titulo, item_id=None):
        d = self.d
        url = self.cfg.url_site + (f"#item={item_id}&casa={d.casa['id']}" if item_id else "")
        cartao = discord.Embed(title=titulo, color=DOURADO, url=url or None)
        faccao = {"Horde": "Horda", "Alliance": "Aliança"}.get(d.casa["nome"].split()[0], "Neutra")
        cartao.set_footer(text=f"{faccao} {d.casa['id']} · foto de {d.quando():%d/%m %H:%M} · "
                               "a Blizzard atualiza de hora em hora")
        return cartao

    def preco(self, item_id):
        d, p = self.d, self.d.preco(item_id)
        cartao = self.base(d.nome(item_id), item_id)
        if p["min"] is None:
            cartao.description = "Sem anúncio com preço de compra agora."
        else:
            cartao.add_field(name="Menor preço", value=moeda(p["min"]) + _pct(p["min"], p["habitual"]), inline=False)
            cartao.add_field(name="À venda", value=_numero(p["qtd"]))
        if p["habitual"]:
            cartao.add_field(name="Habitual (7 dias)", value=moeda(p["habitual"]))
        if p["por_dia"] is not None:
            cartao.add_field(name="Vendas por dia (estimativa)", value="~" + _por_dia(p["por_dia"]))
        if p["npc_paga"]:
            cartao.add_field(name="NPC paga", value=moeda(p["npc_paga"]))
        return cartao

    def receita(self, item_id):
        d, receitas = self.d, self.d.fabricar(item_id)
        cartao = self.base(d.nome(item_id), item_id)
        if not receitas:
            cartao.description = "Nenhuma receita conhecida fabrica este item."
            return cartao
        cartao.description = ("Conta simples, com o material ao preço de agora. O site também considera "
                              "fabricar os materiais intermediários e a quantidade disponível.")
        for r in receitas[:MAX_RECEITAS]:
            linhas = [f"{q:g} × {d.nome(mid)}: {moeda(preco)} cada ({fonte})" if preco is not None
                      else f"{q:g} × {d.nome(mid)}: {fonte}" for mid, q, preco, fonte in r["materiais"]]
            linhas.append(f"**Materiais:** {moeda(r['custo']) if r['custo'] is not None else 'sem preço completo'}")
            linhas.append(f"**Venda, já sem a taxa de 5%:** {moeda(r['liquido'])}")
            if r["lucro"] is not None:
                linhas.append(f"**{'Lucro' if r['lucro'] >= 0 else 'Prejuízo'}:** {moeda(abs(r['lucro']))}")
            linhas.append("**Na guilda:** " + (", ".join(r["quem"]) if r["quem"] else "ninguém sabe ainda"))
            titulo = r["profissao"] + (f" · faz {r['feitos']:g} por vez" if r["feitos"] != 1 else "")
            cartao.add_field(name=titulo, value="\n".join(linhas)[:1024], inline=False)
        return cartao

    def quemfaz(self, item_id):
        d, receitas = self.d, self.d.fabricar(item_id)
        nomes = sorted({n for r in receitas for n in r["quem"]})
        cartao = self.base(d.nome(item_id), item_id)
        cartao.description = (", ".join(nomes) if nomes else
                              "Ninguém da guilda sabe fazer ainda." if receitas else
                              "Nenhuma receita conhecida fabrica este item.")
        return cartao

    def ofertas(self):
        d = self.d
        cartao = self.base("Ofertas: bem abaixo do preço habitual")
        linhas = [f"**{d.nome(i)}**\n{moeda(minimo)}, habitual {moeda(habitual)} "
                  f"({round((minimo - habitual) / habitual * 100)}%) · vende ~{_por_dia(por_dia)}/dia"
                  for i, minimo, habitual, por_dia in d.ofertas()]
        cartao.description = ("\n".join(linhas)[:4000] if linhas else "Nenhuma oferta com esses critérios agora.")
        cartao.add_field(name="Como ler", inline=False, value=(
            "Itens pelo menos 30% abaixo da média de 7 dias e que vendem 10 ou mais por dia. "
            "A foto tem até uma hora: confira no jogo antes de comprar. Preço baixo também pode ser queda de verdade."))
        return cartao

    def lucrativas(self):
        d = self.d
        cartao = self.base("Receitas com lucro que a guilda sabe fazer")
        linhas = [f"**{d.nome(i)}** ({r['profissao']})\nlucro {moeda(r['lucro'])} · vende ~{_por_dia(d.por_dia.get(i))}/dia"
                  f" · {', '.join(r['quem'][:3])}{' …' if len(r['quem']) > 3 else ''}"
                  for i, r in d.lucrativas()]
        cartao.description = ("\n".join(linhas)[:4000] if linhas else "Nenhuma receita da guilda dá lucro agora.")
        cartao.add_field(name="Como ler", inline=False, value=(
            "Conta simples: materiais ao preço de agora, venda pelo menor preço menos 5%. Ordenadas pelo lucro "
            "vezes o que o mercado vende por dia. No site a conta é mais completa."))
        return cartao


# ---- Painel de botões ----

TITULOS = {"preco": "Preço de qual item?", "receita": "Receita de qual item?", "quemfaz": "Quem faz qual item?"}


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
        cartao = getattr(cartoes, self.consulta_id)(int(self.lista.values[0]))
        await interacao.response.edit_message(content=None, embed=cartao, view=None)


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
            await interacao.response.send_message(embed=getattr(cartoes, self.consulta_id)(achados[0]), ephemeral=True)
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
            self.add_item(discord.ui.Button(label="Abrir o site", url=bot.cfg.url_site, row=1))

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
        await interacao.response.send_message(embed=(await self.bot.cartoes()).ofertas(), ephemeral=True)

    @discord.ui.button(label="Lucro da guilda", emoji="💰", style=discord.ButtonStyle.secondary, custom_id="gbx:lucro", row=1)
    async def lucro(self, interacao, _):
        await interacao.response.send_message(embed=(await self.bot.cartoes()).lucrativas(), ephemeral=True)

    @discord.ui.button(label="Como usar", emoji="❓", style=discord.ButtonStyle.secondary, custom_id="gbx:ajuda", row=1)
    async def ajuda(self, interacao, _):
        cartao = discord.Embed(title="Como usar o Goblinomics", description=INSTRUCOES, color=DOURADO,
                               url=self.bot.cfg.url_site or None)
        await interacao.response.send_message(embed=cartao, ephemeral=True)

    async def on_error(self, interacao, erro, item):
        log.exception("erro no painel", exc_info=erro)
        if not interacao.response.is_done():
            await interacao.response.send_message("Não deu para responder agora. Tente de novo em instantes.", ephemeral=True)


INSTRUCOES = (
    "**Botões do painel** (a resposta aparece só para você)\n"
    "🔎 **Preço**, 🛠️ **Receita** e 👥 **Quem faz** abrem uma janela pedindo o item. Digite um pedaço do nome, "
    "em português ou inglês, sem se preocupar com acento. Se vários itens baterem, escolha na lista.\n"
    "📉 **Ofertas** e 💰 **Lucro da guilda** respondem na hora, sem perguntar nada.\n\n"
    "**Comandos** (a resposta fica à vista de todos no canal)\n"
    "`/preco`, `/receita` e `/quemfaz`: comece a digitar o item e escolha uma das sugestões.\n\n"
    "**Como ler os números**\n"
    "• **Menor preço**: o anúncio mais barato na última foto da casa de leilões.\n"
    "• **Habitual**: a média do menor preço nos últimos 7 dias. A porcentagem compara o preço de agora com ela.\n"
    "• **Vendas por dia**: estimativa, pelo que some entre uma foto e outra.\n"
    "• **Lucro**: venda pelo menor preço menos a taxa de 5%, menos os materiais ao preço de agora.\n"
    "• **Na guilda**: quem sabe fabricar, lido do jogo duas vezes por dia.\n\n"
    "**Limites**\n"
    "• A Blizzard só atualiza os preços de hora em hora; confira no jogo antes de comprar ou vender.\n"
    "• Os preços são da casa de leilões da Horda, ruleset Normal.\n"
    "• O bot só consulta: não compra, não vende e não anuncia nada.\n\n"
    "**No site** há mais: histórico de preço, caminho para subir profissão, lista de compras com exportação "
    "para o Auctionator e a conta completa das receitas.")

TEXTO_DO_PAINEL = (
    "Preços da casa de leilões, direto do Goblinomics. As respostas aparecem só para você.\n\n"
    "🔎 **Preço**: menor preço, habitual e vendas por dia de um item\n"
    "🛠️ **Receita**: custo, lucro e quem da guilda fabrica\n"
    "👥 **Quem faz**: os artesãos da guilda para um item\n"
    "📉 **Ofertas**: itens bem abaixo do preço habitual\n"
    "💰 **Lucro da guilda**: receitas que a guilda sabe fazer e dão lucro agora\n"
    "❓ **Como usar**: instruções e como ler os números\n\n"
    "Para responder à vista de todos, use os comandos `/preco`, `/receita` e `/quemfaz`.")


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

    async def mudar_de_canal(self, canal_id):
        """O painel passa a morar neste canal; o do canal antigo é apagado."""
        antigo = dict(self.estado)
        self.estado = {"canal": canal_id}
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
            try:
                await self.conferir()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("falha ao conferir o painel fixo; nova tentativa no próximo ciclo")
            await asyncio.sleep(120)


class Bot(discord.Client):
    def __init__(self, cfg):
        super().__init__(intents=discord.Intents.none(), allowed_mentions=discord.AllowedMentions.none())
        self.cfg = cfg
        self.dados = consulta.Dados(cfg.pasta_site / "dados", cfg.casa_padrao)
        self.tree = app_commands.CommandTree(self)
        self._registrar()

    async def setup_hook(self):
        await asyncio.to_thread(self.dados.atualizar)
        self.add_view(Painel(self))
        self.painel_fixo = PainelFixo(self, self.cfg.banco.parent / "painel_bot.json")
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

    async def cartoes(self):
        """As respostas sobre a foto mais recente; uma falha na releitura mantém os dados anteriores."""
        try:
            await asyncio.to_thread(self.dados.atualizar)
        except Exception as e:
            log.warning("não deu para reler os dados: %s", e)
        return Cartoes(self.cfg, self.dados)

    def _registrar(self):
        async def sugerir(interacao, atual):
            d = self.dados
            return [app_commands.Choice(name=d.nome(i)[:100], value=str(i)) for i in d.buscar(atual)]

        def consultar(nome, descricao, rotulo):
            @self.tree.command(name=nome, description=descricao)
            @app_commands.describe(item=rotulo)
            @app_commands.autocomplete(item=sugerir)
            async def comando(interacao, item: str):
                cartoes = await self.cartoes()
                item_id = cartoes.d.achar(item)
                if item_id is None:
                    await interacao.response.send_message(f"Não achei nenhum item com “{item[:80]}”.", ephemeral=True)
                    return
                await interacao.response.send_message(embed=getattr(cartoes, nome)(item_id))

        consultar("preco", "Preço de um item na casa de leilões", "Nome do item, em português ou inglês")
        consultar("receita", "Custo e lucro de fabricar um item, e quem da guilda faz", "Item fabricado, em português ou inglês")
        consultar("quemfaz", "Quem da guilda sabe fabricar um item", "Item fabricado, em português ou inglês")

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
