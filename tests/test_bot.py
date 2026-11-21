"""Testes do bot do Discord sem rede: os botões, janelas e comandos são chamados com uma interação
falsa, e toda resposta é conferida contra os limites do Discord (que recusa a mensagem inteira
quando um campo passa do tamanho)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

try:
    import discord
except ImportError:   # o pacote python3-discord só existe na máquina do bot
    discord = None

if discord:
    from ahforever import botdiscord, botpessoal
    from ahforever.config import Config

GERENTE = 7   # id de quem clica
CANAL_DO_PAINEL, CANAL_PUBLICO, OUTRO_CANAL = 100, 200, 300


class Resposta:
    """O interacao.response: guarda o que o bot mandou em vez de falar com o Discord."""

    def __init__(self):
        self.envios = []

    def is_done(self):
        return bool(self.envios)

    async def send_message(self, content=None, **extras):
        self.envios.append(("mensagem", {"content": content, **extras}))

    async def edit_message(self, **extras):
        self.envios.append(("edicao", extras))

    async def send_modal(self, modal):
        self.envios.append(("janela", {"modal": modal}))

    async def defer(self, **extras):
        self.envios.append(("espera", extras))


class Canal:
    """Um canal falso: guarda o que foi enviado e o que foi apagado."""

    def __init__(self, canal_id, registro):
        self.id, self.registro = canal_id, registro

    async def send(self, content=None, **extras):
        mensagem = SimpleNamespace(id=9000 + len(self.registro), content=content, **extras)
        self.registro.append(("enviado", self.id, mensagem))
        return mensagem

    def get_partial_message(self, mensagem_id):
        async def apagar():
            self.registro.append(("apagado", self.id, mensagem_id))
        return SimpleNamespace(delete=apagar)


def interacao(canal=CANAL_DO_PAINEL, usuario=GERENTE):
    resposta = Resposta()

    async def original():
        return SimpleNamespace(id=555, flags=SimpleNamespace(ephemeral=True))
    return SimpleNamespace(user=SimpleNamespace(id=usuario, display_name="Glom"), channel_id=canal,
                           response=resposta, original_response=original, followup=resposta)


def conferir_cartao(teste, cartao):
    """Os limites de um embed: título 256, descrição 4096, 25 campos de 256/1024, rodapé 2048, 6000 no total."""
    teste.assertLessEqual(len(cartao.title or ""), 256)
    teste.assertLessEqual(len(cartao.description or ""), 4096)
    teste.assertLessEqual(len(cartao.fields), 25)
    for campo in cartao.fields:
        teste.assertTrue(campo.name and campo.value, "campo vazio é recusado pelo Discord")
        teste.assertLessEqual(len(campo.name), 256)
        teste.assertLessEqual(len(campo.value), 1024, campo.name)
    teste.assertLessEqual(len(cartao.footer.text or ""), 2048)
    teste.assertLessEqual(len(cartao), 6000)


def conferir_botoes(teste, view):
    """Os limites dos componentes: 5 linhas de 5, rótulo de botão 80, lista com 1 a 25 opções de 100."""
    teste.assertLessEqual(len(view.children), 25)
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            teste.assertLessEqual(len(item.label or ""), 80)
        elif isinstance(item, discord.ui.Select):
            teste.assertTrue(1 <= len(item.options) <= 25, "lista sem opções ou com mais de 25")
            teste.assertLessEqual(len(item.placeholder or ""), 150)
            for opcao in item.options:
                teste.assertTrue(1 <= len(opcao.label) <= 100 and 1 <= len(opcao.value) <= 100)


def conferir_janela(teste, janela):
    """Janela de perguntas: título 45, até 5 campos, rótulo 45, dica 100."""
    teste.assertLessEqual(len(janela.title), 45)
    teste.assertTrue(1 <= len(janela.children) <= 5)
    for campo in janela.children:
        rotulo = campo._underlying.label   # campo.label avisa que vai ser trocado por ui.Label no discord.py
        teste.assertLessEqual(len(rotulo), 45, rotulo)
        teste.assertLessEqual(len(campo.placeholder or ""), 100)


def conferir(teste, resposta):
    """Confere tudo o que uma resposta mandou e devolve (tipo, argumentos) do único envio."""
    teste.assertEqual(len(resposta.envios), 1, "cada interação precisa de exatamente uma resposta")
    tipo, extras = resposta.envios[0]
    if tipo == "janela":
        conferir_janela(teste, extras["modal"])
        return tipo, extras
    teste.assertLessEqual(len(extras.get("content") or ""), 2000)
    if extras.get("embed") is not None:
        conferir_cartao(teste, extras["embed"])
    if extras.get("view") is not None:
        conferir_botoes(teste, extras["view"])
    teste.assertTrue(extras.get("content") or extras.get("embed") or extras.get("view"), "resposta vazia")
    return tipo, extras


@unittest.skipUnless(discord, "sem o pacote discord")
class TestBot(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        dados = base / "site" / "dados"
        dados.mkdir(parents=True)
        grava = lambda nome, conteudo: (dados / nome).write_text(json.dumps(conteudo))
        self.foto = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        grava("meta.json", {"casa_padrao": 114, "casas": [{"id": 114, "nome": "Horde Auction House", "arquivo": "casa.json"}]})
        # 10 = bolsa (fabricada, com item de receita 13 à venda), 11 e 12 = materiais, 14 = fabricado que ninguém
        # sabe (item de receita 15 à venda), 20 a 59 = poções, para a busca devolver muitos resultados.
        itens = {"10": ["Mageweave Bag", "RARE", 1, 1, 1, 0, "BAG", "inv_bag", "forever-us", 2500],
                 "11": ["Bolt of Mageweave", "COMMON", 1, 1, 7, 5, "", "inv_bolt", "forever-us", 100],
                 "12": ["Silken Thread", "COMMON", 1, 1, 7, 5, "", "", "forever-us", 10],
                 "13": ["Pattern: Mageweave Bag", "UNCOMMON", 1, 1, 9, 2, "", "inv_scroll", "wowhead", 500],
                 "14": ["Runecloth Bag", "RARE", 1, 1, 1, 0, "BAG", "inv_bag2", "forever-us", 5000],
                 "15": ["Pattern: Runecloth Bag", "UNCOMMON", 1, 1, 9, 2, "", "inv_scroll", "forever-us", 500]}
        itens.update({str(i): [f"Healing Potion {i}", "COMMON", 1, 1, 0, 1, "", "inv_potion", "forever-us", 5] for i in range(20, 60)})
        grava("itens.json", {"itens": itens})
        grava("nomes-pt.json", {"itens": {"10": "Bolsa de Magitrama", "14": "Bolsa de Runatrama"}, "profissoes": {"197": "Alfaiataria"}})
        linhas = [[10, "", 90000, 91000, 3, 3], [11, "", 2500, 2600, 50, 5], [13, "", 40000, 40000, 2, 2],
                  [14, "", 300000, 300000, 4, 4], [15, "", 55500, 55500, 1, 1]]
        linhas += [[i, "", 100 * i, 100 * i, 10, 2] for i in range(20, 60)]
        grava("casa.json", {"coletado_em": self.foto, "linhas": linhas,
                            "medias": {"10": 100000, "13": 80000, "20": 5000, "21": 9000},
                            "vendas": {"horas": 12, "itens": {"10": 6, "14": 3, "20": 40, "21": 40}}})
        grava("receitas.json", {"profissoes": {"197": "Tailoring"}, "npc": {"12": 500},
                                "ensina": {"10": [[13, 225]], "14": [[15, 260]]},
                                "receitas": [[6596, 197, "Bags", "Mageweave Bag", 10, 1.0, [[11, 4], [12, 2]]],
                                             [6597, 197, "Bags", "Runecloth Bag", 14, 1.0, [[11, 5]]]]})
        grava("guildas.json", [{"slug": "g", "nome": "G", "membros": [
            {"nome": "Glom Gazingo", "profissoes": [[197, 280]], "receitas": [6596]},
            {"nome": "Layu Amigodokayu", "profissoes": [[197, 100]], "receitas": []}]}])

        cfg = Config("us", "en_US", [2], [], base / "ah.sqlite", base / "cred.env", base / "brutos", 2,
                     pasta_site=base / "site", casa_padrao=114, url_site="https://exemplo.invalid/g/",
                     bot_servidores=[1], bot_resumo_hora=0)
        self.bot = bot = botdiscord.Bot(cfg)
        bot.dados.atualizar()
        bot.painel_fixo = botdiscord.PainelFixo(bot, base / "painel_bot.json")
        bot.painel_fixo.estado.update(canal=CANAL_DO_PAINEL, mensagem=1)
        bot.guardado = botpessoal.Guardado(base / "bot_guilda.json")
        self.registro, self.privadas = [], []
        bot.get_partial_messageable = lambda canal_id, **_: Canal(canal_id, self.registro)

        async def fetch_user(uid):
            async def send(content=None, **extras):
                self.privadas.append((uid, content, extras))
            return SimpleNamespace(send=send)

        async def application_info():
            return SimpleNamespace(owner=SimpleNamespace(id=1))
        bot.fetch_user, bot.application_info = fetch_user, application_info

    async def clicar(self, view, custom_id=None, rotulo=None, **quem):
        """Clica no botão do painel (pelo custom_id) ou de outra tela (pelo rótulo) e confere a resposta."""
        botao = next(b for b in view.children if isinstance(b, discord.ui.Button)
                     and (b.custom_id == custom_id if custom_id else b.label == rotulo))
        i = interacao(**quem)
        await botao.callback(i)
        return conferir(self, i.response)

    async def preencher(self, janela, **campos):
        for nome, valor in campos.items():
            getattr(janela, nome)._value = valor
        i = interacao()
        await janela.on_submit(i)
        return conferir(self, i.response)

    async def escolher(self, view, valor):
        view.lista._values = [str(valor)]
        i = interacao()
        await view.lista.callback(i)
        return conferir(self, i.response)

    # ---- o painel ----

    async def test_todo_botao_do_painel_responde_dentro_dos_limites(self):
        painel = botdiscord.Painel(self.bot)
        conferir_botoes(self, painel)
        ids = [b.custom_id for b in painel.children if b.custom_id]
        self.assertEqual(ids, ["gbx:preco", "gbx:quemfaz", "gbx:personagem", "gbx:mais", "gbx:ajuda"],
                         "custom_id é o que mantém vivo o painel já publicado: não renomear")
        self.assertLessEqual(len(ids), 5, "o painel é curto de propósito: o resto vai em Mais")
        for custom_id in ids:
            with self.subTest(botao=custom_id):
                tipo, extras = await self.clicar(painel, custom_id)
                if custom_id in ("gbx:preco", "gbx:quemfaz"):
                    self.assertEqual(tipo, "janela")
                else:
                    # Tudo que sai do painel é privado: o canal fica só com a mensagem do painel.
                    self.assertEqual((tipo, extras["ephemeral"]), ("mensagem", True))

    async def test_mais_abre_o_resto_e_cada_botao_responde(self):
        _, extras = await self.clicar(botdiscord.Painel(self.bot), "gbx:mais")
        mais = extras["view"]
        conferir_botoes(self, mais)
        rotulos = [b.label for b in mais.children]
        self.assertEqual(rotulos, ["Receita", "Meus alertas", "Ofertas", "Lucro da guilda", "Falta aprender",
                                   "Consumíveis", "Desejos"])
        for rotulo in rotulos:
            with self.subTest(botao=rotulo):
                self.assertIn(f"**{rotulo}**", botdiscord.TEXTO_DO_MAIS)
                tipo, resposta = await self.clicar(mais, rotulo=rotulo)
                if rotulo == "Receita":
                    self.assertEqual(tipo, "janela")
                else:
                    self.assertEqual((tipo, resposta["ephemeral"]), ("mensagem", True))
        # O nome do botão fica no custom_id (registro de uso); o sufixo evita choque entre duas pessoas.
        outro = botdiscord.Mais(self.bot)
        self.assertTrue(all(b.custom_id.startswith("mais:") for b in mais.children))
        self.assertFalse({b.custom_id for b in mais.children} & {b.custom_id for b in outro.children})

    def test_o_texto_do_painel_e_as_instrucoes_citam_todo_botao(self):
        painel_rotulos = ["Preço", "Receita", "Quem faz", "Ofertas", "Lucro da guilda", "Consumíveis", "Desejos",
                          "Falta aprender", "Meu personagem", "Meus alertas", "Mais", "Como usar"]
        instrucoes = "\n".join(texto for _, texto in botdiscord.INSTRUCOES)
        for rotulo in painel_rotulos:
            self.assertIn(f"**{rotulo}**", botdiscord.TEXTO_DO_PAINEL + botdiscord.TEXTO_DO_MAIS)
            if rotulo != "Como usar":
                self.assertIn(f"**{rotulo}**", instrucoes, "botão sem explicação no Como usar")

    async def test_rotulos_do_painel_batem_com_os_botoes(self):
        rotulos = [b.label for b in botdiscord.Painel(self.bot).children if b.custom_id]
        for rotulo in rotulos:
            self.assertIn(f"**{rotulo}**", botdiscord.TEXTO_DO_PAINEL)

    async def test_cartao_do_painel_avisa_quando_a_foto_envelhece(self):
        fixo = self.bot.painel_fixo
        conferir_cartao(self, fixo.cartao())
        self.assertNotIn("⚠️", fixo.cartao().description)
        self.bot.dados.coletado_em = "2026-01-01T00:00:00Z"
        conferir_cartao(self, fixo.cartao())
        self.assertIn("⚠️ Sem foto nova", fixo.cartao().description)

    # ---- consultas de item ----

    async def test_janela_de_item_nada_um_ou_varios(self):
        _, extras = await self.clicar(botdiscord.Mais(self.bot), rotulo="Receita")
        janela = extras["modal"]
        _, nada = await self.preencher(janela, item="xyzzy")
        self.assertIn("Não achei", nada["content"])
        _, um = await self.preencher(janela, item="bolsa de magi")
        self.assertEqual(um["embed"].title, "Bolsa de Magitrama (Mageweave Bag)")
        self.assertNotIn("view", um)   # sem canal público não há botão de publicar
        # 40 poções batem: a lista para em 25, o máximo de uma lista do Discord.
        _, varios = await self.preencher(janela, item="healing potion")
        self.assertIn("25+ itens", varios["content"])
        tipo, escolhido = await self.escolher(varios["view"], 21)
        self.assertEqual((tipo, escolhido["embed"].title), ("edicao", "Healing Potion 21"))

    async def test_cartao_da_receita_mostra_conta_artesao_e_como_aprender(self):
        cartoes = await self.bot.cartoes()
        cartao = cartoes.receita(10)
        conferir_cartao(self, cartao)
        (campo,) = cartao.fields
        self.assertIn("Alfaiataria", campo.name)
        # 4 peças a 26s + 2 fios a 5s (NPC) = 1g 14s; venda 9g menos 5% = 8g 55s.
        for trecho in ("Materiais **1🟡 14⚪**", "Venda (−5%) **8🟡 55⚪**", "✅ Lucro **7🟡 41⚪**", "👥 Glom Gazingo",
                       "📜 [Pattern: Mageweave Bag]", "no leilão por **4🟡** 📉 −50%", "exige 225", " · NPC"):
            self.assertIn(trecho, campo.value)
        self.assertIn("ninguém da guilda sabe ainda", cartoes.receita(14).fields[0].value)
        self.assertIn("Nenhuma receita conhecida", cartoes.receita(11).description)
        conferir_cartao(self, cartoes.preco(10))
        conferir_cartao(self, cartoes.preco(12))   # sem anúncio
        self.assertIn("**Glom Gazingo**", cartoes.quemfaz(10).description)
        self.assertIn("Ninguém da guilda sabe", cartoes.quemfaz(14).description)

    async def test_listas_prontas(self):
        cartoes = await self.bot.cartoes()
        # Poção 20 a 20s contra 50s habituais; a 21 a 21s contra 90s vem primeiro (desconto maior).
        ofertas = cartoes.ofertas().description
        self.assertLess(ofertas.index("Healing Potion 21"), ofertas.index("Healing Potion 20"))
        self.assertIn("Bolsa de Magitrama", cartoes.lucrativas().description)
        # Falta aprender: a bolsa de runatrama; Glom (280) já pode, Layu (100) não.
        faltam = cartoes.faltam().description
        self.assertIn("Bolsa de Runatrama", faltam)
        self.assertIn("**5🟡 55⚪**", faltam)
        self.assertIn("já pode aprender: Glom Gazingo", faltam)
        self.assertNotIn("Layu", faltam)
        self.assertNotIn("Bolsa de Magitrama", faltam)
        for cartao in (cartoes.ofertas(), cartoes.lucrativas(), cartoes.faltam()):
            conferir_cartao(self, cartao)

    async def test_cartoes_cabem_mesmo_com_listas_enormes(self):
        """O Discord recusa a mensagem inteira se um campo estoura; com muito dado o texto é cortado em linha inteira."""
        d = self.bot.dados
        longo = "Receita de Nome Bem Comprido para Estourar o Limite " * 3
        for i in range(20, 60):
            d.itens[i][0] = f"{longo}{i}"
            d.ensina[i] = [[13, 1]]
            d.receitas[i] = [(7000 + i, 197, f"Poção {i}", 1.0, [[j, 1] for j in range(20, 60)])]
            d.habituais[i] = 100 * i * 3
            d.por_dia[i] = 50
        cartoes = await self.bot.cartoes()
        self.bot.guardado.d.update(consumiveis=[[i, 3] for i in range(20, 45)], desejos=[[i, 1] for i in range(20, 45)])
        self.bot.guardado.usuario(GERENTE)["alertas"] = [{"item": i, "tipo": "abaixo", "preco": 1} for i in range(20, 30)]
        for cartao in (cartoes.ofertas(), cartoes.lucrativas(), cartoes.faltam(), cartoes.receita(30), cartoes.consumiveis(),
                       cartoes.desejos(), botpessoal.cartao_dos_alertas(cartoes, self.bot.guardado.usuario(GERENTE)["alertas"])):
            with self.subTest(cartao=cartao.title):
                conferir_cartao(self, cartao)
        conferir_botoes(self, botpessoal.MeusAlertas(self.bot, d, self.bot.guardado.usuario(GERENTE)["alertas"]))

    # ---- mostrar no canal ----

    async def test_mostrar_no_canal_publica_e_depois_apaga(self):
        fixo = self.bot.painel_fixo
        fixo.estado["publico"] = CANAL_PUBLICO
        _, extras = await self.clicar(botdiscord.Mais(self.bot), rotulo="Ofertas")
        tipo, depois = await self.clicar(extras["view"], rotulo="Mostrar no canal")
        self.assertEqual(tipo, "edicao")
        (_, canal, mensagem), = self.registro
        self.assertEqual(canal, CANAL_PUBLICO)
        conferir_cartao(self, mensagem.embed)
        self.assertEqual(mensagem.embed.author.name, "Pedido por Glom")
        self.assertIn("some em 1 hora", mensagem.embed.footer.text)
        botao = depois["view"].children[0]
        self.assertEqual((botao.disabled, botao.label), (True, "Mostrado"))
        # Antes de uma hora fica; depois, é apagada e sai da lista.
        await fixo.limpar()
        self.assertEqual(len(self.registro), 1)
        fixo.estado["publicas"][0][2] -= botdiscord.SEGUNDOS_NO_CANAL
        await fixo.limpar()
        self.assertEqual(self.registro[-1], ("apagado", CANAL_PUBLICO, mensagem.id))
        self.assertEqual(json.loads(fixo.arquivo.read_text())["publicas"], [])

    # ---- meu personagem ----

    async def test_meu_personagem_escolhe_guarda_e_mostra(self):
        painel = botdiscord.Painel(self.bot)
        _, primeiro = await self.clicar(painel, "gbx:personagem")
        self.assertIn("Qual é o seu personagem?", primeiro["content"])
        tipo, escolhido = await self.escolher(primeiro["view"], "Glom Gazingo")
        self.assertEqual(tipo, "edicao")
        self.assertIn("Alfaiataria **280**", escolhido["embed"].description)
        self.assertIn("Bolsa de Magitrama", escolhido["embed"].description)
        self.assertEqual(json.loads(self.bot.guardado.arquivo.read_text())["usuarios"][str(GERENTE)]["personagem"], "Glom Gazingo")
        # Da segunda vez o cartão já vem, sem perguntar; outra pessoa ainda é perguntada.
        _, segundo = await self.clicar(painel, "gbx:personagem")
        self.assertIsNone(segundo["content"])
        self.assertIn("Glom Gazingo", segundo["embed"].title)
        _, outro = await self.clicar(painel, "gbx:personagem", usuario=8)
        self.assertIsNone(outro["embed"])
        # Personagem que saiu da guilda: volta a perguntar em vez de falhar.
        self.bot.guardado.usuario(GERENTE)["personagem"] = "Sumido"
        _, sumido = await self.clicar(painel, "gbx:personagem")
        self.assertIn("Qual é o seu personagem?", sumido["content"])

    # ---- alertas ----

    async def test_alerta_cria_avisa_uma_vez_por_cruzamento_e_apaga(self):
        bot, painel = self.bot, botdiscord.Painel(self.bot)
        _, vazio = await self.clicar(botdiscord.Mais(self.bot), rotulo="Meus alertas")
        self.assertIn("Você não tem alertas", vazio["embed"].description)
        _, extras = await self.clicar(vazio["view"], rotulo="Novo alerta")
        janela = extras["modal"]
        _, ruim = await self.preencher(janela, item="bolsa de magi", preco="barato", tipo="abaixo")
        self.assertIn("Não entendi o preço", ruim["content"])
        _, nada = await self.preencher(janela, item="xyzzy", preco="5", tipo="abaixo")
        self.assertIn("Não achei", nada["content"])
        # A bolsa está a 9g: alvo de 5g ainda não vale.
        _, criado = await self.preencher(janela, item="bolsa de magi", preco="5", tipo="abaixo")
        self.assertEqual(criado["content"], "Alerta criado.")
        alertas = bot.guardado.usuario(GERENTE)["alertas"]
        self.assertEqual(alertas, [{"item": 10, "tipo": "abaixo", "preco": 50000, "avisado": False}])
        # Vários itens batem: escolhe na lista. A poção 30 custa 30s e o alvo é acima de 10s: já nasce no alvo.
        _, varios = await self.preencher(janela, item="healing potion", preco="10s", tipo="Acima")
        tipo, escolhido = await self.escolher(varios["view"], 30)
        self.assertEqual(tipo, "edicao")
        self.assertIn("já está no alvo", escolhido["content"])
        self.assertEqual(alertas[1], {"item": 30, "tipo": "acima", "preco": 1000, "avisado": True})

        await botpessoal.conferir_alertas(bot)
        self.assertEqual(self.privadas, [])   # nada cruzou
        # Foto nova com a bolsa a 4g: um aviso em privado, e só um.
        bot.dados.precos[10][0] = 40000
        bot.dados.coletado_em = "2026-11-19T02:00:00Z"
        await botpessoal.conferir_alertas(bot)
        (uid, _, extras), = self.privadas
        self.assertEqual(uid, GERENTE)
        conferir_cartao(self, extras["embed"])
        self.assertIn("Seu alerta chegou ao alvo", extras["embed"].description)
        bot.dados.coletado_em = "2026-11-19T03:00:00Z"
        await botpessoal.conferir_alertas(bot)
        self.assertEqual(len(self.privadas), 1)
        # Saiu do alvo e voltou: avisa de novo.
        bot.dados.precos[10][0], bot.dados.coletado_em = 90000, "2026-11-19T04:00:00Z"
        await botpessoal.conferir_alertas(bot)
        bot.dados.precos[10][0], bot.dados.coletado_em = 40000, "2026-11-19T05:00:00Z"
        await botpessoal.conferir_alertas(bot)
        self.assertEqual(len(self.privadas), 2)

        _, lista = await self.clicar(botdiscord.Mais(self.bot), rotulo="Meus alertas")
        self.assertIn("✅ no alvo", lista["embed"].description)
        _, apagado = await self.escolher(lista["view"], 0)
        self.assertEqual(apagado["content"], "Alerta apagado.")
        self.assertEqual([a["item"] for a in bot.guardado.usuario(GERENTE)["alertas"]], [30])

    async def test_alerta_respeita_o_maximo_e_anota_privado_fechado(self):
        bot = self.bot
        bot.guardado.usuario(GERENTE)["alertas"] = [{"item": 10, "tipo": "abaixo", "preco": 1, "avisado": False}
                                                    for _ in range(botpessoal.MAX_ALERTAS)]
        i = interacao()
        await botpessoal.criar_alerta(bot, i, 10, "abaixo", 5, editar=False)
        _, extras = conferir(self, i.response)
        self.assertIn("Você já tem 10 alertas", extras["content"])
        self.assertEqual(len(bot.guardado.usuario(GERENTE)["alertas"]), botpessoal.MAX_ALERTAS)

        async def fechado(uid):
            async def send(**_):
                raise discord.HTTPException(SimpleNamespace(status=403, reason="Forbidden"), "mensagens diretas fechadas")
            return SimpleNamespace(send=send)
        bot.fetch_user = fechado
        bot.guardado.usuario(GERENTE)["alertas"] = [{"item": 10, "tipo": "abaixo", "preco": 95000, "avisado": False}]
        with self.assertLogs("goblinomics-bot", "WARNING"):
            await botpessoal.conferir_alertas(bot)
        alerta = bot.guardado.usuario(GERENTE)["alertas"][0]
        self.assertEqual((alerta["avisado"], alerta["falhou"]), (True, True))
        self.assertIn("não consegui te avisar", botpessoal.texto_do_alerta(await bot.cartoes(), alerta))

    # ---- comandos de barra ----

    async def comando(self, qual, canal=OUTRO_CANAL, **argumentos):
        i = interacao(canal=canal)
        await self.bot.tree.get_command(qual).callback(i, **argumentos)
        return conferir(self, i.response)

    async def test_comandos_de_consulta_publicos_fora_do_painel_e_privados_nele(self):
        self.assertEqual(sorted(c.name for c in self.bot.tree.get_commands()),
                         ["canalavisos", "canalpublico", "consumivel", "desejo", "painel", "personagem", "preco",
                          "quemfaz", "receita"])
        for nome in ("preco", "receita", "quemfaz"):
            with self.subTest(comando=nome):
                _, fora = await self.comando(nome, item="bolsa de magi")
                self.assertNotIn("ephemeral", fora)
                self.assertIn("some em 1 hora", fora["embed"].footer.text)
                _, dentro = await self.comando(nome, canal=CANAL_DO_PAINEL, item="10")
                self.assertTrue(dentro["ephemeral"])
                _, nada = await self.comando(nome, item="xyzzy")
                self.assertTrue(nada["ephemeral"])
        # As três respostas públicas ficaram anotadas para serem apagadas em uma hora.
        self.assertEqual([m[:2] for m in self.bot.painel_fixo.estado["publicas"]], [[OUTRO_CANAL, 555]] * 3)

    async def test_listas_da_guilda_poem_trocam_e_tiram(self):
        _, posto = await self.comando("consumivel", item="healing potion 20", valor="3", remover=False)
        self.assertEqual((posto["content"], self.bot.guardado.lista("consumiveis")), ("Incluído.", [[20, 3]]))
        # 3 poções a 20s cada.
        self.assertIn("= **60⚪**", posto["embed"].description)
        self.assertEqual(posto["embed"].fields[0].value, "**60⚪**")
        _, trocado = await self.comando("consumivel", item="20", valor="", remover=False)
        self.assertEqual((trocado["content"], self.bot.guardado.lista("consumiveis")), ("Atualizado.", [[20, 1]]))
        _, ruim = await self.comando("consumivel", item="20", valor="muitos", remover=False)
        self.assertEqual(ruim["content"], "Não entendi o valor.")
        _, tirado = await self.comando("consumivel", item="20", valor="", remover=True)
        self.assertEqual((tirado["content"], self.bot.guardado.lista("consumiveis")), ("Retirado.", []))
        _, ausente = await self.comando("consumivel", item="20", valor="", remover=True)
        self.assertEqual(ausente["content"], "Esse item não estava na lista.")
        # Desejo: a bolsa a 9g com alvo de 10g está boa; sem anúncio aparece sem preço.
        _, desejo = await self.comando("desejo", item="bolsa de magi", valor="10", remover=False)
        self.assertIn("✅ [Bolsa de Magitrama", desejo["embed"].description)
        _, sem = await self.comando("desejo", item="silken", valor="", remover=False)
        self.assertIn("sem anúncio agora", sem["embed"].description)
        self.assertEqual(self.bot.guardado.lista("desejos"), [[10, 100000], [12, None]])
        self.assertEqual(json.loads(self.bot.guardado.arquivo.read_text())["desejos"], [[10, 100000], [12, None]])

    async def test_personagem_de_fora_valida_o_nome(self):
        arquivo = self.bot.cfg.banco.parent / "personagens_extra.json"
        _, ruim = await self.comando("personagem", nome="Glom 123", remover=False)
        self.assertIn("só com letras", ruim["content"])
        _, posto = await self.comando("personagem", nome="  Glom   Gazingo ", remover=False)
        self.assertIn("`glom-gazingo`", posto["content"])
        _, repetido = await self.comando("personagem", nome="glom gazingo", remover=False)
        self.assertIn("já está na lista", repetido["content"])
        self.assertEqual(json.loads(arquivo.read_text()), ["glom-gazingo"])
        _, tirado = await self.comando("personagem", nome="Glom Gazingo", remover=True)
        self.assertIn("Retirado", tirado["content"])
        self.assertEqual(json.loads(arquivo.read_text()), [])

    async def test_canais_publico_e_de_avisos_ligam_e_desligam(self):
        estado = self.bot.painel_fixo.estado
        _, no_painel = await self.comando("canalpublico", canal=CANAL_DO_PAINEL)
        self.assertIn("Este é o canal do painel", no_painel["content"])
        await self.comando("canalpublico", canal=CANAL_PUBLICO)
        await self.comando("canalavisos", canal=CANAL_PUBLICO)
        self.assertEqual((estado["publico"], estado["avisos"]), (CANAL_PUBLICO, CANAL_PUBLICO))
        await self.comando("canalpublico", canal=CANAL_PUBLICO)
        await self.comando("canalavisos", canal=CANAL_PUBLICO)
        self.assertNotIn("publico", estado)
        self.assertNotIn("avisos", estado)

    # ---- tarefas de fundo ----

    async def test_resumo_do_dia_sai_uma_vez_e_substitui_o_anterior(self):
        fixo, d = self.bot.painel_fixo, self.bot.dados
        fixo.estado.update(avisos=CANAL_PUBLICO, resumo_msg=4321,
                           retrato={"Glom Gazingo": {"profissoes": {"197": 200}, "receitas": []}})
        await fixo.resumir()
        apagado, enviado = self.registro
        self.assertEqual(apagado, ("apagado", CANAL_PUBLICO, 4321))
        cartao = enviado[2].embed
        conferir_cartao(self, cartao)
        # Glom aprendeu a bolsa e passou dos 225; a receita 13 está 50% abaixo do habitual mas a guilda já a sabe.
        self.assertIn("📜 **Glom Gazingo** aprendeu [Bolsa de Magitrama", cartao.description)
        self.assertIn("🎉 **Glom Gazingo** chegou a **225** em Alfaiataria", cartao.description)
        self.assertEqual(fixo.estado["resumo_msg"], enviado[2].id)
        await fixo.resumir()
        self.assertEqual(len(self.registro), 2)   # no mesmo dia não repete
        # Sem novidade no dia seguinte: não publica nada.
        fixo.estado["resumo_dia"] = "2000-01-01"
        d.ensina.clear()
        await fixo.resumir()
        self.assertEqual(len(self.registro), 2)

    async def test_vigia_avisa_o_dono_quando_a_coleta_para_e_quando_volta(self):
        fixo, d = self.bot.painel_fixo, self.bot.dados
        await fixo.vigiar()
        self.assertEqual(self.privadas, [])
        d.coletado_em = "2026-01-01T00:00:00Z"
        await fixo.vigiar()
        await fixo.vigiar()
        self.assertEqual(len(self.privadas), 1)
        self.assertIn("A coleta pode estar parada", self.privadas[0][1])
        d.coletado_em = self.foto
        await fixo.vigiar()
        self.assertEqual(len(self.privadas), 2)
        self.assertIn("a coleta voltou", self.privadas[1][1])

    # ---- miudezas ----

    def test_moedas_e_leitura_de_ouro(self):
        botdiscord.MOEDAS.update(ouro="🟡", prata="⚪", cobre="🟤")
        self.assertEqual([botdiscord.moedas(v) for v in (None, 0, 5, 1234, 120000, 12345678)],
                         ["–", "0🟤", "5🟤", "12⚪ 34🟤", "12🟡", "1.234🟡 56⚪"])
        self.assertEqual([botpessoal.ler_ouro(t) for t in ("50", "12,5", "1g 20s 5c", "30s", "0", "", "caro", "-3")],
                         [500000, 125000, 12005, 3000, None, None, None, None])
        self.assertEqual(botpessoal.caber(["a" * 10, "b" * 10, "c" * 10], 23), "a" * 10 + "\n…")


if __name__ == "__main__":
    unittest.main()
