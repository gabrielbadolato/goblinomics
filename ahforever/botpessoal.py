"""A parte pessoal e de guilda do bot: personagem de cada um, alertas de preço em privado,
consumíveis de raide e lista de desejos. O que as pessoas escolhem fica em dados/bot_guilda.json,
fora do git: {"usuarios": {id: {"personagem", "alertas"}}, "consumiveis": [[item, qtd]], "desejos": [[item, alvo]]}.
"""
import json
import logging
import re

import discord

from .consulta import moeda

log = logging.getLogger("goblinomics-bot")
MAX_ALERTAS = 10
MAX_LISTA = 25
DESCONTO_DO_DESEJO = 0.15   # sem alvo, o desejo "está bom" a partir de 15% abaixo do habitual


class Guardado:
    def __init__(self, arquivo):
        self.arquivo = arquivo
        # Arquivo quebrado aparece no registro em vez de virar lista vazia e apagar os alertas de todos.
        self.d = json.loads(arquivo.read_text()) if arquivo.exists() else {}

    def guardar(self):
        temporario = self.arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(self.d, ensure_ascii=False))
        temporario.replace(self.arquivo)

    def usuario(self, uid):
        return self.d.setdefault("usuarios", {}).setdefault(str(uid), {})

    def lista(self, nome):
        return self.d.setdefault(nome, [])


def ler_ouro(texto):
    """'50', '12,5', '1g 20s 5c' ou '30s' em cobre; None se não der para entender."""
    texto = texto.strip().lower().replace(" ", "")
    partes = re.fullmatch(r"(?:(\d+)g)?(?:(\d+)s)?(?:(\d+)c)?", texto)
    if texto and partes and any(partes.groups()):
        ouro, prata, cobre = (int(p or 0) for p in partes.groups())
        return ouro * 10000 + prata * 100 + cobre
    try:
        valor = round(float(texto.replace(",", ".")) * 10000)
    except ValueError:
        return None
    return valor if valor > 0 else None


# ---- Meu personagem ----

def cartao_do_personagem(cartoes, nome):
    d = cartoes.d
    membro = d.personagens.get(nome)
    if membro is None:
        return None
    cartao = cartoes.base(f"{nome}: o que dá lucro agora")
    profissoes = ", ".join(f"{d.profissoes.get(str(p), '?')} {pts}" for p, pts in membro["profissoes"])
    linhas = [f"**{d.nome(i)}** ({r['profissao']})\nlucro {moeda(r['lucro'])} · vende ~{round(d.por_dia.get(i, 0))}/dia"
              for i, r in d.lucrativas(personagem=nome)]
    cartao.description = (f"{profissoes}\n\n" + ("\n".join(linhas) if linhas else
                          "Nenhuma das receitas que você conhece dá lucro agora."))[:4000]
    cartao.add_field(name="Como ler", inline=False, value=(
        "Receitas que este personagem conhece, pela conta simples: materiais ao preço de agora, venda pelo menor "
        "preço menos 5%. As receitas são lidas do jogo duas vezes por dia."))
    return cartao


class MeuPersonagem(discord.ui.View):
    """Lista para escolher (ou trocar) o personagem; a escolha fica guardada por pessoa."""

    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot
        nomes = sorted(bot.dados.personagens)[:25]
        self.lista = discord.ui.Select(placeholder="Escolha o seu personagem", options=[
            discord.SelectOption(label=n[:100], value=n[:100]) for n in nomes])
        self.lista.callback = self.escolher
        self.add_item(self.lista)

    async def escolher(self, interacao):
        nome = self.lista.values[0]
        self.bot.guardado.usuario(interacao.user.id)["personagem"] = nome
        self.bot.guardado.guardar()
        cartao = cartao_do_personagem(await self.bot.cartoes(), nome)
        await interacao.response.edit_message(content=None, embed=cartao, view=MeuPersonagem(self.bot))


async def abrir_personagem(bot, interacao):
    cartoes = await bot.cartoes()
    if not cartoes.d.personagens:
        await interacao.response.send_message("Ainda não há personagens lidos do jogo.", ephemeral=True)
        return
    nome = bot.guardado.usuario(interacao.user.id).get("personagem")
    cartao = cartao_do_personagem(cartoes, nome) if nome else None
    texto = None if cartao else ("Qual é o seu personagem? A escolha fica guardada e você pode trocar quando quiser. "
                                 "Se ele não está na lista, peça a quem gerencia o servidor para incluir com /personagem.")
    await interacao.response.send_message(texto, embed=cartao, view=MeuPersonagem(bot), ephemeral=True)


# ---- Alertas pessoais ----

def texto_do_alerta(d, alerta):
    agora = d.precos.get(alerta["item"], (None,))[0]
    sinal = "≤" if alerta["tipo"] == "abaixo" else "≥"
    estado = " · ✅ valendo agora" if d.alerta_vale(alerta) else ""
    aviso = " · ⚠️ não consegui te avisar em privado" if alerta.get("falhou") else ""
    return f"{d.nome(alerta['item'])}: avisar quando {sinal} {moeda(alerta['preco'])} (agora {moeda(agora)}){estado}{aviso}"


def cartao_dos_alertas(cartoes, alertas):
    cartao = cartoes.base("Meus alertas de preço")
    cartao.description = ("\n".join(f"{n}. {texto_do_alerta(cartoes.d, a)}" for n, a in enumerate(alertas, 1))
                          if alertas else "Você não tem alertas.")
    cartao.add_field(name="Como funciona", inline=False, value=(
        f"Até {MAX_ALERTAS} alertas. A cada foto nova (de hora em hora) o bot confere e te manda uma mensagem privada "
        "quando o menor preço cruza o alvo. Avisa uma vez e só avisa de novo depois que o preço sair do alvo e voltar. "
        "Precisa das mensagens diretas abertas para membros do servidor."))
    return cartao


class NovoAlerta(discord.ui.Modal):
    def __init__(self, bot):
        super().__init__(title="Novo alerta de preço")
        self.bot = bot
        self.item = discord.ui.TextInput(label="Item", placeholder="Português ou inglês; pode ser só um pedaço",
                                         min_length=2, max_length=80)
        self.preco = discord.ui.TextInput(label="Preço-alvo, em ouro", placeholder="Ex.: 50   ou   12,5   ou   30s",
                                          max_length=20)
        self.tipo = discord.ui.TextInput(label="Avisar quando ficar abaixo ou acima?", default="abaixo", max_length=10)
        for campo in (self.item, self.preco, self.tipo):
            self.add_item(campo)

    async def on_submit(self, interacao):
        cartoes = await self.bot.cartoes()
        preco = ler_ouro(self.preco.value)
        tipo = "acima" if self.tipo.value.strip().lower().startswith("ac") else "abaixo"
        achados = cartoes.d.buscar(self.item.value)
        if preco is None:
            await interacao.response.send_message("Não entendi o preço. Use, por exemplo, 50, 12,5 ou 30s.", ephemeral=True)
        elif not achados:
            await interacao.response.send_message(f"Não achei nenhum item com “{self.item.value}”.", ephemeral=True)
        elif len(achados) == 1:
            await criar_alerta(self.bot, interacao, achados[0], tipo, preco, editar=False)
        else:
            await interacao.response.send_message("Qual destes itens?", ephemeral=True,
                                                  view=EscolhaDoAlerta(self.bot, achados, tipo, preco))


class EscolhaDoAlerta(discord.ui.View):
    def __init__(self, bot, itens, tipo, preco):
        super().__init__(timeout=120)
        self.bot, self.tipo, self.preco = bot, tipo, preco
        self.lista = discord.ui.Select(placeholder="Escolha o item", options=[
            discord.SelectOption(label=bot.dados.nome(i)[:100], value=str(i)) for i in itens])
        self.lista.callback = self.escolher
        self.add_item(self.lista)

    async def escolher(self, interacao):
        await criar_alerta(self.bot, interacao, int(self.lista.values[0]), self.tipo, self.preco, editar=True)


async def criar_alerta(bot, interacao, item_id, tipo, preco, editar):
    alertas = bot.guardado.usuario(interacao.user.id).setdefault("alertas", [])
    cartoes = await bot.cartoes()
    if len(alertas) >= MAX_ALERTAS:
        texto = f"Você já tem {MAX_ALERTAS} alertas. Apague um antes de criar outro."
    else:
        alerta = {"item": item_id, "tipo": tipo, "preco": preco}
        # Se já vale agora, nasce como avisado: o aviso é para quando o preço chegar lá, não para o que já está.
        alerta["avisado"] = cartoes.d.alerta_vale(alerta)
        alertas.append(alerta)
        bot.guardado.guardar()
        texto = "Alerta criado." + (" O preço já está no alvo agora; aviso quando sair e voltar." if alerta["avisado"] else "")
    resposta = {"content": texto, "embed": cartao_dos_alertas(cartoes, alertas), "view": MeusAlertas(bot, cartoes.d, alertas)}
    if editar:
        await interacao.response.edit_message(**resposta)
    else:
        await interacao.response.send_message(ephemeral=True, **resposta)


class MeusAlertas(discord.ui.View):
    def __init__(self, bot, dados, alertas):
        super().__init__(timeout=300)
        self.bot = bot
        if alertas:
            self.lista = discord.ui.Select(placeholder="Apagar um alerta", row=1, options=[
                discord.SelectOption(label=f"{n}. {dados.nome(a['item'])}"[:100], value=str(n - 1))
                for n, a in enumerate(alertas, 1)])
            self.lista.callback = self.apagar
            self.add_item(self.lista)

    @discord.ui.button(label="Novo alerta", emoji="➕", style=discord.ButtonStyle.primary, row=0)
    async def novo(self, interacao, _):
        await interacao.response.send_modal(NovoAlerta(self.bot))

    async def apagar(self, interacao):
        alertas = self.bot.guardado.usuario(interacao.user.id).setdefault("alertas", [])
        indice = int(self.lista.values[0])
        if indice < len(alertas):
            alertas.pop(indice)
            self.bot.guardado.guardar()
        cartoes = await self.bot.cartoes()
        await interacao.response.edit_message(content="Alerta apagado.", embed=cartao_dos_alertas(cartoes, alertas),
                                              view=MeusAlertas(self.bot, cartoes.d, alertas))


async def abrir_alertas(bot, interacao):
    cartoes = await bot.cartoes()
    alertas = bot.guardado.usuario(interacao.user.id).setdefault("alertas", [])
    await interacao.response.send_message(embed=cartao_dos_alertas(cartoes, alertas),
                                          view=MeusAlertas(bot, cartoes.d, alertas), ephemeral=True)


async def conferir_alertas(bot):
    """A cada foto nova: avisa em privado quem tem alerta cruzando o alvo, uma vez por cruzamento."""
    d = bot.dados
    if getattr(bot, "_foto_dos_alertas", None) == d.coletado_em:
        return
    bot._foto_dos_alertas = d.coletado_em
    mudou, cartoes = False, None
    for uid, usuario in bot.guardado.d.get("usuarios", {}).items():
        for alerta in usuario.get("alertas", []):
            vale = d.alerta_vale(alerta)
            if vale == bool(alerta.get("avisado")):
                continue
            alerta["avisado"], mudou = vale, True
            if not vale:
                continue
            cartoes = cartoes or await bot.cartoes()
            cartao = cartoes.preco(alerta["item"])
            cartao.description = f"🔔 Seu alerta: {texto_do_alerta(d, alerta)}"
            try:
                await (await bot.fetch_user(int(uid))).send(embed=cartao)
                alerta.pop("falhou", None)
            except discord.HTTPException:
                alerta["falhou"] = True
                log.warning("não consegui enviar um alerta em privado")
    if mudou:
        bot.guardado.guardar()


# ---- Consumíveis de raide e desejos da guilda ----

def cartao_dos_consumiveis(cartoes, lista):
    d = cartoes.d
    cartao = cartoes.base("Consumíveis de raide: custo de hoje")
    if not lista:
        cartao.description = "A lista está vazia. Quem gerencia o servidor monta com `/consumivel`."
        return cartao
    linhas, total, falta = [], 0, False
    for item_id, qtd in lista:
        preco = d.precos.get(item_id, (None,))[0]
        habitual = d.habituais.get(item_id)
        if preco is None:
            falta = True
            linhas.append(f"{qtd} × {d.nome(item_id)}: sem anúncio agora")
            continue
        total += preco * qtd
        pct = f" ({round((preco - habitual) / habitual * 100):+d}% frente ao habitual)" if habitual else ""
        linhas.append(f"{qtd} × {d.nome(item_id)}: {moeda(preco)} cada{pct} = **{moeda(preco * qtd)}**")
    cartao.description = "\n".join(linhas)[:3900]
    cartao.add_field(name="Total por pessoa", value=moeda(total) + (" (sem os itens sem anúncio)" if falta else ""), inline=False)
    return cartao


def cartao_dos_desejos(cartoes, lista):
    d = cartoes.d
    cartao = cartoes.base("Lista de desejos da guilda")
    if not lista:
        cartao.description = "A lista está vazia. Quem gerencia o servidor monta com `/desejo`."
        return cartao
    linhas = []
    for item_id, alvo in lista:
        preco, _, qtd = d.precos.get(item_id, (None, None, 0))
        habitual = d.habituais.get(item_id)
        if preco is None:
            linhas.append(f"▫️ {d.nome(item_id)}: sem anúncio agora")
            continue
        bom = preco <= alvo if alvo else bool(habitual and preco <= habitual * (1 - DESCONTO_DO_DESEJO))
        partes = [f"{moeda(preco)}", f"{qtd:,} à venda".replace(",", ".")]
        if alvo:
            partes.append(f"alvo {moeda(alvo)}")
        if habitual:
            partes.append(f"habitual {moeda(habitual)} ({round((preco - habitual) / habitual * 100):+d}%)")
        linhas.append(f"{'✅' if bom else '▫️'} **{d.nome(item_id)}**: " + " · ".join(partes))
    cartao.description = "\n".join(linhas)[:3900]
    cartao.add_field(name="Como ler", inline=False, value=(
        "✅ marca o que está bom para comprar agora: no alvo definido ou, sem alvo, pelo menos 15% abaixo do habitual."))
    return cartao


def mexer_na_lista(lista, item_id, valor, remover):
    """Põe, troca ou tira [item, valor] da lista. Devolve 'tirado', 'trocado', 'posto', 'cheia' ou 'ausente'."""
    posicao = next((n for n, par in enumerate(lista) if par[0] == item_id), None)
    if remover:
        if posicao is None:
            return "ausente"
        lista.pop(posicao)
        return "tirado"
    if posicao is not None:
        lista[posicao] = [item_id, valor]
        return "trocado"
    if len(lista) >= MAX_LISTA:
        return "cheia"
    lista.append([item_id, valor])
    return "posto"
