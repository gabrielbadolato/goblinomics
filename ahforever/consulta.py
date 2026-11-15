"""Consultas sobre os arquivos que o site publica (site/dados), para o bot do Discord.

Lê os mesmos JSON da página, então os números batem com os do site. As contas são as simples:
material pelo preço de mercado do leilão ou pelo do NPC, o que for menor, sem a cadeia de
materiais intermediários nem os degraus de preço, que só a página faz.
"""
import json
import unicodedata
from datetime import datetime

HORAS_PARA_VENDAS = 6
TAXA = 0.05          # casas de facção; a neutra cobra 15% e não é a casa do bot
MAX_SUGESTOES = 25   # limite do Discord para o autocompletar
CLASSE_RECEITA = 9
MARCOS = (75, 150, 225, 300)   # habilidades que valem um aviso


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn")


def moeda(cobre):
    if cobre is None:
        return "–"
    cobre = round(cobre)
    ouro, prata, resto = cobre // 10000, cobre // 100 % 100, cobre % 100
    partes = [f"{ouro:,}g".replace(",", ".")] if ouro else []
    if prata or ouro:
        partes.append(f"{prata}s")
    # Com ouro na conta, o cobre só polui.
    if not ouro:
        partes.append(f"{resto}c")
    return " ".join(partes)


class Dados:
    """Os arquivos de uma casa, relidos quando a coleta publica uma foto nova."""

    def __init__(self, pasta, casa_id=None):
        self.pasta, self.casa_id, self._carimbo = pasta, casa_id, None

    def _ler(self, nome, padrao=None):
        arquivo = self.pasta / nome
        return json.loads(arquivo.read_text()) if arquivo.exists() else padrao

    def atualizar(self):
        """Relê tudo se o meta.json mudou. Devolve se releu."""
        carimbo = (self.pasta / "meta.json").stat().st_mtime
        if carimbo == self._carimbo:
            return False
        meta = self._ler("meta.json")
        casa_id = self.casa_id or meta["casa_padrao"]
        casa = next(c for c in meta["casas"] if c["id"] == casa_id)
        foto = self._ler(casa["arquivo"])
        self.casa, self.coletado_em = casa, foto["coletado_em"]
        self.itens = {int(i): v for i, v in self._ler("itens.json")["itens"].items()}
        self.nomes_pt = {int(i): n for i, n in (self._ler("nomes-pt.json", {}).get("itens") or {}).items()}
        # Menor preço entre as variantes, o mercado dela e o total à venda (como no addon).
        self.precos = {}
        for item_id, _, minimo, mercado, quantidade, *_ in foto["linhas"]:
            p = self.precos.setdefault(item_id, [None, None, 0])
            p[2] += quantidade
            if minimo is not None and (p[0] is None or minimo < p[0]):
                p[0], p[1] = minimo, mercado
        self.habituais = {int(i): v for i, v in (foto.get("medias") or {}).items()}
        vendas = foto.get("vendas") or {}
        horas = vendas.get("horas") or 0
        self.por_dia = ({int(i): q / horas * 24 for i, q in vendas.get("itens", {}).items()}
                        if horas >= HORAS_PARA_VENDAS else {})
        receitas = self._ler("receitas.json", {"profissoes": {}, "receitas": [], "npc": {}})
        # Profissões em português quando há tradução, como no site.
        self.profissoes = {**receitas["profissoes"], **(self._ler("nomes-pt.json", {}).get("profissoes") or {})}
        self.npc = {int(i): v for i, v in receitas["npc"].items()}
        self.receitas = {}
        for rid, prof_id, _, nome, item_id, feitos, reagentes in receitas["receitas"]:
            self.receitas.setdefault(item_id, []).append((rid, prof_id, nome, feitos, reagentes))
        self.receita_por_id = {r[0]: (item_id, r[2], r[1]) for item_id, rs in self.receitas.items() for r in rs}
        self.quem, self.membros = {}, {}
        for guilda in self._ler("guildas.json", []):
            if guilda.get("avulsos"):
                continue
            for membro in guilda["membros"]:
                self.membros[membro["nome"]] = membro
                for rid in membro["receitas"]:
                    self.quem.setdefault(rid, []).append(membro["nome"])
        # Busca: nome nas duas línguas, sem acento; quem está à venda vem primeiro.
        self._busca = sorted(
            ((_sem_acento(self.nomes_pt.get(i, "")), _sem_acento(v[0]), i) for i, v in self.itens.items()),
            key=lambda trio: (trio[2] not in self.precos, trio[1]))
        self._carimbo = carimbo
        return True

    def nome(self, item_id):
        """Nome em português com o inglês entre parênteses, quando são diferentes."""
        ingles = self.itens[item_id][0] if item_id in self.itens else f"Item #{item_id}"
        portugues = self.nomes_pt.get(item_id)
        return f"{portugues} ({ingles})" if portugues and portugues != ingles else ingles

    def buscar(self, texto, limite=MAX_SUGESTOES):
        """Itens cujo nome (pt ou en) tem todas as palavras do texto, em qualquer ordem: primeiro os
        que começam com ele, depois os que o contêm inteiro, depois o resto."""
        alvo = " ".join(_sem_acento(texto).split())
        if not alvo:
            return []
        palavras = alvo.split()
        grupos = ([], [], [])
        for pt, en, item_id in self._busca:
            if not (all(p in pt for p in palavras) or all(p in en for p in palavras)):
                continue
            ordem = 0 if pt.startswith(alvo) or en.startswith(alvo) else 1 if alvo in pt or alvo in en else 2
            grupos[ordem].append(item_id)
        return [i for grupo in grupos for i in grupo][:limite]

    def achar(self, texto):
        """O item pedido: pelo número, ou o melhor resultado da busca. None se não há."""
        texto = texto.strip()
        if texto.isdigit() and int(texto) in self.itens:
            return int(texto)
        achados = self.buscar(texto, 1)
        return achados[0] if achados else None

    def preco(self, item_id):
        minimo, mercado, quantidade = self.precos.get(item_id, (None, None, 0))
        return {"min": minimo, "mercado": mercado, "qtd": quantidade, "habitual": self.habituais.get(item_id),
                "por_dia": self.por_dia.get(item_id), "npc_paga": (self.itens.get(item_id) or [None] * 10)[9]}

    def _material(self, item_id):
        minimo, mercado, _ = self.precos.get(item_id, (None, None, 0))
        leilao, npc = mercado if mercado is not None else minimo, self.npc.get(item_id)
        if npc is not None and (leilao is None or npc <= leilao):
            return npc, "NPC"
        return leilao, "leilão" if leilao is not None else "sem anúncio"

    def fabricar(self, item_id):
        """Uma entrada por receita que produz o item: materiais, custo, venda líquida, lucro e quem faz."""
        saida = []
        venda = self.precos.get(item_id, (None,))[0]
        for rid, prof_id, nome, feitos, reagentes in self.receitas.get(item_id, []):
            materiais = [(mid, q, *self._material(mid)) for mid, q in reagentes]
            completo = all(m[2] is not None for m in materiais)
            custo = sum(m[1] * m[2] for m in materiais) if completo else None
            liquido = round(venda * feitos * (1 - TAXA)) if venda is not None else None
            saida.append({"rid": rid, "profissao": self.profissoes.get(str(prof_id), "?"), "nome": nome,
                          "feitos": feitos, "materiais": materiais, "custo": custo, "liquido": liquido,
                          "lucro": liquido - custo if custo is not None and liquido is not None else None,
                          "quem": self.quem.get(rid, [])})
        return saida

    def ofertas(self, limite=10, desconto=0.3, vendas_minimas=10, preco_minimo=100):
        """Itens à venda bem abaixo do preço habitual e que giram: (item, menor preço, habitual, vendas/dia),
        do maior desconto para o menor."""
        achados = []
        for item_id, (minimo, _, _) in self.precos.items():
            habitual, por_dia = self.habituais.get(item_id), self.por_dia.get(item_id)
            if (minimo and habitual and habitual >= preco_minimo and por_dia is not None
                    and por_dia >= vendas_minimas and minimo <= habitual * (1 - desconto)):
                achados.append((item_id, minimo, habitual, por_dia))
        return sorted(achados, key=lambda o: o[1] / o[2])[:limite]

    def lucrativas(self, limite=10, so_da_guilda=True, vendas_minimas=1):
        """Receitas com lucro agora cujo produto vende: (item, receita de fabricar()), do maior lucro
        por dia (lucro vezes o que o mercado absorve) para o menor."""
        achados = []
        for item_id in self.receitas:
            por_dia = self.por_dia.get(item_id)
            if por_dia is None or por_dia < vendas_minimas:
                continue
            for r in self.fabricar(item_id):
                if r["lucro"] and r["lucro"] > 0 and (r["quem"] or not so_da_guilda):
                    achados.append((r["lucro"] * por_dia / r["feitos"], item_id, r))
        achados.sort(key=lambda a: -a[0])
        return [(item_id, r) for _, item_id, r in achados[:limite]]

    def retrato(self):
        """O que cada membro da guilda sabe agora, para comparar no resumo do dia seguinte."""
        return {nome: {"profissoes": {str(p): pts for p, pts in m["profissoes"]}, "receitas": m["receitas"]}
                for nome, m in self.membros.items()}

    def novidades(self, antes):
        """Desde o retrato anterior: (membro, receitas novas, [(profissão, marco alcançado)]).
        Membro que não estava no retrato não conta: tudo dele pareceria novo."""
        saida = []
        for nome, agora in self.retrato().items():
            velho = antes.get(nome)
            if velho is None:
                continue
            novas = sorted(set(agora["receitas"]) - set(velho["receitas"]))
            marcos = [(int(prof), max(m for m in MARCOS if m <= pts)) for prof, pts in agora["profissoes"].items()
                      if any(velho["profissoes"].get(prof, 0) < m <= pts for m in MARCOS)]
            if novas or marcos:
                saida.append((nome, novas, marcos))
        return saida

    def receitas_em_promocao(self, limite=5, desconto=0.3):
        """Itens de receita (Pattern: X, Plans: X…) abaixo do habitual que ensinam algo que ninguém da
        guilda sabe: (item, menor preço, habitual). A ligação com a receita é pelo nome, depois dos dois pontos."""
        # Só profissões que alguém da guilda tem: receita de profissão que ninguém pratica é ruído.
        praticadas = {prof for m in self.membros.values() for prof, _ in m["profissoes"]}
        por_nome = {nome: rid for rid, (_, nome, prof) in self.receita_por_id.items() if prof in praticadas}
        achados = []
        for item_id, (minimo, _, _) in self.precos.items():
            item, habitual = self.itens.get(item_id), self.habituais.get(item_id)
            if not item or item[4] != CLASSE_RECEITA or ": " not in item[0] or not minimo or not habitual:
                continue
            rid = por_nome.get(item[0].split(": ", 1)[1])
            if rid is not None and rid not in self.quem and minimo <= habitual * (1 - desconto):
                achados.append((item_id, minimo, habitual))
        return sorted(achados, key=lambda a: a[1] / a[2])[:limite]

    def quando(self):
        """Hora da foto, no fuso da máquina."""
        return datetime.fromisoformat(self.coletado_em.replace("Z", "+00:00")).astimezone()
