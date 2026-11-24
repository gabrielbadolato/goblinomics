"""Gera site/origens.json: onde se consegue cada item de receita (Pattern, Recipe, Plans…), pela QuestieDB.

Uso:  git clone --depth 1 https://github.com/Questie/QuestieDB.git /tmp/QuestieDB
      python3 -I ferramentas/questie_origens.py /tmp/QuestieDB [saida.json]

Para cada item de classe 9 (receita) com origem na base: vendedores, monstros que derrubam, objetos
(baús), itens que o contêm e quantas missões o dão. Monstros de queda são muitos nas receitas de queda
mundial, então vão no máximo MAX_MONSTROS, com o total ao lado. Os dados derivados seguem a licença da
QuestieDB (GPL-3.0).
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import questie as q  # noqa: E402

CLASSE_RECEITA = 9
MAX_MONSTROS = 6
MINUSCULAS = {"of", "the", "and", "to", "in"}


def _titulo(enum):
    palavras = enum.lower().split("_")
    return " ".join(p if i and p in MINUSCULAS else p.capitalize() for i, p in enumerate(palavras))


def main(questie, saida):
    itens, objetos, npcs = (q.entidades(questie, t) for t in ("Item", "Object", "Npc"))
    por_id, por_nome = q.zonas(questie)
    nossas = json.loads((q.RAIZ / "site/zonas.json").read_text())["zonas"]
    traduzidas = {re.sub(r"[^A-Z]", "", v["en"].upper()): v for v in nossas.values()}
    zonas_usadas, npcs_usados = {}, {}

    def zona(zona_id):
        enum = por_id.get(zona_id)
        if not enum:
            return None
        if zona_id not in zonas_usadas:
            nossa = traduzidas.get(re.sub(r"[^A-Z]", "", enum))
            zonas_usadas[zona_id] = [nossa["en"], nossa["pt"]] if nossa else [_titulo(enum)] * 2
        return zona_id

    def lugar(entidade):
        """A zona declarada da entidade ou, sem ela, a que tem mais pontos."""
        z = q.id_da_zona(entidade.get("zoneID"), por_nome)
        if not z:
            p = q.pontos(entidade.get("spawns"))
            z = max(p, key=p.get) if p else None
        return zona(z) if z else None

    def npc(npc_id):
        n = npcs.get(npc_id)
        if not n or not n.get("name"):
            return None
        if npc_id not in npcs_usados:
            # nome, zona, facção amiga ("A", "H", "AH" ou ""), nível mínimo e máximo
            npcs_usados[npc_id] = [n["name"], lugar(n), n.get("friendlyToFaction") or "", n.get("minLevel"), n.get("maxLevel")]
        return npc_id

    receitas = {}
    for item_id, item in sorted(itens.items()):
        if item.get("class") != CLASSE_RECEITA:
            continue
        e = {}
        vendedores = [n for n in map(npc, q.valores(item.get("vendors"))) if n]
        monstros = [n for n in map(npc, q.valores(item.get("npcDrops"))) if n]
        if vendedores:
            e["v"] = vendedores
        if monstros:
            # Os de nível mais baixo primeiro: são os que dá para matar mais cedo.
            monstros.sort(key=lambda n: (npcs_usados[n][3] or 999, npcs_usados[n][0]))
            e["d"], e["dn"] = monstros[:MAX_MONSTROS], len(monstros)
        coisas = [[o["name"], lugar(o)] for o in (objetos.get(i) for i in q.valores(item.get("objectDrops"))) if o and o.get("name")]
        if coisas:
            e["o"] = coisas[:MAX_MONSTROS]
        dentro = [itens[i]["name"] for i in q.valores(item.get("itemDrops")) if itens.get(i, {}).get("name")]
        if dentro:
            e["i"] = dentro[:MAX_MONSTROS]
        missoes = len(q.valores(item.get("questRewards")))
        if missoes:
            e["q"] = missoes
        if e:
            receitas[item_id] = e
    # Só os NPCs que sobraram nas listas cortadas.
    citados = {n for e in receitas.values() for n in e.get("v", []) + e.get("d", [])}
    dados = {
        "_leia": "Onde se consegue cada item de receita. itens: v vendedores, d monstros que derrubam (no máximo "
                 f"{MAX_MONSTROS}; dn = quantos são ao todo), o objetos [nome, zona], i itens que o contêm, q quantas "
                 "missões o dão. npcs: [nome, zona, facção amiga, nível mín., nível máx.]. zonas: [inglês, português].",
        "_fonte": f"QuestieDB (https://github.com/Questie/QuestieDB), commit {q.versao(questie)}, licença GPL-3.0; "
                  "gerado por ferramentas/questie_origens.py.",
        "zonas": {z: zonas_usadas[z] for z in sorted(zonas_usadas)},
        "npcs": {n: npcs_usados[n] for n in sorted(citados)},
        "itens": receitas,
    }
    saida.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(receitas)} itens de receita com origem, {len(citados)} NPCs, {len(zonas_usadas)} zonas, {saida.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else q.RAIZ / "site/origens.json")
