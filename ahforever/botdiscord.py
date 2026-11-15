"""Bot do Discord do Goblinomics: consultas de preço, receita e artesãos da guilda.

Separado do bot dos servidores de jogo. Só lê site/dados; não grava nada e não fala com a Blizzard.
Rodar: python -m ahforever.botdiscord  (precisa do pacote python3-discord e do token em segredos/).
"""
import asyncio
import logging

import discord
from discord import app_commands

from . import config, consulta
from .consulta import moeda

log = logging.getLogger("goblinomics-bot")
DOURADO = 0xF5C542
MAX_RECEITAS = 3


def _por_dia(v):
    return "–" if v is None else f"{v:,.0f}".replace(",", ".") if v >= 10 else f"{v:.1f}".replace(".", ",")


def _pct(atual, habitual):
    if not atual or not habitual:
        return ""
    d = round((atual - habitual) / habitual * 100)
    return f" ({'+' if d > 0 else ''}{d}% frente ao habitual)" if d else " (igual ao habitual)"


class Bot(discord.Client):
    def __init__(self, cfg):
        super().__init__(intents=discord.Intents.none(), allowed_mentions=discord.AllowedMentions.none())
        self.cfg = cfg
        self.dados = consulta.Dados(cfg.pasta_site / "dados", cfg.casa_padrao)
        self.tree = app_commands.CommandTree(self)
        self._registrar()

    async def setup_hook(self):
        await asyncio.to_thread(self.dados.atualizar)
        # Com servidores no config os comandos aparecem na hora; sem eles, valem em todo lugar
        # onde o bot for convidado, e o Discord pode levar até uma hora para mostrar.
        if self.cfg.bot_servidores:
            for servidor in self.cfg.bot_servidores:
                alvo = discord.Object(id=servidor)
                self.tree.copy_global_to(guild=alvo)
                await self.tree.sync(guild=alvo)
        else:
            await self.tree.sync()
        log.info("comandos registrados")

    async def on_ready(self):
        log.info("conectado como %s", self.user)

    async def _fresco(self):
        """Os dados da foto mais recente; uma falha na releitura mantém os anteriores."""
        try:
            await asyncio.to_thread(self.dados.atualizar)
        except Exception as e:
            log.warning("não deu para reler os dados: %s", e)
        return self.dados

    def _cartao(self, d, item_id, titulo=None):
        cartao = discord.Embed(title=titulo or d.nome(item_id), color=DOURADO,
                               url=f"{self.cfg.url_site}#item={item_id}&casa={d.casa['id']}")
        faccao = {"Horde": "Horda", "Alliance": "Aliança"}.get(d.casa["nome"].split()[0], "Neutra")
        cartao.set_footer(text=f"{faccao} {d.casa['id']} · foto de {d.quando():%d/%m %H:%M} · "
                               "a Blizzard atualiza de hora em hora")
        return cartao

    async def _item(self, interacao, texto):
        """Resolve o item pedido ou responde, só para quem pediu, que não achou."""
        d = await self._fresco()
        item_id = d.achar(texto)
        if item_id is None:
            await interacao.response.send_message(f"Não achei nenhum item com “{texto[:80]}”.", ephemeral=True)
        return d, item_id

    def _registrar(self):
        async def sugerir(interacao, atual):
            d = self.dados
            return [app_commands.Choice(name=d.nome(i)[:100], value=str(i)) for i in d.buscar(atual)]

        @self.tree.command(name="preco", description="Preço de um item na casa de leilões")
        @app_commands.describe(item="Nome do item, em português ou inglês")
        @app_commands.autocomplete(item=sugerir)
        async def preco(interacao, item: str):
            d, item_id = await self._item(interacao, item)
            if item_id is None:
                return
            p = d.preco(item_id)
            cartao = self._cartao(d, item_id)
            if p["min"] is None:
                cartao.description = "Sem anúncio com preço de compra agora."
            else:
                cartao.add_field(name="Menor preço", value=moeda(p["min"]) + _pct(p["min"], p["habitual"]), inline=False)
                cartao.add_field(name="À venda", value=f"{p['qtd']:,}".replace(",", "."))
            if p["habitual"]:
                cartao.add_field(name="Habitual (7 dias)", value=moeda(p["habitual"]))
            if p["por_dia"] is not None:
                cartao.add_field(name="Vendas por dia (estimativa)", value="~" + _por_dia(p["por_dia"]))
            if p["npc_paga"]:
                cartao.add_field(name="NPC paga", value=moeda(p["npc_paga"]))
            await interacao.response.send_message(embed=cartao)

        @self.tree.command(name="receita", description="Custo e lucro de fabricar um item, e quem da guilda faz")
        @app_commands.describe(item="Item fabricado, em português ou inglês")
        @app_commands.autocomplete(item=sugerir)
        async def receita(interacao, item: str):
            d, item_id = await self._item(interacao, item)
            if item_id is None:
                return
            receitas = d.fabricar(item_id)
            cartao = self._cartao(d, item_id)
            if not receitas:
                cartao.description = "Nenhuma receita conhecida fabrica este item."
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
            if receitas:
                cartao.description = ("Conta simples, com o material ao preço de agora. O site também considera "
                                      "fabricar os materiais intermediários e a quantidade disponível.")
            await interacao.response.send_message(embed=cartao)

        @self.tree.command(name="quemfaz", description="Quem da guilda sabe fabricar um item")
        @app_commands.describe(item="Item fabricado, em português ou inglês")
        @app_commands.autocomplete(item=sugerir)
        async def quemfaz(interacao, item: str):
            d, item_id = await self._item(interacao, item)
            if item_id is None:
                return
            receitas = d.fabricar(item_id)
            nomes = sorted({n for r in receitas for n in r["quem"]})
            cartao = self._cartao(d, item_id)
            cartao.description = (", ".join(nomes) if nomes else
                                  "Ninguém da guilda sabe fazer ainda." if receitas else
                                  "Nenhuma receita conhecida fabrica este item.")
            await interacao.response.send_message(embed=cartao)


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
