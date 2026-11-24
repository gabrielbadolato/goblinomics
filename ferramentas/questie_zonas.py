"""Refaz em site/zonas.json os mapas de ervas e minérios a partir da QuestieDB (base do addon Questie).

Uso:  git clone --depth 1 https://github.com/Questie/QuestieDB.git /tmp/QuestieDB
      python3 -I ferramentas/questie_zonas.py /tmp/QuestieDB [saida.json]

Só lê os arquivos de dados da QuestieDB (não executa nada dela). Monta os itens e objetos do Forever na
ordem da própria base (dados brutos do Classic com coordenadas convertidas -> delta do Forever ->
registros de jogadores) e conta, para cada material, os pontos de coleta por mapa. As correções feitas
à mão pelo Questie (forever*Fixes.lua) não são lidas. Esfolamento e o que estiver com origem "guilda"
ficam como estão. Os dados derivados seguem a licença da QuestieDB (GPL-3.0).
"""
import collections
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lualit  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PROFISSOES = ("182", "186")
# Um mapa entra para o material com pelo menos 3 pontos e 3% dos pontos dele: corta masmorras e sobras.
MIN_PONTOS, MIN_FATIA = 3, 0.03
ITEM = ["name", "npcDrops", "objectDrops"]
OBJETO = ["name", "questStarts", "questEnds", "spawns"]
# Raros que a tabela antiga não tinha. Death Lotus: erva incomum que vale mais que o Lótus Negro; a base não
# diz a frequência do ponto, então fica fora da média por escolha nossa (tirar daqui se a guilda disser que é comum).
RAROS = {248822}
# Mapas que só existem no Forever: sem nome em português nem faixa de nível conhecidos.
NOVOS = {"MOUNT_HYJAL": ("hyjal", "Monte Hyjal", "Mount Hyjal"), "ZEPHRAS_ISLE": ("zephras", "Zephras Isle", "Zephras Isle"),
         "RIVERGLADES": ("riverglades", "Riverglades", "Riverglades")}


def _valores(v):
    return [x for x in (v.values() if isinstance(v, dict) else v or []) if x is not None]


def _bruto(arquivo, campos):
    t = arquivo.read_text(encoding="utf-8")
    d = lualit.tabela(t[t.index("[[return {") + 9: t.rindex("}]]") + 1])
    return {i: {c: v for c, v in zip(campos, lualit.lista(l)) if v is not None} | {"_era": True} for i, l in d.items()}


def _aplicar(base, arquivo):
    t = arquivo.read_text(encoding="utf-8")
    for i, campos in lualit.tabela(t[t.index("return {") + 7: t.rindex("}") + 1]).items():
        e = base.setdefault(i, {})
        for c, v in campos.items():
            if c.endswith("_add"):
                e[c[:-4]] = list(dict.fromkeys(_valores(e.get(c[:-4])) + _valores(v)))
            elif c.endswith("_remove"):
                e[c[:-7]] = [x for x in _valores(e.get(c[:-7])) if x not in set(_valores(v))]
            else:
                e[c] = v


def main(questie, saida):
    c = questie / "src/corrections/Forever"
    itens = _bruto(questie / "data/Forever/foreverItemDB.lua", ITEM)
    objetos = _bruto(questie / "data/Forever/foreverObjectDB.lua", OBJETO)
    for base, nome in ((itens, "Item"), (objetos, "Object")):
        _aplicar(base, c / f"generated/foreverBase{nome}.lua")
        _aplicar(base, c / f"traces/forever{nome}Traces.lua")
    nomes = {int(i): n for n, i in re.findall(
        r"^\s*([A-Z][A-Z0-9_]+)\s*=\s*(\d+)\s*,", (questie / "src/corrections/enum/zones.lua").read_text(), re.M)}

    z = json.loads((RAIZ / "site/zonas.json").read_text())
    chave_por_ingles = {re.sub(r"[^A-Z]", "", v["en"].upper()): k for k, v in z["zonas"].items()}

    def chave(zona_id):
        nome = nomes.get(zona_id)
        if nome in NOVOS:
            k, pt, en = NOVOS[nome]
            z["zonas"].setdefault(k, {"pt": pt, "en": en, "nivel": None})
            return k
        return chave_por_ingles.get(re.sub(r"[^A-Z]", "", nome or ""))

    resumo = []
    for prof in PROFISSOES:
        for item_id in z["profissoes"][prof]:
            antigo = z["materiais"].get(str(item_id), {})
            if antigo.get("origem") == "guilda":
                continue
            item = itens.get(item_id, {})
            pontos = collections.Counter()
            for objeto in _valores(item.get("objectDrops")):
                for zona_id, lista in (objetos.get(objeto, {}).get("spawns") or {}).items():
                    pontos[zona_id] += len(lista) if isinstance(lista, dict) else 0
            total = sum(pontos.values())
            por_chave = {}
            for zona_id, n in pontos.most_common():
                k = chave(zona_id)
                if k and n >= MIN_PONTOS and n >= MIN_FATIA * total:
                    por_chave[k] = por_chave.get(k, 0) + n
            if not por_chave:
                resumo.append(f"{item_id} {item.get('name')}: sem mapa na QuestieDB, mantido como estava")
                continue
            z["materiais"][str(item_id)] = {
                "zonas": list(por_chave), "pontos": list(por_chave.values()),
                # questie: posições do Classic convertidas; forever: só existe no Forever (registros de jogadores).
                "origem": "questie" if item.get("_era") else "forever",
                **({"raro": True} if antigo.get("raro") or item_id in RAROS else {})}
            resumo.append(f"{item_id} {item.get('name')}: {len(por_chave)} mapas, {z['materiais'][str(item_id)]['origem']}")
    versao = subprocess.run(["git", "-C", str(questie), "log", "-1", "--format=%h %ad", "--date=short"],
                            capture_output=True, text=True).stdout.strip()
    z["_fonte"] = (f"Ervas e minérios: QuestieDB (https://github.com/Questie/QuestieDB), commit {versao}, licença GPL-3.0; "
                   "gerado por ferramentas/questie_zonas.py. Esfolamento: tabela do Classic feita à mão.")
    z["_leia"] = ("Onde cada material de coleta nasce. origem 'questie' = QuestieDB, posições do Classic convertidas para o "
                  "Forever; 'forever' = QuestieDB, material que só existe no Forever (registros de jogadores); 'classic' = "
                  "tabela feita à mão, não conferida; 'guilda' = confirmado por alguém da guilda no Forever (a ferramenta não "
                  "mexe). zonas vem do mapa com mais pontos para o com menos; pontos = quantos pontos de coleta a base tem em "
                  "cada um (os de origem 'forever' são inflados e não se comparam com os outros). raro = fica fora da média do "
                  "mapa. nivel null = mapa novo do Forever, faixa desconhecida. Material de 'profissoes' sem entrada em "
                  "'materiais' aparece no site como 'sem mapa conhecido'.")
    z = {"_leia": z.pop("_leia"), "_fonte": z.pop("_fonte"), **z}
    saida.write_text(json.dumps(z, ensure_ascii=False, indent=1) + "\n")
    print("\n".join(resumo))


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "site/zonas.json")
